"""Audit every github.com/smallest-inc/cookbook URL in v4 docs MDX.

The cookbook is a separate repo. Doc pages reference cookbook samples via
hardcoded GitHub blob/tree URLs. When a sample is renamed, moved, or
removed in the cookbook repo, the doc link silently 404s — link-check.py
won't catch it because it only audits internal slugs.

This script:
  1. Walks v4 MDX (fern/products/{waves,atoms}/pages and v4.0.0 versions).
  2. Extracts every `https://github.com/smallest-inc/cookbook/...` URL.
  3. Issues a small GET against each one (HEAD doesn't work for GitHub
     blob/tree URLs — they redirect HEAD to a login wall).
  4. Reports any URL that doesn't return 2xx.

Usage:
    python3 scripts/check_cookbook_links.py            # human-readable
    python3 scripts/check_cookbook_links.py --json     # machine-readable
    python3 scripts/check_cookbook_links.py --fail-on-broken  # CI gate
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Where to scan. Frozen versions (v2.2.0, v3.0.1) are intentionally
# excluded — we don't ship them anymore and they reference cookbook
# state from a prior era.
SCAN_PATHS = [
    REPO_ROOT / "fern" / "products" / "waves" / "pages",
    REPO_ROOT / "fern" / "products" / "atoms" / "pages",
    REPO_ROOT / "fern" / "products" / "waves" / "versions" / "v4.0.0",
]

# Match cookbook URLs. Stop at whitespace, markdown bracket/paren
# closers, quotes, angle brackets, or backticks.
COOKBOOK_RE = re.compile(
    r"https://github\.com/smallest-inc/cookbook/[^\s)\]\"'<>`]+",
)
# Trim trailing punctuation that's likely sentence-end, not URL.
TRAILING_PUNCT = ".,;:"


def find_cookbook_urls() -> dict[str, list[str]]:
    """Return {url: [files referencing it]} for every cookbook URL in scope."""
    found: dict[str, list[str]] = {}
    for root in SCAN_PATHS:
        if not root.exists():
            continue
        for path in root.rglob("*.mdx"):
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for raw in COOKBOOK_RE.findall(text):
                url = raw.rstrip(TRAILING_PUNCT)
                # Strip URL fragment (#section). GitHub returns 200 for
                # any valid path regardless of whether the anchor exists,
                # so checking the path is the only meaningful signal.
                # Anchor rot is a separate concern not covered by this
                # audit; HEAD-checking the path catches actual link rot.
                url = url.split("#", 1)[0]
                # Skip the bare prefix that survives when the regex
                # stops at a space mid-sentence (e.g., "see the
                # https://github.com/smallest-inc/cookbook/raw/main/ folder").
                if url.endswith("/raw/main/") or url.endswith("/tree/main/"):
                    continue
                rel = str(path.relative_to(REPO_ROOT))
                found.setdefault(url, [])
                if rel not in found[url]:
                    found[url].append(rel)
    return found


def head_check(url: str, timeout: int = 15, max_attempts: int = 3) -> tuple[int, str]:
    """Return (status_code, error_message). status_code=0 on network error.

    Retries with exponential backoff on transient failures (5xx responses
    and URL/network errors). 4xx responses are treated as definitive and
    not retried — those are real broken links, not flakes. The audit runs
    weekly against ~50 URLs, so an extra 1–4s per genuine flake is cheap
    insurance against false-positive issues + Slack pings on Monday
    morning when GitHub blips.
    """
    # GitHub redirects HEAD on blob/tree URLs to a login page (302). Use
    # a small GET instead and let the connection close after headers.
    req = urllib.request.Request(
        url,
        method="GET",
        headers={
            "User-Agent": "smallest-docs-cookbook-link-audit/1.0",
            "Accept": "*/*",
        },
    )
    last_status = 0
    last_err = ""
    for attempt in range(max_attempts):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.status, ""
        except urllib.error.HTTPError as e:
            last_status = e.code
            last_err = f"HTTP {e.code} {e.reason}"
            # 4xx is a definitive answer — don't retry.
            if 400 <= e.code < 500:
                return last_status, last_err
            # 5xx falls through to retry.
        except urllib.error.URLError as e:
            last_status = 0
            last_err = f"URLError: {e.reason}"
        except Exception as e:  # noqa: BLE001
            last_status = 0
            last_err = f"{type(e).__name__}: {e}"
        # Backoff before next attempt: 1s, 2s, 4s …
        if attempt < max_attempts - 1:
            time.sleep(2 ** attempt)
    return last_status, last_err


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    parser.add_argument(
        "--fail-on-broken",
        action="store_true",
        help="exit 1 if any cookbook URL is broken (for CI)",
    )
    args = parser.parse_args()

    urls = find_cookbook_urls()
    if not urls:
        if args.json:
            print(json.dumps({"checked": 0, "broken": [], "ok": []}))
        else:
            print("No cookbook URLs found in scope.")
        return 0

    results = []
    for url in sorted(urls):
        status, err = head_check(url)
        ok = 200 <= status < 300
        results.append({
            "url": url,
            "status": status,
            "ok": ok,
            "error": err,
            "files": urls[url],
        })

    broken = [r for r in results if not r["ok"]]
    ok = [r for r in results if r["ok"]]

    if args.json:
        print(json.dumps({
            "checked": len(results),
            "broken": broken,
            "ok": ok,
        }, indent=2))
    else:
        print(f"Checked {len(results)} cookbook URLs across v4 docs.")
        print(f"  OK:     {len(ok)}")
        print(f"  Broken: {len(broken)}")
        if broken:
            print("\nBroken URLs:")
            for r in broken:
                print(f"  - {r['url']}")
                print(f"    status: {r['status']}  {r['error']}")
                for f in r["files"]:
                    print(f"    referenced in: {f}")

    if args.fail_on_broken and broken:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
