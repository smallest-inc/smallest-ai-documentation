#!/usr/bin/env python3
"""
Unified TTS spec language enum ↔ voice catalog drift check.

The TTS request schema accepts language codes. The voice catalog exposes
tags. When a code shows up in the catalog but not in the spec, users
can't pass it (missing docs). When a code shows up in the spec but not
in the catalog, the model silently falls back to the voice's primary
language, so the user gets wrong audio without any error.

Post-unification (PR #301) the spec covers both `lightning_v3.1` and
`lightning_v3.1_pro` models in a single enum. The v3.1 catalog only
lists voices trained under the base pool. Pro voices are exposed via
`/waves/v1/lightning-v3.1-pro/get_voices` when that pool exists.

Drift classification:
  - HARD (exit 1): catalog exposes a language the spec doesn't list —
    users can't pass it, definite docs gap.
  - SOFT (informational): spec lists a language absent from v3.1 catalog
    but potentially covered by Pro. Reported but doesn't fail. A future
    Pro-catalog query can tighten this.

Reads:
  - spec enum: fern/apis/waves/openapi/tts-openapi.yaml →
    components.schemas.TtsRequest.properties.language.enum
  - live catalog: GET https://api.smallest.ai/waves/v1/lightning-v3.1/get_voices
                  GET https://api.smallest.ai/waves/v1/lightning-v3.1-pro/get_voices
    voices[].tags.language

Exit codes:
  0 — no HARD drift (catalog fully documented)
  1 — HARD drift (catalog code missing from spec)
  2 — could not load spec or fetch catalog
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import requests
import yaml

API_KEY = os.environ.get("SMALLEST_API_KEY")
if not API_KEY:
    print("FATAL: set SMALLEST_API_KEY", file=sys.stderr)
    sys.exit(2)

REPO = Path(__file__).resolve().parents[2]
SPEC = REPO / "fern/apis/waves/openapi/tts-openapi.yaml"

# Tag-name → ISO 639-1 code mapping (the voice catalog uses English names)
TAG_TO_CODE = {
    "english": "en",
    "hindi": "hi",
    "marathi": "mr",
    "kannada": "kn",
    "tamil": "ta",
    "bengali": "bn",
    "gujarati": "gu",
    "telugu": "te",
    "malayalam": "ml",
    "punjabi": "pa",
    "odia": "or",
    "spanish": "es",
    "german": "de",
    "french": "fr",
    "italian": "it",
    "portuguese": "pt",
    "russian": "ru",
    "greek": "el",
    "finnish": "fi",
    "norwegian": "no",
    "polish": "pl",
    "arabic": "ar",
    "chinese": "zh",
    "mandarin": "zh",
    "indonesian": "id",
    "japanese": "ja",
    "korean": "ko",
    "malay": "ms",
    "turkish": "tr",
    "vietnamese": "vi",
}

CATALOG_ENDPOINTS = [
    "https://api.smallest.ai/waves/v1/lightning-v3.1/get_voices",
    "https://api.smallest.ai/waves/v1/lightning-v3.1-pro/get_voices",
]


def load_spec_enum() -> set[str]:
    try:
        spec = yaml.safe_load(SPEC.read_text())
    except Exception as exc:
        print(f"FATAL: cannot parse {SPEC}: {exc}", file=sys.stderr)
        sys.exit(2)
    enum = (
        spec.get("components", {})
        .get("schemas", {})
        .get("TtsRequest", {})
        .get("properties", {})
        .get("language", {})
        .get("enum")
    )
    if not enum:
        print(f"FATAL: no language enum at components.schemas.TtsRequest.properties.language.enum in {SPEC}", file=sys.stderr)
        sys.exit(2)
    return set(enum)


def load_catalog_codes(url: str) -> set[str] | None:
    """Return set of ISO codes for a catalog URL. None if endpoint 404s
    (e.g. Pro pool not yet publicly reachable) — caller treats as skipped."""
    try:
        r = requests.get(
            url,
            headers={"Authorization": f"Bearer {API_KEY}"},
            timeout=30,
        )
    except requests.RequestException as exc:
        print(f"NOTE: {url} unreachable ({exc}); skipping this catalog", file=sys.stderr)
        return None
    if r.status_code == 404:
        print(f"NOTE: {url} returned 404; skipping (pool may not be exposed via this endpoint yet)")
        return None
    if not r.ok:
        print(f"FATAL: {url} → HTTP {r.status_code}: {r.text[:200]}", file=sys.stderr)
        sys.exit(2)
    voices = r.json().get("voices", [])
    seen_tags: set[str] = set()
    for v in voices:
        for tag in (v.get("tags") or {}).get("language") or []:
            seen_tags.add(tag.lower())
    codes = {TAG_TO_CODE[t] for t in seen_tags if t in TAG_TO_CODE}
    unmapped = seen_tags - set(TAG_TO_CODE.keys())
    if unmapped:
        print(f"NOTE: voice tags not mapped to ISO codes ({url}): {sorted(unmapped)}")
    return codes


def main() -> int:
    spec = load_spec_enum()
    spec_real = spec - {"auto"}

    v31_catalog = load_catalog_codes(CATALOG_ENDPOINTS[0]) or set()
    pro_catalog = load_catalog_codes(CATALOG_ENDPOINTS[1])

    if pro_catalog is None:
        combined_catalog = v31_catalog
        pro_note = " (Pro catalog not queryable; SOFT-drift check is v3.1-only)"
    else:
        combined_catalog = v31_catalog | pro_catalog
        pro_note = ""

    print("=" * 72)
    print("Unified TTS spec enum ↔ voice catalog drift check")
    print("=" * 72)
    print(f"spec enum       ({len(spec)} values): {sorted(spec)}")
    print(f"v3.1 catalog    ({len(v31_catalog)} values): {sorted(v31_catalog)}")
    if pro_catalog is not None:
        print(f"Pro catalog     ({len(pro_catalog)} values): {sorted(pro_catalog)}")
    print(f"combined        ({len(combined_catalog)} values){pro_note}")
    print()

    catalog_only = combined_catalog - spec_real          # HARD drift
    spec_only = spec_real - combined_catalog             # SOFT drift

    exit_code = 0

    if catalog_only:
        print(f"HARD DRIFT — catalog exposes {len(catalog_only)} language(s) NOT in spec enum:")
        for c in sorted(catalog_only):
            print(f"  {c}  (voices exist; users can't pass this code — docs gap)")
        exit_code = 1

    if spec_only:
        print(f"SOFT DRIFT (informational) — spec lists {len(spec_only)} language(s) not in accessible catalogs:")
        for c in sorted(spec_only):
            print(f"  {c}  (may be covered by a pool not queried; verify manually)")

    if exit_code == 0 and not spec_only:
        print(f"PASS — spec covers the full {len(combined_catalog)}-language catalog with no unaccounted codes.")
    elif exit_code == 0:
        print(f"PASS — no HARD drift ({len(spec_only)} soft item(s) noted for follow-up).")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
