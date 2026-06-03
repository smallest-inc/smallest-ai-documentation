#!/usr/bin/env python3
"""
Platform spec diff probe.

Compares query parameter coverage between:
  - SOURCE OF TRUTH: Zod schemas in the waves-platform repo
    (apps/main-backend/src/routes/speech/asr/pulse/pulse.asr.schema.ts)
  - DOCS SPEC: AsyncAPI + OpenAPI under fern/apis/waves/

Reports any param the platform accepts but the docs spec does not declare,
and any param the docs spec declares that the platform schema does not have.
This catches the class of regression that PR #187 (unified-spec rewrite)
introduced: the new spec dropped a batch of platform-supported params (10
on WS, 4 on REST, restored in PR #198) silently and no existing probe
could see the gap.

Usage:
  python3 platform_spec_diff.py [--source-of-truth-path PATH] [--mode {advisory,strict}]
                                [--scope {stt,all}]

Exit codes:
  0 — no regression (or advisory mode)
  1 — at least one platform param is missing from the docs spec (strict mode)

The script has no external dependencies; it reads the Zod source as text
with a focused regex, which is robust to whitespace and comment changes
but brittle to large refactors of the schema file shape. When the platform
team changes the schema file's structure, update the patterns below.
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

try:
    import yaml  # pyyaml — available in CI and most local envs
except ImportError:
    print("ERROR: pyyaml not installed. `pip install pyyaml`", file=sys.stderr)
    sys.exit(2)


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PLATFORM_PATH = Path.home() / "Projects/smallest_work/waves-platform"


@dataclass
class ParamSummary:
    name: str
    kind: str = ""           # "enum" / "string" / "number" / "preprocess" / "url"
    enum_values: list[str] = field(default_factory=list)
    default: str | None = None
    notes: str = ""

    def __repr__(self):
        bits = [self.kind or "?"]
        if self.enum_values:
            bits.append("[" + ",".join(self.enum_values) + "]")
        if self.default is not None:
            bits.append(f"default={self.default}")
        return f"{self.name} ({' '.join(bits)})"


# ---------------------------------------------------------------------------
# Zod schema parser (TypeScript source → dict[schema_name, dict[param, ParamSummary]])
# ---------------------------------------------------------------------------

# Each Zod object schema:   export const NAME = z.object({ ... });
# Each extending schema:    export const NAME = OTHER.extend({ ... });
SCHEMA_HEADER_RE = re.compile(
    r"export\s+const\s+(?P<name>\w+)\s*=\s*"
    r"(?:(?P<base>\w+)\s*\.\s*extend\s*\(\s*)?"  # optional <base>.extend(
    r"(?:z\.object\s*\()?"                       # optional z.object(
    r"\s*\{",
    re.MULTILINE,
)


def _match_braces(src: str, open_idx: int) -> int:
    """Return the index of the `}` matching the `{` at open_idx, ignoring
    braces inside strings/comments."""
    depth = 0
    i = open_idx
    n = len(src)
    in_str: str | None = None  # quote char if currently inside a string literal
    in_line_comment = False
    in_block_comment = False
    while i < n:
        ch = src[i]
        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
        elif in_block_comment:
            if ch == "*" and i + 1 < n and src[i + 1] == "/":
                in_block_comment = False
                i += 1
        elif in_str:
            if ch == "\\":
                i += 1
            elif ch == in_str:
                in_str = None
        else:
            if ch == "/" and i + 1 < n and src[i + 1] == "/":
                in_line_comment = True
                i += 1
            elif ch == "/" and i + 1 < n and src[i + 1] == "*":
                in_block_comment = True
                i += 1
            elif ch in ('"', "'", "`"):
                in_str = ch
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return i
        i += 1
    raise ValueError(f"unbalanced braces starting at {open_idx}")


# Param entries inside an object body. We tolerate:
#   name: z.enum([...]).optional().default("x"),
#   name: z.string().optional(),
#   name: z.preprocess((v) => {...}, z.array(z.string()).optional()),
#   name: z.number().int().positive().optional(),
#   name: z.string().url().optional(),
PARAM_LINE_RE = re.compile(
    r"^\s*(?P<name>[a-zA-Z_]\w*)\s*:\s*z(?P<body>\s*\.[^,]*?(?:\([^)]*\))?[^,]*?)"
    r"(?=,\s*$|,\s*//|,\s*\n|\s*$)",
    re.MULTILINE,
)
ENUM_VALUES_RE = re.compile(r"\.enum\s*\(\s*\[(?P<vals>[^\]]*)\]")
DEFAULT_RE = re.compile(r"\.default\s*\(\s*(?P<val>[^)]+)\)")
KIND_HINTS = [
    (re.compile(r"\.preprocess\s*\("), "preprocess"),
    (re.compile(r"\.string\s*\(\s*\)\.url"), "url"),
    (re.compile(r"\.string\s*\(\s*\)"), "string"),
    (re.compile(r"\.number\s*\(\s*\)"), "number"),
    (re.compile(r"\.enum\s*\("), "enum"),
]


def _parse_param_body(body: str) -> ParamSummary:
    kind = "?"
    for pat, label in KIND_HINTS:
        if pat.search(body):
            kind = label
            break
    enum_vals: list[str] = []
    m = ENUM_VALUES_RE.search(body)
    if m:
        raw = m.group("vals")
        enum_vals = [
            v.strip().strip('"').strip("'")
            for v in raw.split(",")
            if v.strip() and not v.strip().startswith("Pulse")  # filter ts enum refs
        ]
    default_val: str | None = None
    m = DEFAULT_RE.search(body)
    if m:
        default_val = m.group("val").strip().strip('"').strip("'")
    return ParamSummary(name="", kind=kind, enum_values=enum_vals, default=default_val)


def parse_zod_schemas(ts_path: Path) -> dict[str, dict[str, ParamSummary]]:
    """Parse all exported z.object / .extend schemas in a TS source file.

    Returns: { schema_name: { param_name: ParamSummary } }
    Extensions are resolved by composing the parent schema's params first
    then overlaying the extension's params.
    """
    src = ts_path.read_text(encoding="utf-8")
    schemas: dict[str, dict[str, ParamSummary]] = {}
    bases: dict[str, str | None] = {}  # schema_name -> parent (None for z.object)

    for m in SCHEMA_HEADER_RE.finditer(src):
        name = m.group("name")
        base = m.group("base")
        open_brace = src.index("{", m.end() - 1)
        close_brace = _match_braces(src, open_brace)
        body = src[open_brace + 1: close_brace]
        params: dict[str, ParamSummary] = {}
        for pm in PARAM_LINE_RE.finditer(body):
            pname = pm.group("name")
            pbody = pm.group("body")
            summary = _parse_param_body(pbody)
            summary.name = pname
            params[pname] = summary
        schemas[name] = params
        bases[name] = base

    # Resolve extension chains by composing.
    resolved: dict[str, dict[str, ParamSummary]] = {}
    for name in schemas:
        chain: list[str] = []
        cur: str | None = name
        while cur:
            chain.append(cur)
            cur = bases.get(cur)
        merged: dict[str, ParamSummary] = {}
        for nm in reversed(chain):
            merged.update(schemas.get(nm, {}))
        resolved[name] = merged
    return resolved


# ---------------------------------------------------------------------------
# Docs spec readers
# ---------------------------------------------------------------------------

def read_asyncapi_query_params(path: Path) -> dict[str, dict]:
    """Read query params from a Smallest AsyncAPI spec.

    Looks at servers.production.bindings.ws.query.properties (base shape
    used in stt-live-ws.yaml).
    """
    doc = yaml.safe_load(path.read_text())
    servers = doc.get("servers", {}) or {}
    for sname, sval in servers.items():
        try:
            props = sval["bindings"]["ws"]["query"]["properties"]
            if isinstance(props, dict):
                return props
        except (KeyError, TypeError):
            continue
    return {}


def read_openapi_query_params(path: Path, operation_id: str) -> dict[str, dict]:
    """Read query params for a given operationId in an OpenAPI 3.0 spec."""
    doc = yaml.safe_load(path.read_text())
    for path_obj in (doc.get("paths") or {}).values():
        for method_obj in path_obj.values():
            if not isinstance(method_obj, dict):
                continue
            if method_obj.get("operationId") != operation_id:
                continue
            params = method_obj.get("parameters", []) or []
            return {p["name"]: p for p in params if p.get("in") == "query"}
    return {}


# ---------------------------------------------------------------------------
# Diff
# ---------------------------------------------------------------------------

@dataclass
class DiffReport:
    scope: str
    protocol: str
    platform_schema: str
    docs_file: str
    missing_in_docs: list[ParamSummary] = field(default_factory=list)
    extra_in_docs: list[str] = field(default_factory=list)


def diff_param_set(
    platform: dict[str, ParamSummary],
    docs: dict[str, dict],
    ignore_in_platform: set[str] = frozenset(),
) -> tuple[list[ParamSummary], list[str]]:
    plat_names = set(platform.keys()) - set(ignore_in_platform)
    docs_names = set(docs.keys())
    missing = [platform[n] for n in sorted(plat_names - docs_names)]
    extra = sorted(docs_names - plat_names - {"model"})  # `model` is a docs-only routing param
    return missing, extra


# Minimum params we expect to find in each schema. Tripwire for parser
# breakage: if waves-platform refactors and our regex stops matching,
# we'd otherwise silently report "in sync" and miss real regressions.
# Bump these floors when the platform genuinely adds params.
MIN_PARAMS = {
    "lightningAsrQuerySchema": 10,           # actual: 14 as of 2026-06-04
    "lightningAsrWebsocketQuerySchema": 15,  # actual: 20 as of 2026-06-04
}


def run_stt_diff(platform_path: Path) -> list[DiffReport]:
    schema_file = (
        platform_path
        / "apps/main-backend/src/routes/speech/asr/pulse/pulse.asr.schema.ts"
    )
    if not schema_file.exists():
        raise SystemExit(f"platform schema file not found at {schema_file}")

    schemas = parse_zod_schemas(schema_file)
    rest_schema = schemas.get("lightningAsrQuerySchema", {})
    ws_schema = schemas.get("lightningAsrWebsocketQuerySchema", {})

    if not rest_schema or not ws_schema:
        raise SystemExit("could not find expected Pulse schemas in the source file")

    # Sanity floor — if the parser regressed (waves-platform refactor, syntax change,
    # etc.), bail loudly instead of silently green.
    for sname, schema in (("lightningAsrQuerySchema", rest_schema),
                          ("lightningAsrWebsocketQuerySchema", ws_schema)):
        floor = MIN_PARAMS[sname]
        if len(schema) < floor:
            raise SystemExit(
                f"parser sanity check failed: parsed only {len(schema)} params from {sname} "
                f"(expected ≥ {floor}). The Zod regex likely needs an update — "
                f"inspect {schema_file} for syntax that doesn't match PARAM_LINE_RE."
            )

    reports: list[DiffReport] = []

    # REST — POST /waves/v1/stt/ ; operationId: transcribe
    docs_rest = read_openapi_query_params(
        REPO_ROOT / "fern/apis/waves/openapi/stt-openapi.yaml", "transcribe"
    )
    # `webhook_*` params are documented on REST already and platform-supported there;
    # nothing to ignore here. Keep the strict comparison.
    miss, extra = diff_param_set(rest_schema, docs_rest)
    reports.append(DiffReport(
        scope="stt",
        protocol="REST",
        platform_schema="lightningAsrQuerySchema",
        docs_file="fern/apis/waves/openapi/stt-openapi.yaml",
        missing_in_docs=miss,
        extra_in_docs=extra,
    ))

    # WS — wss://api.smallest.ai/waves/v1/stt/live
    docs_ws = read_asyncapi_query_params(
        REPO_ROOT / "fern/apis/waves/asyncapi/stt-live-ws.yaml"
    )
    # webhook_* doesn't apply to WS — platform schema inherits them via .extend but
    # they're meaningless on a live socket; ignore the false positive.
    miss, extra = diff_param_set(
        ws_schema, docs_ws,
        ignore_in_platform={"webhook_url", "webhook_method", "webhook_extra"},
    )
    reports.append(DiffReport(
        scope="stt",
        protocol="WS",
        platform_schema="lightningAsrWebsocketQuerySchema",
        docs_file="fern/apis/waves/asyncapi/stt-live-ws.yaml",
        missing_in_docs=miss,
        extra_in_docs=extra,
    ))

    return reports


def print_report(reports: list[DiffReport]) -> int:
    bar = "=" * 78
    print(bar)
    print(f"Platform-vs-docs spec diff — {len(reports)} surfaces checked")
    print(bar)
    total_missing = 0
    for r in reports:
        print(f"\n[{r.scope.upper()} / {r.protocol}]")
        print(f"  platform: {r.platform_schema}")
        print(f"  docs:     {r.docs_file}")
        if r.missing_in_docs:
            print(f"  ❌ {len(r.missing_in_docs)} platform param(s) missing from docs:")
            for p in r.missing_in_docs:
                print(f"     - {p}")
            total_missing += len(r.missing_in_docs)
        if r.extra_in_docs:
            print(f"  ℹ️  {len(r.extra_in_docs)} param(s) in docs but not in platform schema:")
            for p in r.extra_in_docs:
                print(f"     - {p}")
        if not r.missing_in_docs and not r.extra_in_docs:
            print("  ✅ in sync")
    print()
    print(bar)
    if total_missing:
        print(f"FAIL — {total_missing} platform param(s) missing from docs")
    else:
        print("PASS — every platform-supported param is in the docs spec")
    print(bar)
    return total_missing


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-of-truth-path",
        type=Path,
        default=DEFAULT_PLATFORM_PATH,
        help=f"Path to the waves-platform checkout (default: {DEFAULT_PLATFORM_PATH})",
    )
    parser.add_argument(
        "--mode",
        choices=["advisory", "strict"],
        default="advisory",
        help="advisory: always exit 0; strict: exit 1 if missing params",
    )
    parser.add_argument(
        "--scope",
        choices=["stt", "all"],
        default="stt",
        help="which API surface to check (only STT supported in v1)",
    )
    args = parser.parse_args()

    reports = run_stt_diff(args.source_of_truth_path)
    # TTS + Atoms support: extend here when their schema files are wired.

    missing = print_report(reports)
    if args.mode == "strict" and missing:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
