#!/usr/bin/env python3
"""
Contract diff probe — docs spec vs platform contract.

Fetches the latest API-contract release from waves-platform
(or reads a local manifest directory for tests/CI), compares each
platform schema against the corresponding docs spec file under
`fern/apis/waves/`, and reports drift:

  - MISSING_IN_DOCS — platform supports param X, docs don't declare it
                      (regression class that PR #187 introduced)
  - EXTRA_IN_DOCS  — docs declare param Y, platform doesn't validate it
                     (either docs is wrong, or platform deprecated it)
  - DELETION       — this PR removes a param that's on main
                     (catches accidental removals during a refactor)

Modes:

  - Per-PR (default): compare the PR branch's docs spec against the
    platform manifest, AND against the same files on `origin/main` to
    detect deletions introduced by this PR.

  - Scheduled (--scope=cron): compare main's docs spec against the
    platform manifest. Surfaces drift that doesn't have a docs PR
    in flight to fix it.

Strict mode (--strict) exits 1 on any MISSING_IN_DOCS or DELETION;
advisory mode (default) always exits 0 — the workflow comments on the
PR but doesn't fail it.

Manifest source:

  --manifest-dir LOCAL_DIR   — read pre-downloaded manifests (used by
                              tests + by the workflow after the asset
                              download step).
  --fetch-from-release       — fetch the latest contract-* release from
                              smallest-inc/waves-platform via GH API.
                              Requires `gh` on PATH and a token with
                              waves-platform read access.

The platform schema → docs spec mapping lives in CONTRACT_MAPPINGS
below. Adding a new model = adding a row.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

try:
    import yaml
except ImportError:
    print("ERROR: pyyaml not installed. Run `pip install pyyaml`.", file=sys.stderr)
    sys.exit(2)


REPO_ROOT = Path(__file__).resolve().parents[2]


# =============================================================================
# Mapping config — which platform schema maps to which docs spec location.
# Each mapping captures: surface name, schema name in the manifest, docs file,
# and a "selector" that tells the docs-spec reader where to find the property
# bag inside the file.
# =============================================================================

@dataclass(frozen=True)
class Mapping:
    """One pairing of a platform schema to a docs spec property bag."""
    surface: str
    platform_schema: str
    docs_file: str
    # selector kind: "openapi-op-params" | "openapi-op-body" |
    #                "asyncapi-server-query" | "asyncapi-channel-params" |
    #                "asyncapi-message-payload"
    selector_kind: str
    # selector args — meaning varies by kind. Documented inline at the readers.
    selector: tuple[str, ...]
    # Optional list of param names the platform schema has that we deliberately
    # don't expect in docs (e.g., internal webhook bookkeeping for WS surfaces).
    ignore_platform: frozenset[str] = field(default_factory=frozenset)


CONTRACT_MAPPINGS: list[Mapping] = [
    # STT — Pulse REST (unified endpoint POST /waves/v1/stt/)
    Mapping(
        surface="stt",
        platform_schema="lightningAsrQuerySchema",
        docs_file="fern/apis/waves/openapi/stt-openapi.yaml",
        selector_kind="openapi-op-params",
        selector=("transcribe",),  # operationId
    ),
    # STT — Pulse WebSocket (WSS /waves/v1/stt/live)
    Mapping(
        surface="stt",
        platform_schema="lightningAsrWebsocketQuerySchema",
        docs_file="fern/apis/waves/asyncapi/stt-live-ws.yaml",
        selector_kind="asyncapi-server-query",
        selector=("production",),  # server name
        # Platform inherits webhook_* via .extend() but they don't apply on
        # a live socket — already filtered upstream in the platform parser's
        # ignore list, but we ALSO filter here for defensive reasons.
        ignore_platform=frozenset(["webhook_url", "webhook_method", "webhook_extra"]),
    ),
    # TTS — unified REST (POST /waves/v1/tts) — same schema used by both
    # the unified and legacy `/lightning-v3.1/get_speech` routes.
    Mapping(
        surface="tts",
        platform_schema="lightningV3_1Schema",
        docs_file="fern/apis/waves/openapi/tts-openapi.yaml",
        selector_kind="openapi-op-body",
        selector=("synthesizeSpeech",),  # operationId
    ),
    # TTS — unified WebSocket
    Mapping(
        surface="tts",
        platform_schema="lightningV3_1WebSocketSchema",
        docs_file="fern/apis/waves/asyncapi/tts-ws.yaml",
        selector_kind="asyncapi-message-payload",
        selector=("ttsStream", "ttsRequest.message"),  # channel name, message key
    ),
    # LLM — Electron chat completions
    Mapping(
        surface="llm",
        platform_schema="llmChatCompletionSchema",
        docs_file="fern/apis/waves/openapi/electron-openapi.yaml",
        selector_kind="openapi-op-body",
        selector=("electronChatCompletions",),
    ),
    # S2S — Hydra connect query only (per coverage_note in the manifest)
    Mapping(
        surface="s2s",
        platform_schema="s2sQuerySchema",
        docs_file="fern/apis/waves/asyncapi/hydra-ws.yaml",
        selector_kind="asyncapi-server-query",
        selector=("production",),
    ),
]


# =============================================================================
# Manifest loading
# =============================================================================

def load_manifests(manifest_dir: Path) -> dict[str, dict]:
    """Read each <surface>.json under manifest_dir.

    Returns: { surface_name: manifest_dict }
    """
    manifests: dict[str, dict] = {}
    if not manifest_dir.exists():
        raise SystemExit(f"manifest dir not found: {manifest_dir}")
    for path in sorted(manifest_dir.glob("*.json")):
        with path.open() as f:
            doc = json.load(f)
        surface = doc.get("surface")
        if surface:
            manifests[surface] = doc
    return manifests


# =============================================================================
# Docs spec property readers
# =============================================================================

def _load_yaml(path: Path) -> dict | None:
    """Load YAML, returning None if the file doesn't exist."""
    if not path.exists():
        return None
    with path.open() as f:
        return yaml.safe_load(f)


