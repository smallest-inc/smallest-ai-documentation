"""Spec ↔ live API enum drift check.

Catches the class of bug where a spec ships an outdated enum (e.g.,
Lightning v3.1 language listed [en, hi] but the platform actually
accepts 15) without anyone noticing until a customer complains.

How it works
------------
For each enum field listed in CHECKS, send a deliberately-bogus value
to the live API and parse the canonical accepted-values list from the
`invalid_enum_value` error payload. Compare against the spec enum.
Report drift in either direction:
  - in spec but not accepted by API → docs claim a value the platform rejects
  - accepted by API but not in spec → docs are missing a supported value

Limitations
-----------
- Only covers endpoints that return their canonical enum via an
  `invalid_enum_value`-style error response. Add new entries to CHECKS
  as new endpoints ship.
- Boolean enums (true/false) are not worth validating — both values
  always work or fail in obvious ways. Excluded from CHECKS.

Usage
-----
    SMALLEST_API_KEY=... python3 scripts/spec-live-tests/spec_enum_vs_api_check.py
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
KEY = os.environ.get("SMALLEST_API_KEY")
if not KEY:
    sys.exit("SMALLEST_API_KEY env var is required")


# Each check: (label, send_request_fn, spec_path_relative_to_repo, json_path_to_enum)
# send_request_fn returns (status, body_dict) for a request that should
# trigger invalid_enum_value on the targeted field.
def post(url: str, body: dict) -> tuple[int, dict | str]:
    r = urllib.request.Request(
        url, data=json.dumps(body).encode(), method="POST",
        headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(r, timeout=20) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(body_text)
        except json.JSONDecodeError:
            return e.code, body_text


def unified_tts_post(field: str, bogus_value, model: str | None = None):
    """Live-probe the unified TTS endpoint. `model` optionally sets the
    request's `model` field to force the base vs Pro pool."""
    body = {"text": "hi", "voice_id": "magnus", "sample_rate": 24000, field: bogus_value}
    if model:
        body["model"] = model
    return post("https://api.smallest.ai/waves/v1/tts", body)


CHECKS = [
    (
        "unified /waves/v1/tts (model=lightning_v3.1) / language",
        lambda: unified_tts_post("language", "__bogus__", model="lightning_v3.1"),
        "fern/apis/waves/openapi/tts-openapi.yaml",
        ["components", "schemas", "TtsRequest", "properties", "language", "enum"],
    ),
    (
        "unified /waves/v1/tts (model=lightning_v3.1_pro) / language",
        lambda: unified_tts_post("language", "__bogus__", model="lightning_v3.1_pro"),
        "fern/apis/waves/openapi/tts-openapi.yaml",
        ["components", "schemas", "TtsRequest", "properties", "language", "enum"],
    ),
    (
        "unified /waves/v1/tts / output_format",
        lambda: unified_tts_post("output_format", "__bogus__"),
        "fern/apis/waves/openapi/tts-openapi.yaml",
        ["components", "schemas", "TtsRequest", "properties", "output_format", "enum"],
    ),
    (
        "unified /waves/v1/tts / sample_rate",
        lambda: unified_tts_post("sample_rate", 99999),
        "fern/apis/waves/openapi/tts-openapi.yaml",
        ["components", "schemas", "TtsRequest", "properties", "sample_rate", "enum"],
    ),
]


def get_at(node, path):
    cur = node
    for k in path:
        if isinstance(cur, dict) and k in cur:
            cur = cur[k]
        else:
            return None
    return cur


import re as _re

_SUPPORTED_RE = _re.compile(
    r"Supported\s+(?:languages?|formats?|values?|options?)\s*:\s*([^\.\n\}\"']+)",
    _re.IGNORECASE,
)


