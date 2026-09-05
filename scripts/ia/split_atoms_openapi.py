#!/usr/bin/env python3
"""
Split a monolithic atoms OpenAPI file into one file per domain, byte for byte.

The splitter works on the raw YAML text, not on a parsed tree, so nothing is
re-serialised: descriptions, examples, quoting, and YAML 1.1 edge cases such
as the string `on` survive untouched. Each output file keeps its paths in the
original order and points every `#/components/...` reference at the shared
components.yaml through an external `$ref`. Fern merges every file registered
under the same namespace in generators.yml into one API, and SDK grouping
comes from tags, so the generated SDK surface does not change. Prove it with
`fern ir` before and after (see CONTRIBUTING.md, "Spec files").

Usage:
  python3 scripts/ia/split_atoms_openapi.py --source path/to/openapi.yaml
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = REPO_ROOT / "fern/apis/atoms/openapi"
COMPONENTS_FILE = "components.yaml"

# Domain file -> tags that belong in it. Order = order in generators.yml.
GROUPS: dict[str, list[str]] = {
    "agents": ["Agents", "Agent Templates", "Widget", "Web Call", "Realtime Agent", "Prompt Scoring"],
    "agent-versioning": ["Agent Versioning - Branches", "Agent Versioning - Revisions",
                         "Agent Versioning - Drafts", "Agent Versioning - Versions"],
    "calls": ["Calls", "Conversations", "Logs", "Call Actions", "Live Transcripts",
              "Post-Call Analytics", "Disposition Metric Templates"],
    "campaigns": ["Campaigns", "Audience", "DNC"],
    "phone-numbers": ["Phone Numbers", "Compliance"],
    "knowledge-base": ["Knowledge Base"],
    "tools": ["Tools", "Secrets", "Integrations"],
    "webhooks": ["Webhooks"],
    "analytics": ["Analytics"],
    "account": ["User", "Account", "Billing", "Concurrency"],
}
TITLES = {
    "agents": "Voice Agents API: Agents",
    "agent-versioning": "Voice Agents API: Agent Versioning",
    "calls": "Voice Agents API: Calls and Conversations",
    "campaigns": "Voice Agents API: Campaigns and Audiences",
    "phone-numbers": "Voice Agents API: Phone Numbers and Compliance",
    "knowledge-base": "Voice Agents API: Knowledge Base",
    "tools": "Voice Agents API: Tools, Secrets, and Integrations",
    "webhooks": "Voice Agents API: Webhooks",
    "analytics": "Voice Agents API: Analytics",
    "account": "Voice Agents API: Account, Billing, and Concurrency",
}
METHODS = ("get", "post", "put", "patch", "delete", "head", "options")
REF_RE = re.compile(r"(\$ref:\s*['\"]?)#/components/")


def top_level_blocks(lines: list[str]) -> dict[str, tuple[int, int]]:
    """Map each column-0 key to its [start, end) line range."""
    starts = [(i, l.split(":", 1)[0]) for i, l in enumerate(lines) if re.match(r"^[A-Za-z][\w-]*:", l)]
    blocks = {}
    for n, (i, key) in enumerate(starts):
        end = starts[n + 1][0] if n + 1 < len(starts) else len(lines)
        blocks[key] = (i, end)
    return blocks


def child_blocks(lines: list[str], start: int, end: int, indent: int, key_re: str) -> list[tuple[str, int, int]]:
    """Slice a block into its children at a given indent whose key matches key_re."""
    pat = re.compile(rf"^ {{{indent}}}({key_re})")
    idx = [(i, pat.match(lines[i]).group(1)) for i in range(start, end) if pat.match(lines[i])]
    out = []
    for n, (i, key) in enumerate(idx):
        e = idx[n + 1][0] if n + 1 < len(idx) else end
        out.append((key, i, e))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    args = ap.parse_args()
    text = Path(args.source).read_text(encoding="utf-8")
    lines = text.split("\n")
    blocks = top_level_blocks(lines)
    for k in ("openapi", "info", "paths", "components"):
        if k not in blocks:
            sys.exit(f"missing top-level `{k}:` block")

    # ---- paths: slice per path key (2-space indent, starts with /)
    ps, pe = blocks["paths"]
    path_blocks = child_blocks(lines, ps + 1, pe, 2, r"/\S+(?=:)")
    tag2file = {t: f for f, ts in GROUPS.items() for t in ts}
    buckets: dict[str, list[str]] = {f: [] for f in GROUPS}
    used_tags: dict[str, list[str]] = {f: [] for f in GROUPS}
    for key, s, e in path_blocks:
        raw = "\n".join(lines[s:e]).rstrip("\n")
        parsed = yaml.safe_load(raw)  # read-only, only to find tags
        ops = parsed[key]
        tags = {op.get("tags", [None])[0] for m, op in ops.items() if m in METHODS}
        files = {tag2file.get(t) for t in tags}
        if None in files or len(files) != 1:
            sys.exit(f"cannot assign {key}: tags {sorted(tags, key=str)} span {files}")
        f = files.pop()
        buckets[f].append(REF_RE.sub(rf"\g<1>./{COMPONENTS_FILE}#/components/", raw))
        for m, op in ops.items():
            if m in METHODS:
                for t in op.get("tags", []):
                    if t not in used_tags[f]:
                        used_tags[f].append(t)

    # ---- shared header pieces (verbatim)
    def block_text(key: str) -> str:
        s, e = blocks[key]
        return "\n".join(lines[s:e]).rstrip("\n")

    openapi_line = block_text("openapi")
    info = yaml.safe_load(block_text("info"))
    version = info.get("version", "1.0.0")
    servers = block_text("servers") if "servers" in blocks else ""

    # components: keep securitySchemes verbatim in every file (operations
    # reference the scheme by name), everything else goes to components.yaml
    cs, ce = blocks["components"]
    comp_children = child_blocks(lines, cs + 1, ce, 2, r"[A-Za-z]+(?=:)")
    security_raw = ""
    for key, s, e in comp_children:
        if key == "securitySchemes":
            security_raw = "\n".join(lines[s:e]).rstrip("\n")

    # root tags: keep each `- name:` item verbatim
    tag_items: dict[str, str] = {}
    if "tags" in blocks:
        ts, te = blocks["tags"]
        for key, s, e in child_blocks(lines, ts + 1, te, 2, r"- name:"):
            raw = "\n".join(lines[s:e]).rstrip("\n")
            name = yaml.safe_load(raw)[0]["name"]
            tag_items[name] = raw

    written = []
    for fname, paths in buckets.items():
        if not paths:
            continue
        out = [openapi_line,
               "info:",
               f"  title: \"{TITLES[fname]}\"",
               f"  version: {version}",
               f"  description: \"Part of the Voice Agents (Atoms) API. Shared schemas live in {COMPONENTS_FILE}.\""]
        if servers:
            out.append(servers)
        out.append("paths:")
        out.extend(paths)
        out.append("components:")
        out.append(security_raw)
        tags_raw = [tag_items[t] for t in used_tags[fname] if t in tag_items]
        if tags_raw:
            out.append("tags:")
            out.extend(tags_raw)
        target = OUT_DIR / f"{fname}.yaml"
        target.write_text("\n".join(out) + "\n", encoding="utf-8")
        written.append((target, len(paths)))

    comp_out = [openapi_line,
                "info:",
                "  title: \"Voice Agents API shared components\"",
                f"  version: {version}",
                "  description: \"Shared schemas, parameters, and responses referenced by every domain file in this folder.\"",
                "paths: {}",
                "\n".join(lines[cs:ce]).rstrip("\n")]
    (OUT_DIR / COMPONENTS_FILE).write_text("\n".join(comp_out) + "\n", encoding="utf-8")

    for target, n in written:
        print(f"{target.relative_to(REPO_ROOT)}: {n} paths")
    print(f"{(OUT_DIR / COMPONENTS_FILE).relative_to(REPO_ROOT)}: components block copied verbatim")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