def read_openapi_op_params(doc: dict, operation_id: str) -> set[str]:
    """Query parameters declared on a specific OpenAPI operation."""
    for path_obj in (doc.get("paths") or {}).values():
        if not isinstance(path_obj, dict):
            continue
        for method_obj in path_obj.values():
            if not isinstance(method_obj, dict):
                continue
            if method_obj.get("operationId") != operation_id:
                continue
            params = method_obj.get("parameters", []) or []
            return {p["name"] for p in params if isinstance(p, dict) and p.get("in") == "query"}
    return set()


def read_openapi_op_body(doc: dict, operation_id: str) -> set[str]:
    """Request-body JSON-schema property names on a specific OpenAPI operation.

    Resolves a single `$ref` into `#/components/schemas/<X>` (the only
    indirection style our specs currently use). Inline schemas are read as-is.
    """
    for path_obj in (doc.get("paths") or {}).values():
        if not isinstance(path_obj, dict):
            continue
        for method_obj in path_obj.values():
            if not isinstance(method_obj, dict):
                continue
            if method_obj.get("operationId") != operation_id:
                continue
            body = method_obj.get("requestBody") or {}
            content = body.get("content") or {}
            schema = (content.get("application/json") or {}).get("schema") or {}
            return _resolve_schema_properties(schema, doc).keys() | set()
    return set()


def _resolve_schema_properties(schema: dict, root: dict) -> dict:
    """If schema is a $ref, follow it; then return its `properties` dict."""
    while isinstance(schema, dict) and "$ref" in schema:
        ref = schema["$ref"]
        # Only support local refs `#/components/schemas/X`.
        if not ref.startswith("#/"):
            return {}
        cur: dict | list = root
        for part in ref.lstrip("#/").split("/"):
            if isinstance(cur, dict):
                cur = cur.get(part)  # type: ignore[assignment]
            else:
                return {}
            if cur is None:
                return {}
        schema = cur if isinstance(cur, dict) else {}
    if not isinstance(schema, dict):
        return {}
    return schema.get("properties") or {}


def read_asyncapi_server_query(doc: dict, server_name: str) -> set[str]:
    """WebSocket connect-query property names on an AsyncAPI server."""
    server = (doc.get("servers") or {}).get(server_name)
    if not isinstance(server, dict):
        return set()
    try:
        props = server["bindings"]["ws"]["query"]["properties"]
    except (KeyError, TypeError):
        return set()
    return set(props.keys()) if isinstance(props, dict) else set()