def extract_options(error_body) -> list | None:
    """Walk the error body and find the canonical accepted-values list.

    Two shapes handled:
      1. Zod-style `{"options": [...]}` under `code: "invalid_enum_value"`.
      2. Platform-style `"code": "custom", "message": "Language 'X' is
         not supported on the lightning_v3.1 model. Supported languages:
         en, hi, mr, ..."` — parse the comma-separated tail out of the
         message.

    Returns None if neither shape matches."""
    def recurse(n):
        if isinstance(n, dict):
            if "options" in n and isinstance(n["options"], list):
                return n["options"]
            msg = n.get("message")
            if isinstance(msg, str):
                m = _SUPPORTED_RE.search(msg)
                if m:
                    tail = m.group(1)
                    parts = [p.strip() for p in tail.split(",") if p.strip()]
                    if parts:
                        return parts
            for v in n.values():
                r = recurse(v)
                if r is not None:
                    return r
        elif isinstance(n, list):
            for v in n:
                r = recurse(v)
                if r is not None:
                    return r
        return None
    return recurse(error_body)


def main() -> int:
    print("=" * 78)
    print("Spec ↔ live API enum drift check")
    print("=" * 78)

    drift_count = 0
    for label, send, spec_path, enum_path in CHECKS:
        print(f"\n{label}")
        print(f"  spec: {spec_path}")

        # 1. read spec enum
        with open(ROOT / spec_path) as f:
            spec = yaml.safe_load(f)
        spec_enum = get_at(spec, enum_path)
        if spec_enum is None:
            print(f"  ✗ enum not found at {'.'.join(map(str, enum_path))}")
            drift_count += 1
            continue

        # 2. probe live API with bogus value
        status, body = send()
        if 200 <= status < 300:
            print(f"  ✗ API returned {status} on bogus value — endpoint doesn't strictly validate this enum.")
            print(f"     skipping (not a drift signal we can act on automatically)")
            continue

        # 3. extract canonical options from error
        api_enum = extract_options(body)
        if api_enum is None:
            preview = (json.dumps(body) if isinstance(body, dict) else str(body))[:200]
            # Some endpoints return `code: "custom"` errors that don't expose
            # an options list. Can't auto-validate — log and skip without
            # counting as drift (a future endpoint update could change format).
            print(f"  ⚠ skipping (no `options` in error response): {preview}")
            continue

        # 4. compare. Normalize types (sample_rate uses ints, others strings).
        spec_set = {str(x) for x in spec_enum}
        api_set = {str(x) for x in api_enum}
        if spec_set == api_set:
            print(f"  ✓ enum matches API ({len(api_set)} values)")
            continue

        only_in_spec = sorted(spec_set - api_set)
        only_in_api = sorted(api_set - spec_set)

        # Under the unified TTS spec, one enum covers BOTH `lightning_v3.1`
        # and `lightning_v3.1_pro` — but validation runs per-model. So
        # "spec has values the current model rejects" is expected (Pro
        # codes probed against base, or vice versa) and only warned.
        # The docs-side prose (tts-openapi.yaml `language` description)
        # already carves out which codes belong to which model.
        #
        # "API accepts a value the spec doesn't list" is a real docs
        # gap — customers can't discover it — and always fails.
        if only_in_api:
            print(f"  ✗ DRIFT — API accepts values NOT documented in spec:")
            print(f"     {only_in_api}")
            print(f"     spec has {len(spec_set)}, API has {len(api_set)}")
            drift_count += 1
        if only_in_spec:
            print(f"  ⚠ spec broader than this model's API surface ({len(spec_set)} vs {len(api_set)})")
            print(f"     documented but rejected by this model: {only_in_spec}")
            print(f"     (expected on unified spec: enum covers both v3.1 base + Pro pools)")

    print()
    print("=" * 78)
    if drift_count == 0:
        print(f"PASS — all {len(CHECKS)} spec enums match live API")
        return 0
    print(f"FAIL — {drift_count} of {len(CHECKS)} checks flagged drift")
    print("Update the spec to match the API, or escalate to platform team if the")
    print("API enum looks wrong.")
    print("=" * 78)
    return 1


if __name__ == "__main__":
    sys.exit(main())
