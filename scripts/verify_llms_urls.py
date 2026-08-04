#!/usr/bin/env python3
"""
Verify every URL in fern/llms.txt returns 200 on the live docs site.

Complements scripts/build_llms_txt.py + the llms-txt drift PR check:
  - Drift check catches nav <-> llms.txt out-of-sync at PR time.
  - This runtime check catches drift the other direction:
    llms.txt says a page exists at URL X, but live docs 404 it because
    Fern silently changed a slug derivation, a redirect went missing,
    or the CDN cache is stale.

Intended to run on a schedule against main, not on PR branches: a PR
may legitimately add pages that do not exist on live yet, which would
be a false positive here.

Exit codes:
  0 - every URL 200
  1 - one or more URLs returned non-200 (details printed to stdout)
  2 - argparse / io error
"""
from __future__ import annotations

import argparse
import concurrent.futures
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LLMS_TXT = REPO_ROOT / "fern" / "llms.txt"

# Matches `- [Title](https://.../page.md): description`.
LINK_RE = re.compile(r"^-\s*\[[^\]]+\]\((https?://[^)]+)\)", re.MULTILINE)


def extract_urls(text: str) -> list[str]:
    return LINK_RE.findall(text)


def check(url: str, timeout: float, attempts: int = 3) -> tuple[str, int, str]:
    """HEAD-check a URL. Retries on timeouts + transient errors (Fern is served
    via Vercel; a cold origin fetch can spike past 10s once per URL). HTTP
    responses like 404 are NOT retried."""
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "smallest-llms-verifier/1.0"})
    last_err = ""
    for i in range(attempts):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return url, resp.status, ""
        except urllib.error.HTTPError as e:
            return url, e.code, e.reason or ""
        except (urllib.error.URLError, TimeoutError) as e:
            last_err = str(e)
    return url, 0, last_err


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--file",
        type=Path,
        default=DEFAULT_LLMS_TXT,
        help=f"llms.txt to verify (default: {DEFAULT_LLMS_TXT.relative_to(REPO_ROOT)})",
    )
    p.add_argument("--concurrency", type=int, default=16, help="parallel requests")
    p.add_argument("--timeout", type=float, default=15.0, help="per-request timeout seconds")
    args = p.parse_args()

    if not args.file.exists():
        print(f"error: {args.file} not found", file=sys.stderr)
        return 2

    urls = extract_urls(args.file.read_text(encoding="utf-8"))
    if not urls:
        print(f"error: no URLs found in {args.file}", file=sys.stderr)
        return 2

    try:
        rel = args.file.resolve().relative_to(REPO_ROOT)
    except ValueError:
        rel = args.file
    print(f"Verifying {len(urls)} URLs from {rel} against live docs...")

    fails: list[tuple[str, int, str]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        futures = {ex.submit(check, u, args.timeout): u for u in urls}
        for fut in concurrent.futures.as_completed(futures):
            url, status, err = fut.result()
            if status != 200:
                fails.append((url, status, err))
                print(f"  FAIL  {status:>3}  {url}  {err}")

    print()
    if fails:
        print(f"{len(fails)} of {len(urls)} URLs failed.")
        return 1
    print(f"All {len(urls)} URLs returned 200.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
