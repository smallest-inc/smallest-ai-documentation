#!/usr/bin/env python3
"""
Verify every internal doc link inside an MDX file resolves on docs.smallest.ai.

Replaces pattern-matching heuristics (which give false positives — some
leading-slash paths are Fern CDN assets, others are Mintlify-era page links).
Actual HTTP-test is the only reliable signal.

USAGE
    python3 scripts/check_links.py                       # scan every MDX under fern/products/
    python3 scripts/check_links.py path/to/one.mdx ...   # scan specific files (used by CI on changed files)
    python3 scripts/check_links.py --base https://smallest-ai.docs.buildwithfern.com  # override target (for preview URLs)

WHAT IT DOES
    1. Grep internal links — Markdown `[text](/path)` and HTML `href="/path"`.
    2. De-duplicate URLs to minimise HTTP requests.
    3. HEAD each URL against docs.smallest.ai (or --base). Follow redirects.
    4. Flag anything that isn't 2xx or 3xx→2xx as a broken link.

WHAT IT IGNORES
    - External links (http(s)://, mailto:, discord://, etc.)
    - Anchors within the current page (#section)
    - Image CDN paths that Fern rewrites at build time (detected because
      they return 404 at docs.smallest.ai but the image still renders —
      we ignore those by looking at the element: if the URL appears inside
      an `<img src>` or Markdown `![]()`, skip it — Fern handles assets)
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

try:
    import yaml  # used for --registered-only mode
except ImportError:
    yaml = None

REPO_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_BASE = "https://docs.smallest.ai"
TIMEOUT = 10
MAX_WORKERS = 16

# Nav YAMLs whose `path:` entries define "files that render to customers".
# Anything NOT referenced from one of these is either an orphan or belongs
# to a frozen older version — its broken links don't hurt live users.
NAV_CONFIGS = [
    REPO_ROOT / "fern" / "products" / "atoms.yml",
    REPO_ROOT / "fern" / "products" / "waves" / "versions" / "v4.0.0.yml",
    REPO_ROOT / "fern" / "products" / "waves" / "versions" / "v3.0.1.yml",
    REPO_ROOT / "fern" / "products" / "waves" / "versions" / "v2.2.0.yml",
]

# Root-relative internal paths — [text](/path), href="/path", etc.
MD_LINK_RE = re.compile(r'(?<!!)\[[^\]]*\]\((/[^)]+)\)')         # [text](/path) — NOT image
IMG_MD_RE = re.compile(r'!\[[^\]]*\]\((/[^)]+)\)')               # ![](/path) — skip (asset)
HREF_RE = re.compile(r'href\s*=\s*["\'](/[^"\']+)["\']')         # href="/path"
IMG_SRC_RE = re.compile(r'<img[^>]*src\s*=\s*["\'](/[^"\']+)["\']')  # <img src="/path"> — skip

# Same-host fully-qualified URLs — catches pages that write out the full
# docs domain (e.g. `https://docs.smallest.ai/waves/foo`) instead of a
# root-relative `/waves/foo`. Fern's own checker catches the live site's
# external links but renderer-agnostic link rot caught locally is faster.
# Matches whatever domain DEFAULT_BASE points at, so overriding --base
# also targets the same host in this regex.
FQ_SAME_HOST_RE_TEMPLATE = r'https?://{host}(/[^\s\'"\)<>]*)'


def nav_registered_files() -> set[Path]:
    """Return the set of MDX files registered in any nav YAML."""
    if yaml is None:
        return set()
    found: set[Path] = set()
    for cfg in NAV_CONFIGS:
        if not cfg.exists():
            continue
        base = cfg.parent
        data = yaml.safe_load(cfg.read_text())

        def walk(node):
            if isinstance(node, dict):
                if "path" in node and isinstance(node["path"], str) and node["path"].endswith(".mdx"):
                    found.add((base / node["path"]).resolve())
                for v in node.values():
                    walk(v)
            elif isinstance(node, list):
                for item in node:
                    walk(item)

        walk(data)
    return found


def extract_internal_links(content: str, base: str = DEFAULT_BASE) -> set[str]:
    """Return set of internal URL paths from an MDX file, excluding image refs.

    "Internal" means root-relative (`/path`) OR same-host fully-qualified
    (`https://{base_host}/path`). Cross-domain links are skipped here; Fern's
    built-in checker on the deployed site covers those.
    """
    # Collect asset-like URLs first (anything inside an image ref — we skip these)
    asset_urls: set[str] = set()
    for m in IMG_MD_RE.finditer(content):
        asset_urls.add(m.group(1))
    for m in IMG_SRC_RE.finditer(content):
        asset_urls.add(m.group(1))

    urls: set[str] = set()
    for m in MD_LINK_RE.finditer(content):
        url = m.group(1).split('#')[0]
        if url and url not in asset_urls:
            urls.add(url)
    for m in HREF_RE.finditer(content):
        url = m.group(1).split('#')[0]
        if url and url not in asset_urls:
            urls.add(url)

    # Also pick up fully-qualified same-host links — these used to slip
    # through because the regexes above only matched a leading slash.
    host = re.escape(base.split('://', 1)[-1].rstrip('/'))
    for m in re.finditer(FQ_SAME_HOST_RE_TEMPLATE.format(host=host), content):
        url = m.group(1).split('#')[0].rstrip('.,);:\'"')
        if url and url not in asset_urls:
            urls.add(url)
    return urls


def newly_registered_mdx_stems(base_ref: str) -> set[str]:
    """Return the stems of MDX files whose URLs may legitimately 404 against
    the production docs site during an in-flight deploy.

    Two cases are classified as pending-deploy (not broken):

    (a) Pages registered in the current branch's nav but not in base_ref's.
        Cross-links between pages added in the same PR fall here.
    (b) Pages registered in base_ref's nav (already merged to main) whose
        production deploy has not yet caught up. Without this, every open
        PR fails link-check in the window between merge-to-main and CDN
        propagation for any page added by a prior PR.

    Heuristic: matches when the URL's last path segment equals the MDX
    file's stem. Handles the common case where Fern's slug == file stem.
    Falls through (treated as broken) when a display-name-derived slug
    differs from the stem (e.g. websocket-sdk.mdx rendered as /web-socket-sdk).
    """
    # Union of current-branch nav + base_ref nav. Either is a valid
    # pending-deploy candidate; genuinely orphaned links (pointing at
    # MDX files that no nav registers) still fall through to "broken".
    current = {p.name for p in nav_registered_files()}
    base_registered: set[str] = set()
    for cfg in NAV_CONFIGS:
        if not cfg.exists():
            continue
        try:
            base_yaml = subprocess.check_output(
                ["git", "show", f"{base_ref}:{cfg.relative_to(REPO_ROOT)}"],
                cwd=REPO_ROOT,
                stderr=subprocess.DEVNULL,
                text=True,
            )
        except subprocess.CalledProcessError:
            continue
        if yaml is None:
            continue
        data = yaml.safe_load(base_yaml)
        base_dir = cfg.parent

        def walk(node):
            if isinstance(node, dict):
                if "path" in node and isinstance(node["path"], str) and node["path"].endswith(".mdx"):
                    base_registered.add((base_dir / node["path"]).resolve().name)
                if "changelog" in node and isinstance(node["changelog"], str):
                    entries_dir = (base_dir / node["changelog"]).resolve()
                    if entries_dir.is_dir():
                        for mdx in entries_dir.rglob("*.mdx"):
                            base_registered.add(mdx.resolve().name)
                for v in node.values():
                    walk(v)
            elif isinstance(node, list):
                for item in node:
                    walk(item)

        walk(data)

    return {Path(n).stem for n in (current | base_registered)}


def probe(url: str, base: str) -> tuple[str, int, str]:
    """HEAD-check a single URL. Return (url, status_code, note).

    Retries transient network errors up to 3 times with exponential backoff.
    HTTP-level errors (4xx/5xx) are returned immediately without retry.
    """
    full = base.rstrip('/') + url
    req = Request(full, method='HEAD', headers={'User-Agent': 'fern-link-check/1.0'})
    last_err: Exception | None = None
    for attempt in range(3):
        try:
            with urlopen(req, timeout=TIMEOUT) as resp:
                return url, resp.status, ''
        except HTTPError as e:
            return url, e.code, ''
        except (URLError, Exception) as e:
            last_err = e
            if attempt < 2:
                time.sleep(1 + attempt)
                continue
            if isinstance(e, URLError):
                return url, -1, f'URL error: {e.reason} (after 3 attempts)'
            return url, -1, f'{type(e).__name__}: {e} (after 3 attempts)'
    return url, -1, f'unreachable: {last_err}'


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('files', nargs='*', help='MDX files to scan (default: all under fern/products/)')
    ap.add_argument('--base', default=DEFAULT_BASE, help=f'Base URL to test against (default: {DEFAULT_BASE})')
    ap.add_argument(
        '--all-files', action='store_true',
        help='Check every MDX file including orphans and frozen versions. Default behaviour is to only check files registered in a nav YAML (i.e. pages that actually render on docs.smallest.ai).',
    )
    ap.add_argument(
        '--pending-base', default='origin/main',
        help='Git ref to diff against when detecting pages added in this branch. A 404 on a URL whose last segment matches a newly-added MDX stem is reported as PENDING rather than broken. Default: origin/main.',
    )
    args = ap.parse_args()

    if args.files:
        # Explicit list — honour exactly what was passed (used by PR CI on changed files)
        targets = [Path(f) for f in args.files if f.endswith('.mdx')]
    else:
        all_mdx = list((REPO_ROOT / 'fern' / 'products').rglob('*.mdx'))
        if args.all_files:
            targets = all_mdx
        else:
            registered = nav_registered_files()
            targets = [f for f in all_mdx if f.resolve() in registered]
            skipped = len(all_mdx) - len(targets)
            if skipped:
                print(f'Skipping {skipped} MDX file(s) not registered in any nav YAML (orphan/frozen). Use --all-files to include them.')

    if not targets:
        print('No MDX files to check.')
        return 0

    # url -> [files referencing it]
    url_sources: dict[str, list[str]] = {}
    for f in targets:
        if not f.exists():
            continue
        try:
            content = f.read_text()
        except UnicodeDecodeError:
            continue
        for url in extract_internal_links(content, args.base):
            url_sources.setdefault(url, []).append(str(f.relative_to(REPO_ROOT) if f.is_absolute() else f))

    if not url_sources:
        print(f'✅ No internal links found across {len(targets)} file(s).')
        return 0

    print(f'Checking {len(url_sources)} unique internal URL(s) across {len(targets)} file(s) against {args.base} ...')

    pending_stems = newly_registered_mdx_stems(args.pending_base)

    broken: list[tuple[str, int, list[str]]] = []
    pending: list[tuple[str, int, list[str]]] = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(probe, url, args.base): url for url in url_sources}
        for fut in as_completed(futures):
            url, code, note = fut.result()
            # 2xx and 3xx are acceptable (Fern commonly returns 307 for redirect-to-first-endpoint)
            if code < 200 or code >= 400:
                last_segment = url.rstrip('/').rsplit('/', 1)[-1]
                if last_segment in pending_stems:
                    pending.append((url, code, url_sources[url]))
                else:
                    broken.append((url, code, url_sources[url]))

    if pending:
        print()
        print(f'⏳ {len(pending)} link(s) pending deploy (points at a page added in this branch):')
        for url, code, sources in sorted(pending):
            print(f'  {code}  {url}')
            for src in sources[:2]:
                print(f'        in: {src}')

    if not broken:
        resolved = len(url_sources) - len(pending)
        print(f'✅ {resolved} internal link(s) resolve; {len(pending)} pending deploy.')
        return 0

    print()
    print(f'❌ {len(broken)} broken link(s):')
    for url, code, sources in sorted(broken):
        print(f'\n  {code}  {url}')
        for src in sources[:3]:
            print(f'        in: {src}')
        if len(sources) > 3:
            print(f'        ...and {len(sources) - 3} more')
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
