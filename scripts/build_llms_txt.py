#!/usr/bin/env python3
"""
Generate a Vapi-style llms.txt with per-page descriptions, sourced from
each page's `description:` frontmatter field. Writes to fern/llms.txt.

Why this exists: Fern's auto-generated llms.txt emits `[Title](URL.md)`
lines without descriptions. AI agents benefit from the description
suffix because they can prune candidate pages without fetching each
one. This script reads the same nav YAMLs the docs site builds from
and the same .mdx frontmatter, so the output stays in lockstep with
the rendered docs.

Output is wired into the Fern docs site via the `agents:` block in
docs.yml, which tells Fern to serve this file at /llms.txt instead of
the default.

Run before any PR that adds, removes, or renames pages. Idempotent.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterable

try:
    import yaml
except ImportError:
    print("PyYAML required. Install with: pip install pyyaml", file=sys.stderr)
    sys.exit(2)

REPO_ROOT = Path(__file__).resolve().parent.parent
SITE_URL = "https://docs.smallest.ai"
OUTPUT_FILE = REPO_ROOT / "fern" / "llms.txt"

# Nav files paired with the (a) URL prefix that Fern serves their pages under
# and (b) the *display* of the product in the output. Order here is the order
# sections appear in the output.
NAV_SOURCES: list[tuple[Path, str, str]] = [
    (REPO_ROOT / "fern" / "products" / "atoms.yml", "/voice-agents", "Voice Agents"),
    (REPO_ROOT / "fern" / "products" / "waves" / "versions" / "v4.0.0.yml", "/models", "Models"),
]

# Tabs whose pages are *not* surfaced in llms.txt. Reasons:
#   - api-reference: rendered from OpenAPI/AsyncAPI, no .mdx page = no description.
#   - changelog: dated entries are noisy in an index; deep-link from llms-full.txt instead.
#   - ai-tools: 2 thin index pages (Overview, Context7).
# mcp (6 pages) and integrations (10 partner pages) are kept — they have
# real content that AI agents may want to recommend.
SKIP_TABS = {"api-reference", "changelog", "ai-tools"}

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def slugify(label: str) -> str:
    """Match Fern's URL slug derivation:
    - split on lowercase→uppercase transitions (camelCase: 'WebSocket' → 'web-socket')
    - split on letter↔digit transitions ('lightning v3' → 'lightning-v-3')
    - strip 'and' / '&' connectors
    - lowercase, non-alphanum → hyphen, collapse, trim

    Verified empirically against live docs.smallest.ai for:
      'WebSocket SDK' → 'web-socket-sdk'
      'ElevenLabs' → 'eleven-labs'
      'iOS Swift' → 'i-os-swift'
      'Lightning v3.1 Pro' → 'lightning-v-3-1-pro'
      'Testing & Debugging' → 'testing-debugging'
    """
    s = label
    # Insert space at camelCase boundaries before lowercasing.
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", s)
    # Insert space at letter↔digit boundaries in either direction.
    s = re.sub(r"([A-Za-z])([0-9])", r"\1 \2", s)
    s = re.sub(r"([0-9])([A-Za-z])", r"\1 \2", s)
    s = s.lower()
    # Drop 'and' / '&' connectors.
    s = re.sub(r"\s*&\s*|\s+and\s+", " ", s)
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s


def read_frontmatter(mdx_path: Path) -> dict:
    """Return parsed frontmatter dict, or empty dict if none."""
    if not mdx_path.exists():
        return {}
    text = mdx_path.read_text(encoding="utf-8", errors="replace")
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}
    try:
        return yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return {}


def walk_nav(node, url_prefix: str, tab_slug: str, breadcrumb: list[str]) -> Iterable[dict]:
    """Yield {title, description, url, breadcrumb, tab} dicts for every page
    entry in a nav YAML subtree.

    URL is built as `{url_prefix}/{tab_slug}/{section_slugs.../}{page_slug}`,
    matching the slug rules Fern uses on the live docs site.
    """
    if isinstance(node, dict):
        if "page" in node and "path" in node:
            title = node["page"]
            mdx_path = (node["_base"] / node["path"]).resolve() if "_base" in node else None
            page_slug = node.get("slug") or slugify(title)
            parts = [url_prefix.rstrip("/"), tab_slug] + [slugify(s) for s in breadcrumb] + [page_slug]
            url = "/".join(parts)
            fm = read_frontmatter(mdx_path) if mdx_path else {}
            yield {
                "title": title,
                "description": (fm.get("description") or "").strip(),
                "url": url,
                "tab": tab_slug,
                "breadcrumb": list(breadcrumb),
            }
            return
        if "section" in node and "contents" in node:
            new_crumb = breadcrumb + [node["section"]]
            for item in node["contents"]:
                if isinstance(item, dict):
                    item["_base"] = node.get("_base")
                yield from walk_nav(item, url_prefix, tab_slug, new_crumb)
            return
    elif isinstance(node, list):
        for item in node:
            yield from walk_nav(item, url_prefix, tab_slug, breadcrumb)


def collect_pages_for_nav(nav_file: Path, url_prefix: str) -> list[dict]:
    """Load a nav YAML and return all page dicts across all non-skipped tabs."""
    if not nav_file.exists():
        return []
    with nav_file.open() as f:
        data = yaml.safe_load(f)

    base = nav_file.parent
    tabs_meta = data.get("tabs", {}) or {}
    nav = data.get("navigation", []) or []

    pages: list[dict] = []
    for tab in nav:
        if not isinstance(tab, dict) or "tab" not in tab:
            continue
        tab_key = tab["tab"]
        if tab_key in SKIP_TABS:
            continue
        tab_meta = tabs_meta.get(tab_key) or {}
        display = tab_meta.get("display-name") or tab_key
        tab_slug = tab_meta.get("slug") or slugify(display)
        for item in tab.get("layout", []) or []:
            if isinstance(item, dict):
                item["_base"] = base
            pages.extend(walk_nav(item, url_prefix, tab_slug, breadcrumb=[]))
    return pages


def format_line(page: dict) -> str:
    """Render a single page entry. Vapi-style: `- [Title](URL.md): description`."""
    desc = page["description"]
    suffix = f": {desc}" if desc else ""
    return f"- [{page['title']}]({SITE_URL}{page['url']}.md){suffix}"


def build_output() -> str:
    out: list[str] = [
        "# Smallest AI Docs",
        "",
        "## Instructions for AI Agents",
        "",
        "- For clean Markdown of any page, append `.md` to the page URL.",
        "- For a complete documentation index, see https://docs.smallest.ai/llms.txt",
        "- For section-specific indexes, append `/llms.txt` to any section URL.",
        "",
    ]
    for nav_file, url_prefix, product_label in NAV_SOURCES:
        pages = collect_pages_for_nav(nav_file, url_prefix)
        if not pages:
            continue
        out.append(f"## {product_label}")
        out.append("")
        # Group pages by tab, then by first breadcrumb (top-level section).
        # Preserves the order Fern shows them in the sidebar.
        seen_tabs: list[str] = []
        by_tab: dict[str, list[dict]] = {}
        for p in pages:
            t = p["tab"]
            if t not in by_tab:
                by_tab[t] = []
                seen_tabs.append(t)
            by_tab[t].append(p)
        for tab_slug in seen_tabs:
            tab_pages = by_tab[tab_slug]
            seen_sections: list[str] = []
            sections: dict[str, list[dict]] = {}
            for p in tab_pages:
                section = p["breadcrumb"][0] if p["breadcrumb"] else "Other"
                if section not in sections:
                    sections[section] = []
                    seen_sections.append(section)
                sections[section].append(p)
            for section in seen_sections:
                out.append(f"### {section}")
                out.append("")
                for p in sections[section]:
                    out.append(format_line(p))
                out.append("")
    return "\n".join(out).rstrip() + "\n"


def main() -> int:
    content = build_output()
    OUTPUT_FILE.write_text(content, encoding="utf-8")
    line_count = content.count("\n")
    print(f"Wrote {OUTPUT_FILE.relative_to(REPO_ROOT)} ({line_count} lines)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
