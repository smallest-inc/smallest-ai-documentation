#!/usr/bin/env python3
"""
Append <CodingAgentCallout /> to every eligible page MDX under
`fern/products/{atoms,waves}/pages/`, `fern/pages/`, and `fern/ai-tools/`.

Idempotent: each injected page carries a `{/* coding-agent-callout-injected */}`
sentinel, and this script only touches files without it. Re-running is safe.

Exclusions:
  - `changelog-entries/**` (dated ephemera, would show 260+ times on the tab)
  - `api-reference/**` (rendered from OpenAPI/AsyncAPI; not user-authored prose)
  - The Build-with-a-coding-agent page itself (self-referential).

CI counterpart is `.github/workflows/agent-callout-present.yml`, which fails
any PR that adds or edits an eligible MDX without the sentinel. Fix by
re-running this script.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parent.parent
PAGES_ROOTS = [
    REPO_ROOT / "fern" / "products" / "atoms" / "pages",
    REPO_ROOT / "fern" / "products" / "waves" / "pages",
    REPO_ROOT / "fern" / "pages",
    REPO_ROOT / "fern" / "ai-tools",
]

EXCLUDE_PATTERNS = (
    "changelog-entries",
    "/api-reference/",
    "/openapi/",
    "/asyncapi/",
    "build-with-coding-agent.mdx",
)

SENTINEL = "{/* coding-agent-callout-injected */}"
IMPORT_LINE = 'import { CodingAgentCallout } from "@/components/CodingAgentCallout";'
CALLOUT_LINE = "<CodingAgentCallout />"

FRONTMATTER_RE = re.compile(r"\A(---\s*\n.*?\n---\s*\n)", re.DOTALL)


def is_excluded(path: Path) -> bool:
    p = str(path.as_posix())
    return any(pat in p for pat in EXCLUDE_PATTERNS)


def already_injected(text: str) -> bool:
    return SENTINEL in text


def find_target_files() -> Iterable[Path]:
    for root in PAGES_ROOTS:
        if not root.exists():
            continue
        for mdx in sorted(root.rglob("*.mdx")):
            if is_excluded(mdx):
                continue
            yield mdx


def inject(text: str) -> str:
    """Return the new file contents with the callout appended.

    Places the import block right after the frontmatter (or at file start if
    none), and appends the component call + sentinel at the very end.
    """
    m = FRONTMATTER_RE.match(text)
    if m:
        head, body = m.group(1), text[m.end():]
    else:
        head, body = "", text

    # Insert import once if not present. Standalone paragraph with blank
    # line on either side so it does not fuse with adjacent content.
    if IMPORT_LINE not in body:
        # Strip leading blank lines from body so we control the spacing.
        body = body.lstrip("\n")
        body_prefix = f"\n{IMPORT_LINE}\n\n"
    else:
        body_prefix = ""

    # Append callout + sentinel at end.
    body_rstripped = body.rstrip() + "\n"
    body_suffix = f"\n{CALLOUT_LINE}\n\n{SENTINEL}\n"

    return head + body_prefix + body_rstripped + body_suffix


def check(paths: Iterable[Path]) -> tuple[int, list[Path]]:
    """Return (total, missing) for a --check pass. Missing = eligible files
    without the sentinel."""
    total = 0
    missing: list[Path] = []
    for p in paths:
        total += 1
        text = p.read_text(encoding="utf-8", errors="replace")
        if not already_injected(text):
            missing.append(p)
    return total, missing


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--check",
        action="store_true",
        help="do not write; exit 1 if any eligible MDX is missing the callout",
    )
    ap.add_argument(
        "--paths",
        nargs="+",
        type=Path,
        help="restrict to these files (used by CI to check only what a PR changed)",
    )
    args = ap.parse_args()

    if args.paths:
        # In check mode with explicit paths (CI: touched files in the PR).
        # Filter through the same exclusion rules so a PR that legitimately
        # touches a changelog entry is not spuriously failed.
        files = [
            p.resolve()
            for p in args.paths
            if p.suffix == ".mdx" and not is_excluded(p) and p.exists()
        ]
    else:
        files = list(find_target_files())

    if args.check:
        total, missing = check(files)
        if missing:
            print(f"Missing callout in {len(missing)} of {total} eligible MDX files:")
            for p in missing:
                try:
                    rel = p.resolve().relative_to(REPO_ROOT)
                except ValueError:
                    rel = p
                print(f"  {rel}")
            print()
            print("Fix locally:  python3 scripts/inject_agent_callout.py")
            return 1
        print(f"All {total} eligible MDX files carry the callout sentinel.")
        return 0

    changed = 0
    for path in files:
        text = path.read_text(encoding="utf-8", errors="replace")
        if already_injected(text):
            continue
        path.write_text(inject(text), encoding="utf-8")
        changed += 1

    print(f"Injected callout into {changed} MDX files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