def read_asyncapi_channel_params(doc: dict, channel_name: str) -> set[str]:
    """Channel-level `parameters` block (Fern's v4 docs override convention)."""
    channel = (doc.get("channels") or {}).get(channel_name)
    if not isinstance(channel, dict):
        return set()
    params = channel.get("parameters")
    return set(params.keys()) if isinstance(params, dict) else set()


def read_asyncapi_message_payload(doc: dict, channel_name: str, message_key: str) -> set[str]:
    """Property names of a specific WS message's payload."""
    channel = (doc.get("channels") or {}).get(channel_name)
    if not isinstance(channel, dict):
        return set()
    msg = (channel.get("messages") or {}).get(message_key)
    if not isinstance(msg, dict):
        return set()
    payload = msg.get("payload") or {}
    if not isinstance(payload, dict):
        return set()
    props = payload.get("properties")
    return set(props.keys()) if isinstance(props, dict) else set()


def docs_param_set(mapping: Mapping, repo_root: Path) -> set[str] | None:
    """Apply a Mapping to a docs spec and return the param set.
    Returns None when the docs file or selector target doesn't exist."""
    path = repo_root / mapping.docs_file
    doc = _load_yaml(path)
    if doc is None:
        return None
    kind = mapping.selector_kind
    if kind == "openapi-op-params":
        return read_openapi_op_params(doc, mapping.selector[0])
    if kind == "openapi-op-body":
        return read_openapi_op_body(doc, mapping.selector[0])
    if kind == "asyncapi-server-query":
        return read_asyncapi_server_query(doc, mapping.selector[0])
    if kind == "asyncapi-channel-params":
        return read_asyncapi_channel_params(doc, mapping.selector[0])
    if kind == "asyncapi-message-payload":
        return read_asyncapi_message_payload(doc, mapping.selector[0], mapping.selector[1])
    return None


# =============================================================================
# Platform schema reader
# =============================================================================

def platform_param_set(manifest: dict, schema_name: str, ignore: frozenset[str]) -> set[str] | None:
    """Read property names from a specific schema in a manifest."""
    schemas = manifest.get("schemas") or {}
    schema = schemas.get(schema_name)
    if not isinstance(schema, dict):
        return None
    props = schema.get("properties") or {}
    return set(props.keys()) - ignore


def platform_is_passthrough(manifest: dict, schema_name: str) -> bool:
    """True when the platform schema accepts undeclared fields via .passthrough().

    Used to suppress 'extra in docs' findings — docs legitimately document
    OpenAI-compatible fields that pass through (e.g., Electron's
    temperature, top_p, etc.) even though Zod doesn't enumerate them.
    """
    schema = (manifest.get("schemas") or {}).get(schema_name)
    if not isinstance(schema, dict):
        return False
    return schema.get("additionalProperties") == "passthrough"


# =============================================================================
# Diff + report
# =============================================================================

@dataclass
class MappingReport:
    mapping: Mapping
    missing_in_docs: list[str]
    extra_in_docs: list[str]
    docs_present: bool
    platform_present: bool

    def is_clean(self) -> bool:
        return self.docs_present and self.platform_present and not self.missing_in_docs and not self.extra_in_docs


@dataclass
class DeletionReport:
    """A param removed from the docs spec on this PR vs `--baseline-ref`."""
    docs_file: str
    selector_kind: str
    selector: tuple[str, ...]
    deleted: list[str]


def diff_mapping(mapping: Mapping, manifest: dict, repo_root: Path) -> MappingReport:
    plat = platform_param_set(manifest, mapping.platform_schema, mapping.ignore_platform)
    docs = docs_param_set(mapping, repo_root)
    missing = sorted((plat or set()) - (docs or set()))
    # When the platform schema is passthrough, docs are EXPECTED to declare
    # additional fields the platform forwards but doesn't validate. Suppress
    # the 'extra in docs' finding so it doesn't drown out real issues.
    if platform_is_passthrough(manifest, mapping.platform_schema):
        extras: list[str] = []
    else:
        extras = sorted((docs or set()) - (plat or set()))
    return MappingReport(
        mapping=mapping,
        missing_in_docs=missing,
        extra_in_docs=extras,
        docs_present=docs is not None,
        platform_present=plat is not None,
    )


