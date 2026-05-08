#!/usr/bin/env python3
"""
Lightning v3.1 spec language enum ↔ voice catalog drift check.

The Lightning v3.1 server schema accepts more language codes than the
voice catalog actually has trained voices for. Codes without voices
silently fall back to the voice's primary language — so users who pass
e.g. `language=ar` get back the voice's English (or Hindi) audio without
any error. This is exactly the bug class that PR #125 introduced and
the May 8 correction reversed.

This check fails when the spec enum lists a language that has zero
voices in the live catalog. Run on every PR that touches the Lightning
v3.1 spec.

Reads:
  - spec enum: fern/apis/waves/openapi/lightning-v3.1-openapi.yaml →
    components.schemas.LightningV31Request.properties.language.enum
  - live catalog: GET https://api.smallest.ai/waves/v1/lightning-v3.1/get_voices
    voices[].tags.language

Exit codes:
  0 — every spec code (except `auto`) has at least one voice
  1 — one or more spec codes have zero voices (drift)
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
SPEC = REPO / "fern/apis/waves/openapi/lightning-v3.1-openapi.yaml"

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
}


def load_spec_enum() -> set[str]:
    try:
        spec = yaml.safe_load(SPEC.read_text())
    except Exception as exc:
        print(f"FATAL: cannot parse {SPEC}: {exc}", file=sys.stderr)
        sys.exit(2)
    schemas = spec.get("components", {}).get("schemas", {})
    for name, schema in schemas.items():
        if name.lower().startswith("lightningv3"):
            enum = (
                schema.get("properties", {})
                .get("language", {})
                .get("enum")
            )
            if enum:
                return set(enum)
    print(f"FATAL: no language enum found under components.schemas.* in {SPEC}", file=sys.stderr)
    sys.exit(2)


def load_voice_catalog_codes() -> set[str]:
    r = requests.get(
        "https://api.smallest.ai/waves/v1/lightning-v3.1/get_voices",
        headers={"Authorization": f"Bearer {API_KEY}"},
        timeout=30,
    )
    r.raise_for_status()
    voices = r.json().get("voices", [])
    seen_tags: set[str] = set()
    for v in voices:
        for tag in (v.get("tags") or {}).get("language") or []:
            seen_tags.add(tag.lower())
    codes = {TAG_TO_CODE[t] for t in seen_tags if t in TAG_TO_CODE}
    unmapped = seen_tags - set(TAG_TO_CODE.keys())
    if unmapped:
        print(f"NOTE: voice tags not mapped to ISO codes: {sorted(unmapped)}")
    return codes


def main() -> int:
    spec = load_spec_enum()
    catalog = load_voice_catalog_codes()
    auto_in_spec = "auto" in spec
    spec_real = spec - {"auto"}

    print("=" * 72)
    print("Lightning v3.1 — spec enum ↔ voice catalog drift check")
    print("=" * 72)
    print(f"spec enum    ({len(spec)} values, auto={'yes' if auto_in_spec else 'no'}): {sorted(spec)}")
    print(f"voice codes  ({len(catalog)} values): {sorted(catalog)}")
    print()

    spec_only = spec_real - catalog
    catalog_only = catalog - spec_real

    if not spec_only and not catalog_only:
        print(f"PASS — spec lists exactly the {len(spec_real)} languages with voices.")
        return 0

    if spec_only:
        print(f"DRIFT — spec lists {len(spec_only)} language(s) with NO voices in the catalog:")
        for c in sorted(spec_only):
            print(f"  {c}  (silently falls back; users get wrong language)")
    if catalog_only:
        print(f"GAP — voice catalog has {len(catalog_only)} language(s) NOT in the spec enum:")
        for c in sorted(catalog_only):
            print(f"  {c}  (users can't pass this code)")

    return 1


if __name__ == "__main__":
    sys.exit(main())
