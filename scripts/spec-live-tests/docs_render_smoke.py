"""Docs-render smoke test — runs after deploy.

The bug class this catches: the spec is correct on disk, fern check passes,
spec_drift_check passes, but the rendered docs site silently drops an
operation or section. That's how `sendFinalize` was missing from the live
Pulse STT API ref for 5+ weeks even though every other check was green.

This script fetches a small set of customer-facing docs URLs and asserts
that every documented operation / signal / section appears in the rendered
HTML. If any expected marker is missing, exits 1 with a clear list of
what's missing where.

Wired into the post-deploy workflow so a Fern render regression surfaces
in minutes, not weeks. Add new pages + markers below as they're shipped.

Usage:
    python3 scripts/spec-live-tests/docs_render_smoke.py
    python3 scripts/spec-live-tests/docs_render_smoke.py --site https://preview-...fern.dev
"""
from __future__ import annotations
import argparse
import html
import re
import sys
import urllib.error
import urllib.request


# Each PAGE entry lists the URL path + a list of markers that MUST appear
# in the rendered HTML (case-insensitive, after stripping tags). Markers
# are short strings that should be present in the rendered text — operation
# names, signal payloads, section titles, etc. Stay focused: one or two
# per page is enough to catch the silent-drop class of bug.
#
# NOTE: Only MDX pages are checked here. Fern's auto-generated
# `/api-reference/**` pages render client-side (the SSR HTML is a shell
# with just the site chrome), so `curl | grep` for operation names on
# those pages always returns nothing — a false alarm dressed up as a
# real one. The PR #189 class of bug — silently-dropped spec content —
# is now caught by `spec_enum_vs_api_check.py` on the spec side and
# `check_nav.py` on the nav side, both of which run pre-deploy.
#
# For MDX pages the SSR body contains the actual content, so the
# marker check works. Everything below points at an MDX page.
PAGES = [
    {
        # Lightning v3.1 model card — surfaces the word-timestamp
        # feature. Deleting this section from the MDX would fail here.
        "path": "/models/model-cards/text-to-speech/lightning-v-3-1",
        "name": "Lightning v3.1 model card",
        "markers": [
            "word_timestamps",
            "word_timestamp",
        ],
    },
    {
        # TTS word-timestamps how-to — mirror of the above from the
        # documentation nav path, since users often land here first.
        "path": "/models/documentation/text-to-speech-lightning/word-timestamps",
        "name": "TTS word-timestamps how-to",
        "markers": [
            "word_timestamps",
            "word_timestamp",
        ],
    },
    {
        "path": "/models/documentation/speech-to-text-pulse/realtime-web-socket/response-format",
        "name": "Pulse STT response-format page",
        "markers": [
            "is_final",
            "is_last",
            "close_stream",
        ],
    },
    {
        "path": "/models/documentation/speech-to-text-pulse/features/inverse-text-normalization",
        "name": "Pulse STT ITN feature page",
        "markers": [
            "itn_normalize",
            "finalize_on_words",
            "eou_timeout_ms",
            # After PR #189, this page recommends both control messages
            "finalize",
            "close_stream",
        ],
    },
]


# Default to the production docs site. Override with --site for preview URLs.
DEFAULT_SITE = "https://docs.smallest.ai"


def fetch(url: str, timeout: int = 30) -> str:
    """Fetch a URL and return the body as text. Raises on network errors."""
    req = urllib.request.Request(url, headers={"User-Agent": "smallest-docs-smoke/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def strip_html(text: str) -> str:
    """Strip script/style/svg blocks + all tags, decode entities, collapse whitespace."""
    text = re.sub(r"<(script|style|svg)[^>]*>.*?</\1>", "", text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text


def check_page(site: str, page: dict) -> list[str]:
    """Return a list of missing markers for the given page (empty = OK)."""
    url = site.rstrip("/") + page["path"]
    try:
        body = fetch(url)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
        return [f"FETCH FAILED: {e}"]
    text = strip_html(body).lower()
    missing = [m for m in page["markers"] if m.lower() not in text]
    return missing


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--site", default=DEFAULT_SITE,
                   help="Base URL of the docs site to probe. Override for previews.")
    args = p.parse_args()

    print("=" * 78)
    print(f"Docs render smoke test — {args.site}")
    print("=" * 78)

    grand_missing = 0
    for page in PAGES:
        print(f"\n→ {page['name']}")
        print(f"  {args.site.rstrip('/')}{page['path']}")
        missing = check_page(args.site, page)
        if not missing:
            print(f"  ✓ all {len(page['markers'])} markers present: {', '.join(page['markers'])}")
            continue
        print(f"  ✗ {len(missing)} marker(s) missing from rendered HTML:")
        for m in missing:
            print(f"     - {m}")
        grand_missing += len(missing)

    print()
    print("=" * 78)
    if grand_missing == 0:
        print(f"PASS — all {sum(len(p['markers']) for p in PAGES)} markers present across {len(PAGES)} page(s)")
        return 0
    print(f"FAIL — {grand_missing} marker(s) missing across the rendered docs")
    print()
    print("This means the spec is on disk + CI passed, but the rendered docs site")
    print("dropped content during merge/render. Same class of bug as PR #189")
    print("(sendFinalize silently dropped for 5+ weeks). Investigate the docs build,")
    print("the override layering, or the deploy state.")
    print("=" * 78)
    return 1


if __name__ == "__main__":
    sys.exit(main())