def read_docs_param_set_at_ref(mapping: Mapping, repo_root: Path, ref: str) -> set[str] | None:
    """Read the docs param set from a git-historic version of the file."""
    try:
        blob = subprocess.check_output(
            ["git", "-C", str(repo_root), "show", f"{ref}:{mapping.docs_file}"],
            stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError:
        return None
    doc = yaml.safe_load(blob)
    if doc is None:
        return None
    kind = mapping.selector_kind
    if kind == "openapi-op-params":
        return read_openapi_op_params(doc, mapping.selector[0])
    if kind == "openapi-op-body":
        return read_openapi_op_body(doc, mapping.selector[0])
    if kind == "asyncapi-server-query":
        return read_asyncapi_server_query(doc, mapping.selector[0])
    if kind == "asyncapi-channel-params":
        return read_asyncapi_channel_params(doc, mapping.selector[0])
    if kind == "asyncapi-message-payload":
        return read_asyncapi_message_payload(doc, mapping.selector[0], mapping.selector[1])
    return None


def find_deletions(mapping: Mapping, repo_root: Path, baseline_ref: str) -> DeletionReport | None:
    """Compare the current docs spec against `baseline_ref`. Reports any
    param that's on baseline but not on the current branch."""
    baseline = read_docs_param_set_at_ref(mapping, repo_root, baseline_ref)
    current = docs_param_set(mapping, repo_root)
    if baseline is None or current is None:
        return None
    deleted = sorted(baseline - current)
    if not deleted:
        return None
    return DeletionReport(
        docs_file=mapping.docs_file,
        selector_kind=mapping.selector_kind,
        selector=mapping.selector,
        deleted=deleted,
    )


# =============================================================================
# Report rendering
# =============================================================================

def render_text(reports: list[MappingReport], deletions: list[DeletionReport], manifests: dict[str, dict]) -> str:
    lines: list[str] = []
    lines.append("=" * 78)
    lines.append("Docs spec vs platform contract")
    lines.append("=" * 78)
    for surface, m in sorted(manifests.items()):
        commit = m.get("platform_commit", "?")
        note = m.get("coverage_note")
        lines.append(f"  {surface}: platform_commit={commit}")
        if note:
            lines.append(f"     ⓘ {note}")
    lines.append("")
    n_missing = sum(len(r.missing_in_docs) for r in reports)
    n_extra = sum(len(r.extra_in_docs) for r in reports)
    n_deletions = sum(len(d.deleted) for d in deletions)

    for r in reports:
        lines.append(f"## [{r.mapping.surface.upper()} / {r.mapping.platform_schema}]")
        lines.append(f"   docs: {r.mapping.docs_file}  ({r.mapping.selector_kind} {' '.join(r.mapping.selector)})")
        if not r.platform_present:
            lines.append(f"   ⚠ platform schema not in manifest — mapping is stale")
        if not r.docs_present:
            lines.append(f"   ⚠ docs file not found — mapping target moved or deleted")
        if r.missing_in_docs:
            lines.append(f"   ❌ MISSING IN DOCS ({len(r.missing_in_docs)}):")
            for n in r.missing_in_docs:
                lines.append(f"       - {n}")
        if r.extra_in_docs:
            lines.append(f"   ℹ️  EXTRA IN DOCS ({len(r.extra_in_docs)}):")
            for n in r.extra_in_docs:
                lines.append(f"       - {n}")
        if r.is_clean():
            lines.append("   ✅ in sync")
        lines.append("")

    if deletions:
        lines.append("=" * 78)
        lines.append("🚨 DELETIONS (this PR removes docs spec entries that exist on baseline)")
        lines.append("=" * 78)
        for d in deletions:
            lines.append(f"\n  {d.docs_file}")
            for n in d.deleted:
                lines.append(f"     - {n}")
        lines.append("")

    lines.append("=" * 78)
    if n_missing == 0 and n_deletions == 0:
        lines.append(f"PASS — no missing platform params, no deletions"
                     + (f" (info: {n_extra} extra in docs)" if n_extra else ""))
    else:
        lines.append(f"FINDINGS — {n_missing} missing in docs, {n_deletions} deletions, {n_extra} extras")
    lines.append("=" * 78)
    return "\n".join(lines)


def render_markdown(reports: list[MappingReport], deletions: list[DeletionReport], manifests: dict[str, dict]) -> str:
    """PR-comment friendly Markdown."""
    blocks: list[str] = []
    blocks.append("<!-- contract-diff-probe -->")
    blocks.append("## Contract diff (docs ↔ platform)")
    blocks.append("")
    # Per-surface platform commit + coverage note
    blocks.append("**Platform manifest:**")
    for surface, m in sorted(manifests.items()):
        commit = m.get("platform_commit", "?")
        line = f"- `{surface}` — commit `{commit}`"
        if m.get("coverage_note"):
            line += f" — _{m['coverage_note']}_"
        blocks.append(line)
    blocks.append("")
    n_missing = sum(len(r.missing_in_docs) for r in reports)
    n_extra = sum(len(r.extra_in_docs) for r in reports)
    n_deletions = sum(len(d.deleted) for d in deletions)

    if deletions:
        blocks.append("### 🚨 Deletions on this PR")
        blocks.append("")
        blocks.append("This PR removes the following params from the docs spec that exist on baseline:")
        blocks.append("")
        for d in deletions:
            blocks.append(f"- `{d.docs_file}` — `" + "`, `".join(d.deleted) + "`")
        blocks.append("")
        blocks.append("_If intentional, add a label `acknowledged-spec-deletion` to this PR. If accidental, restore the entries._")
        blocks.append("")

    if n_missing or n_extra:
        blocks.append("### Drift findings")
        blocks.append("")
        for r in reports:
            if r.is_clean():
                continue
            head = f"**`{r.mapping.surface}` / `{r.mapping.platform_schema}`** → `{r.mapping.docs_file}`"
            blocks.append(head)
            if r.missing_in_docs:
                blocks.append("- ❌ Platform supports, docs missing: `" + "`, `".join(r.missing_in_docs) + "`")
            if r.extra_in_docs:
                blocks.append("- ℹ️ Docs declares, platform doesn't: `" + "`, `".join(r.extra_in_docs) + "`")
            blocks.append("")
    elif not deletions:
        blocks.append("### ✅ In sync")
        blocks.append("")
        blocks.append("Every mapped platform schema matches the docs spec. No drift, no deletions.")
        blocks.append("")
    return "\n".join(blocks)


# =============================================================================
# CLI
# =============================================================================

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest-dir",
        type=Path,
        help="Local directory containing per-surface JSON manifests "
        "(stt.json, tts.json, llm.json, s2s.json).",
    )
    parser.add_argument(
        "--baseline-ref",
        type=str,
        default=None,
        help="Git ref to diff the docs spec against, for deletion detection. "
        "Defaults to none (skip the deletion check). In CI for PRs, set to "
        "`origin/main`.",
    )
    parser.add_argument(
        "--mode",
        choices=["advisory", "strict"],
        default="advisory",
    )
    parser.add_argument(
        "--out-markdown",
        type=Path,
        help="If set, write the Markdown report to this path (for PR comment).",
    )
    args = parser.parse_args(argv)

    if not args.manifest_dir:
        raise SystemExit("--manifest-dir is required for now. Use a local dir or download release assets first.")
    manifests = load_manifests(args.manifest_dir)
    if not manifests:
        raise SystemExit("no manifests found in --manifest-dir")

    reports: list[MappingReport] = []
    for mapping in CONTRACT_MAPPINGS:
        manifest = manifests.get(mapping.surface)
        if manifest is None:
            continue
        reports.append(diff_mapping(mapping, manifest, REPO_ROOT))

    deletions: list[DeletionReport] = []
    if args.baseline_ref:
        for mapping in CONTRACT_MAPPINGS:
            d = find_deletions(mapping, REPO_ROOT, args.baseline_ref)
            if d:
                deletions.append(d)

    print(render_text(reports, deletions, manifests))

    if args.out_markdown:
        args.out_markdown.write_text(render_markdown(reports, deletions, manifests) + "\n")

    n_missing = sum(len(r.missing_in_docs) for r in reports)
    n_deletions = sum(len(d.deleted) for d in deletions)
    if args.mode == "strict" and (n_missing or n_deletions):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
