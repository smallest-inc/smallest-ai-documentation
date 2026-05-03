"""Audit MDX frontmatter for missing title / description fields.

`description` is what Fern surfaces in `llms.txt` as each page's
one-line summary, and what Ask Fern's RAG retriever weights heavily.
A page without a description is effectively invisible to the AI search.
This script walks v4 MDX and reports pages that need a `description:`
filled in.

Usage:
    python3 scripts/audit_frontmatter.py
    python3 scripts/audit_frontmatter.py --json
    python3 scripts/audit_frontmatter.py --fail-on-missing  # CI gate

Frozen versions (v2.2.0, v3.0.1) and the auto-generated
`api-references` directory are excluded — those have stable content
that we do not edit, and the API reference pages get descriptions from
their OpenAPI/AsyncAPI source.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

SCAN_PATHS = [
    REPO_ROOT / "fern" / "products" / "atoms" / "pages",
    REPO_ROOT / "fern" / "products" / "waves" / "pages" / "v4.0.0",
    REPO_ROOT / "fern" / "products" / "waves" / "versions" / "v4.0.0",
]

# Skip categories that don't benefit from a description (auto-rendered
# from spec, or content type where description doesn't apply).
SKIP_DIR_NAMES = {
    "api-references",
    "changelog-entries",
}

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)


def parse_frontmatter(text: str) -> dict[str, str]:
    """Tiny YAML-ish parser for frontmatter — handles only top-level
    string keys, which is all our MDX uses. Avoids pulling pyyaml as a
    runtime dep for a 30-line script."""
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}
    fields: dict[str, str] = {}
    for line in m.group(1).splitlines():
        line = line.rstrip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip().strip("'\"")
    return fields


def should_skip(path: Path) -> bool:
    return any(part in SKIP_DIR_NAMES for part in path.parts)


def audit() -> tuple[list[dict], list[dict]]:
    """Return (pages_missing_description, pages_missing_title)."""
    missing_desc: list[dict] = []
    missing_title: list[dict] = []
    for root in SCAN_PATHS:
        if not root.exists():
            continue
        for path in root.rglob("*.mdx"):
            if should_skip(path):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            fm = parse_frontmatter(text)
            rel = str(path.relative_to(REPO_ROOT))
            if not fm.get("description"):
                missing_desc.append({"path": rel, "title": fm.get("title", "")})
            if not fm.get("title"):
                missing_title.append({"path": rel})
    return missing_desc, missing_title


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-on-missing", action="store_true")
    args = parser.parse_args()

    missing_desc, missing_title = audit()

    if args.json:
        print(json.dumps({
            "missing_description": missing_desc,
            "missing_title": missing_title,
        }, indent=2))
    else:
        print(f"Pages missing `title`: {len(missing_title)}")
        for r in missing_title[:50]:
            print(f"  - {r['path']}")
        print()
        print(f"Pages missing `description`: {len(missing_desc)}")
        for r in missing_desc[:50]:
            t = r["title"] or "(no title)"
            print(f"  - {r['path']}  [{t}]")
        if len(missing_desc) > 50:
            print(f"  ... and {len(missing_desc) - 50} more")

    if args.fail_on_missing and (missing_desc or missing_title):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
