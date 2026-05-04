"""Atoms — testAutomation ↔ Fern OpenAPI endpoint-surface diff.

Extracts every (HTTP method, path) tuple actually exercised by
`smallest-inc/testAutomation` (api-tests/) and compares it against the
endpoint surface declared in `fern/apis/atoms/openapi/openapi.yaml`.
Endpoints in testAutomation but NOT in Fern OpenAPI are the canonical
"docs gap" — undocumented endpoints customers may discover via SDK or
trial-and-error. Endpoints in OpenAPI but NOT in testAutomation are
"unverified" — could be stale or pre-release.

Why this exists
---------------
The live read-only GET probe (scripts/probes/atoms.py) can only safely
probe ~11 endpoints. Atoms has ~40+. testAutomation runs all of them
(GET/POST/PUT/DELETE) end-to-end as part of its own CI, so its endpoint
surface is the single freshest source of truth for what the platform
actually serves. Diffing testAutomation vs Fern OpenAPI catches:

- New endpoints shipped in testAutomation but never added to OpenAPI
  → SDK won't generate a method for them; docs page is missing.
- Endpoints removed from testAutomation but still in OpenAPI
  → docs claim something the platform no longer does.
- Method changes (POST → PUT, etc.) on existing endpoints.

Field-level drift (renamed properties, default-value changes, required-
vs-optional flips) is OUT OF SCOPE for this v1. testAutomation tests
exercise fields via assertions, not declarative schemas — extracting
field-level expectations would require AST parsing the test code.
Tracked as a follow-up.

Usage:
    python3 scripts/probes/atoms_spec_diff.py \\
        --testautomation /path/to/testAutomation \\
        --openapi fern/apis/atoms/openapi/openapi.yaml \\
        [--markdown] [--baseline scripts/probes/baseline-atoms-spec-diff.json]

Exit code: 0 = no diff, 1 = drift detected, 2 = error.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml

# Match `atoms.get('/atoms/v1/agent')`, `atoms.post("/atoms/v1/agent/${id}")`, etc.
TS_CALL_RE = re.compile(
    r"""atoms\.(?P<method>get|post|put|delete|patch)\s*\(\s*['"`](?P<path>/atoms/v1[^'"`]+)['"`]""",
    re.IGNORECASE,
)

# Path-template substitution: `${anything}` and `:param` and `{param}` all
# normalise to a generic `{p}` placeholder for cross-source comparison.
PATH_PARAM_RE = re.compile(r"(\$\{[^}]+\}|:[A-Za-z_][A-Za-z0-9_]*|\{[^}]+\})")
PREFIX = "/atoms/v1"


def normalise_path(path: str) -> str:
    """Strip the /atoms/v1 prefix and normalise path params to {p}.

    Both Fern OpenAPI (which omits the prefix) and testAutomation (which
    includes it) reduce to the same shape after this. Path params from
    either source — `{id}`, `${agentId}`, `:agentId` — collapse to
    `{p}` so renames don't false-positive.
    """
    s = path.strip()
    if s.startswith(PREFIX):
        s = s[len(PREFIX):]
    if not s.startswith("/"):
        s = "/" + s
    s = PATH_PARAM_RE.sub("{p}", s)
    s = s.rstrip("/")
    return s or "/"


def extract_testautomation_endpoints(repo_root: Path) -> set[tuple[str, str]]:
    """Return {(METHOD, normalised_path)} from every .ts test under api-tests/."""
    found: set[tuple[str, str]] = set()
    test_root = repo_root / "api-tests" / "tests"
    if not test_root.exists():
        raise SystemExit(f"testAutomation api-tests/tests dir not found at {test_root}")
    for f in test_root.rglob("*.ts"):
        try:
            text = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for m in TS_CALL_RE.finditer(text):
            found.add((m.group("method").upper(), normalise_path(m.group("path"))))
    return found


def extract_openapi_endpoints(spec_path: Path) -> set[tuple[str, str]]:
    """Return {(METHOD, normalised_path)} from a Fern atoms OpenAPI surface.

    Fern merges the main openapi.yaml with every override (`*-overrides.y*ml`,
    `*_override.y*ml`) sitting next to it. This function unions the
    `paths:` keys across all files in the same directory so a future
    override that ADDS an endpoint is captured (overrides today only
    tweak existing endpoints — SDK names, summaries, examples — but the
    pattern needs to stay aligned with Fern's read order).
    """
    found: set[tuple[str, str]] = set()
    spec_dir = spec_path.parent
    candidates = [spec_path]
    for ext in ("*.yaml", "*.yml"):
        for p in spec_dir.glob(ext):
            if p != spec_path:
                candidates.append(p)
    for p in candidates:
        try:
            with open(p) as f:
                spec = yaml.safe_load(f) or {}
        except (OSError, yaml.YAMLError):
            continue
        for path, ops in (spec.get("paths") or {}).items():
            if not isinstance(ops, dict):
                continue
            for method in ops:
                if method.lower() in ("get", "post", "put", "delete", "patch"):
                    found.add((method.upper(), normalise_path(path)))
    return found


def diff_sets(
    test_only: set[tuple[str, str]],
    spec_only: set[tuple[str, str]],
) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """Return (in_testautomation_only, in_openapi_only) sorted lists."""
    only_in_test = sorted(test_only - spec_only)
    only_in_spec = sorted(spec_only - test_only)
    return only_in_test, only_in_spec


def render_markdown(only_in_test: list, only_in_spec: list) -> str:
    if not only_in_test and not only_in_spec:
        return "✅ Atoms spec diff: testAutomation and Fern OpenAPI cover the same endpoints."
    lines = ["⚠️ **Atoms spec drift detected**", ""]
    if only_in_test:
        lines.append(
            f"### {len(only_in_test)} endpoint(s) in testAutomation but NOT in Fern OpenAPI"
        )
        lines.append("(undocumented — likely missing from SDK + docs)")
        lines.append("")
        for method, path in only_in_test:
            lines.append(f"- `{method:7s} /atoms/v1{path}`")
        lines.append("")
    if only_in_spec:
        lines.append(
            f"### {len(only_in_spec)} endpoint(s) in Fern OpenAPI but NOT in testAutomation"
        )
        lines.append(
            "(unverified — could be stale, pre-release, or admin-only — confirm before assuming drift)"
        )
        lines.append("")
        for method, path in only_in_spec:
            lines.append(f"- `{method:7s} /atoms/v1{path}`")
        lines.append("")
    lines.append("**Doc files to audit:**")
    lines.append("")
    lines.append("- `fern/apis/atoms/openapi/openapi.yaml`")
    lines.append("- `fern/apis/atoms/openapi/openapi-overrides.yaml`")
    lines.append("- `fern/products/atoms/pages/`")
    lines.append("- New changelog entry under `fern/products/atoms/pages/intro/reference/changelog-entries/`")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--testautomation",
        required=True,
        help="path to a local clone of smallest-inc/testAutomation",
    )
    parser.add_argument(
        "--openapi",
        default="fern/apis/atoms/openapi/openapi.yaml",
        help="path to the Fern atoms openapi.yaml",
    )
    parser.add_argument("--markdown", action="store_true")
    parser.add_argument(
        "--baseline",
        help="optional baseline JSON. If provided, exits 0 only when the "
             "current diff matches the baseline (so known drift can be "
             "acknowledged without spamming weekly).",
    )
    parser.add_argument(
        "--write-baseline",
        help="write the current diff state to this path and exit 0",
    )
    args = parser.parse_args()

    test_root = Path(args.testautomation)
    spec_path = Path(args.openapi)
    if not test_root.exists():
        print(f"testAutomation path not found: {test_root}", file=sys.stderr)
        return 2
    if not spec_path.exists():
        print(f"OpenAPI spec not found: {spec_path}", file=sys.stderr)
        return 2

    test_endpoints = extract_testautomation_endpoints(test_root)
    spec_endpoints = extract_openapi_endpoints(spec_path)
    only_in_test, only_in_spec = diff_sets(test_endpoints, spec_endpoints)

    state = {
        "schema_version": 1,
        "service": "atoms-spec-diff",
        "only_in_testautomation": [list(t) for t in only_in_test],
        "only_in_openapi": [list(t) for t in only_in_spec],
        "stats": {
            "testautomation_total": len(test_endpoints),
            "openapi_total": len(spec_endpoints),
            "only_in_testautomation": len(only_in_test),
            "only_in_openapi": len(only_in_spec),
        },
    }

    if args.write_baseline:
        Path(args.write_baseline).write_text(json.dumps(state, indent=2, sort_keys=True))
        print(f"Wrote baseline to {args.write_baseline}", file=sys.stderr)
        return 0

    # Compare against baseline if given — only fail if drift CHANGED.
    if args.baseline:
        baseline = json.loads(Path(args.baseline).read_text())
        b_test = {tuple(t) for t in baseline.get("only_in_testautomation", [])}
        b_spec = {tuple(t) for t in baseline.get("only_in_openapi", [])}
        c_test = set(map(tuple, state["only_in_testautomation"]))
        c_spec = set(map(tuple, state["only_in_openapi"]))
        new_drift_test = sorted(c_test - b_test)
        new_drift_spec = sorted(c_spec - b_spec)
        if not new_drift_test and not new_drift_spec:
            if args.markdown:
                print("✅ Atoms spec diff: no NEW drift since baseline.")
            return 0
        # Render only the new drift
        if args.markdown:
            print(render_markdown(new_drift_test, new_drift_spec))
        return 1

    if args.markdown:
        print(render_markdown(only_in_test, only_in_spec))
    else:
        print(json.dumps(state, indent=2, sort_keys=True))

    return 0 if (not only_in_test and not only_in_spec) else 1


if __name__ == "__main__":
    sys.exit(main())
