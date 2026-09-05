#!/usr/bin/env python3
"""
Compute the rendered URL of every MDX page from a Fern nav config.

Works for both shapes:
  - a product nav file (fern/products/atoms.yml) with a URL prefix ("/voice-agents")
  - the single-site docs.yml (tabs + navigation inline) with prefix ""

Slug rules mirror Fern: tab slug -> section slugs -> page slug, honoring
`slug:` / `skip-slug:` on tabs, sections, and pages, and an absolute
frontmatter `slug:` pin (leading "/") which overrides the whole path.

Usage:
  python3 scripts/ia/page_urls.py fern/products/atoms.yml /voice-agents > old-atoms.json
  python3 scripts/ia/page_urls.py fern/docs.yml "" > new.json
Output: JSON list of {"file": <repo-relative mdx path>, "url": <path>, "title": ...}
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def slugify(label: str) -> str:
    s = label
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", s)
    s = re.sub(r"([A-Za-z])([0-9])", r"\1 \2", s)
    s = re.sub(r"([0-9])([A-Za-z])", r"\1 \2", s)
    s = s.lower()
    s = re.sub(r"\s*&\s*|\s+and\s+", " ", s)
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s


def read_frontmatter(p: Path) -> dict:
    if not p.exists():
        return {}
    m = FRONTMATTER_RE.match(p.read_text(encoding="utf-8", errors="replace"))
    if not m:
        return {}
    try:
        return yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return {}


def node_slug_parts(node: dict, label_key: str) -> list[str]:
    """Slug contribution of a section/tab node: [] if skip-slug, else [slug]."""
    if node.get("skip-slug"):
        return []
    explicit = node.get("slug")
    if explicit:
        return [str(explicit).strip("/")]
    return [slugify(str(node[label_key]))]


def walk(items, base: Path, crumbs: list[str], out: list[dict]):
    for node in items or []:
        if not isinstance(node, dict):
            continue
        if "page" in node and "path" in node:
            mdx = (base / node["path"]).resolve()
            fm = read_frontmatter(mdx)
            fm_slug = str(fm.get("slug") or "").strip()
            if fm_slug.startswith("/"):
                url = "/" + fm_slug.strip("/")
            else:
                leaf = fm_slug or node.get("slug") or slugify(str(node["page"]))
                url = "/" + "/".join([c for c in crumbs if c] + [str(leaf).strip("/")])
            try:
                rel = str(mdx.relative_to(REPO_ROOT))
            except ValueError:
                rel = str(mdx)
            out.append({"file": rel, "url": url, "title": node["page"], "hidden": bool(node.get("hidden"))})
        elif "section" in node:
            walk(node.get("contents"), base, crumbs + node_slug_parts(node, "section"), out)
        elif "api" in node:
            parts = node_slug_parts(node, "api")
            out.append({"file": f"<api:{node.get('api-name')}>", "url": "/" + "/".join([c for c in crumbs if c] + parts), "title": node["api"], "hidden": False})
        elif "changelog" in node:
            title = node.get("title")
            parts = [slugify(title)] if title else []
            out.append({"file": f"<changelog:{node['changelog']}>", "url": "/" + "/".join([c for c in crumbs if c] + parts), "title": title or "Changelog", "hidden": False})


def compute(nav_file: Path, prefix: str) -> list[dict]:
    data = yaml.safe_load(nav_file.read_text())
    base = nav_file.parent
    tabs = data.get("tabs") or {}
    out: list[dict] = []
    root = [prefix.strip("/")] if prefix.strip("/") else []
    for tab in data.get("navigation") or []:
        if not isinstance(tab, dict):
            continue
        if "tab" in tab:
            meta = tabs.get(tab["tab"]) or {}
            if meta.get("skip-slug"):
                tparts: list[str] = []
            else:
                tparts = [meta.get("slug") or slugify(meta.get("display-name") or tab["tab"])]
            walk(tab.get("layout"), base, root + tparts, out)
        else:
            walk([tab], base, root, out)
    return out


if __name__ == "__main__":
    nav = REPO_ROOT / sys.argv[1]
    prefix = sys.argv[2] if len(sys.argv) > 2 else ""
    json.dump(compute(nav, prefix), sys.stdout, indent=1)
