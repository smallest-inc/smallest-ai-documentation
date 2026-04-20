#!/usr/bin/env python3
"""
Verify every page-MDX file is registered in a Fern nav config, and every nav
entry points to a file that actually exists.

Runs in CI on every PR. Catches two classes of bugs:
  1. Orphaned MDX pages — exist in pages/ but missing from nav. Fern skips
     them, so any link pointing at them 404s. This is exactly what happened
     with tts-evaluation.mdx (reported by Yash, fixed in PR #49).
  2. Dangling nav entries — nav points at an MDX path that no longer exists
     (renamed/deleted without updating nav). Fern build errors on these, but
     running it locally to catch is a slow feedback loop.

Intentionally-unlisted pages (partials, snippets, work-in-progress) can be
allow-listed in scripts/.nav-ignore.
"""
from __future__ import annotations

import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("PyYAML is required. Install with: pip install pyyaml", file=sys.stderr)
    sys.exit(2)

REPO_ROOT = Path(__file__).resolve().parent.parent
NAV_IGNORE_FILE = REPO_ROOT / "scripts" / ".nav-ignore"

# Nav YAML files to scan. Ordered — the first file defines its own search root.
NAV_CONFIGS = [
    REPO_ROOT / "fern" / "products" / "atoms.yml",
    REPO_ROOT / "fern" / "products" / "waves" / "versions" / "v4.0.0.yml",
    REPO_ROOT / "fern" / "products" / "waves" / "versions" / "v3.0.1.yml",
    REPO_ROOT / "fern" / "products" / "waves" / "versions" / "v2.2.0.yml",
]

# Directories that contain customer-facing pages. Every .mdx in here must be
# reachable from at least one nav config (unless allow-listed).
PAGE_ROOTS = [
    REPO_ROOT / "fern" / "products" / "atoms" / "pages",
    REPO_ROOT / "fern" / "products" / "waves" / "pages",
]


def load_ignore_list() -> set[Path]:
    """Read .nav-ignore. One path per line, relative to repo root. # comments ok."""
    if not NAV_IGNORE_FILE.exists():
        return set()
    ignored: set[Path] = set()
    for raw in NAV_IGNORE_FILE.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        ignored.add((REPO_ROOT / line).resolve())
    return ignored


def extract_mdx_paths_from_nav(nav_file: Path) -> set[Path]:
    """Walk a Fern nav YAML and return every .mdx path resolved to absolute.

    Nav entries look like:
        - page: Foo
          path: ../pages/foo.mdx

    Paths are resolved relative to the YAML file's own directory.
    """
    if not nav_file.exists():
        return set()

    with nav_file.open() as f:
        data = yaml.safe_load(f)

    base_dir = nav_file.parent
    paths: set[Path] = set()

    def walk(node):
        if isinstance(node, dict):
            if "path" in node and isinstance(node["path"], str) and node["path"].endswith(".mdx"):
                paths.add((base_dir / node["path"]).resolve())
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(data)
    return paths


def list_all_mdx(root: Path) -> set[Path]:
    """Return every .mdx file under a directory, recursively."""
    if not root.exists():
        return set()
    return {p.resolve() for p in root.rglob("*.mdx")}


def main() -> int:
    ignored = load_ignore_list()
    referenced: set[Path] = set()
    dangling: list[tuple[Path, Path]] = []  # (nav_file, missing_path)

    for nav_file in NAV_CONFIGS:
        if not nav_file.exists():
            print(f"⚠  nav file missing, skipping: {nav_file.relative_to(REPO_ROOT)}")
            continue
        for mdx_path in extract_mdx_paths_from_nav(nav_file):
            referenced.add(mdx_path)
            if not mdx_path.exists():
                dangling.append((nav_file, mdx_path))

    existing: set[Path] = set()
    for root in PAGE_ROOTS:
        existing |= list_all_mdx(root)

    orphans = sorted(p for p in (existing - referenced - ignored))
    dangling.sort()

    ok = True
    if orphans:
        ok = False
        print("❌ Orphan MDX pages (exist in pages/ but not listed in any nav YAML):")
        print("   These will 404 on the docs site. Either register them in the")
        print("   matching nav, or add to scripts/.nav-ignore if intentionally unlisted.")
        print()
        for p in orphans:
            print(f"   - {p.relative_to(REPO_ROOT)}")
        print()

    if dangling:
        ok = False
        print("❌ Dangling nav entries (nav points to a missing MDX file):")
        print()
        for nav_file, missing in dangling:
            print(f"   - in {nav_file.relative_to(REPO_ROOT)}")
            print(f"     → {missing.relative_to(REPO_ROOT)}")
        print()

    if ok:
        print(f"✅ Nav check passed: {len(referenced)} referenced, {len(existing)} MDX pages, {len(ignored)} allow-listed.")
        return 0

    print(f"Found {len(orphans)} orphan(s), {len(dangling)} dangling nav entry(ies).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
