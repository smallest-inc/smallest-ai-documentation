"""Diff a fresh probe result JSON against the committed baseline.

Compares only the *shape* fields — flags whose change would be a real
behavior signal (param accepted, response field appeared/disappeared,
transcript noticeably garbled, ITN/redaction placeholders changed).
Ignores `transcript_first120` and `transcript_len` since those drift
naturally with model retraining.

Usage:
    python3 scripts/probes/diff.py BASELINE.json LIVE.json
    python3 scripts/probes/diff.py BASELINE.json LIVE.json --markdown

Exit 0: results match baseline.
Exit 1: any per-case shape change. Markdown report written to stdout.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Fields where a change indicates a real behavior shift, picked per
# service since each probe writes a different record shape. Diagnostic
# fields like `elapsed_ms`, `transcript_len`, `transcript_first120` are
# deliberately excluded — they drift naturally and are noise.
SHAPE_FIELDS_BY_SERVICE: dict[str, list[str]] = {
    "pulse-stt-ws": [
        "ok",
        "error",
        "saw_full_transcript_field",
        "has_pii_placeholder",
        "has_pci_placeholder",
        "has_itn_currency",
        "has_itn_date_or_time",
        "looks_garbled",
        "languages_seen",
    ],
    "lightning-tts": [
        "ok",
        "error",
        "status_code",
        "content_type",
        "size_class",
        "sse_saw_complete",
        "sse_saw_event_audio",
    ],
    "atoms": [
        "ok",
        "error",
        "status_code",
        "content_type",
        "envelope_keys",
        "envelope_status",
        "data_kind",
        "count_class",
        "data_keys",
        "item_keys_first",
    ],
}

# Backwards-compat default — used when the live JSON has no `service`
# key (old probes from before this dispatch existed).
DEFAULT_SHAPE_FIELDS = SHAPE_FIELDS_BY_SERVICE["pulse-stt-ws"]


def index_by_label(payload: dict) -> dict[str, dict]:
    return {r["label"]: r for r in payload["results"]}


def diff_records(baseline: dict, live: dict, shape_fields: list[str]) -> list[dict]:
    """Return list of {label, field, baseline, live} for each diff."""
    diffs = []
    for field in shape_fields:
        b = baseline.get(field)
        l = live.get(field)
        if b != l:
            diffs.append(
                {
                    "label": baseline["label"],
                    "field": field,
                    "baseline": b,
                    "live": l,
                }
            )
    return diffs


# Doc files most likely to need an update when a particular service's
# probe surfaces a behavior change. Reported in the markdown output so
# whoever triages the diff knows where to look first.
DOCS_TO_AUDIT_BY_SERVICE: dict[str, list[str]] = {
    "pulse-stt-ws": [
        "`fern/apis/waves-v4/overrides/pulse-stt-ws-overrides.yml`",
        "`fern/apis/waves/asyncapi/pulse-stt-ws.yaml`",
        "`fern/apis/waves/asyncapi/pulse-stt-ws-overrides.yml`",
        "`fern/apis/waves/openapi/pulse-stt-openapi.yaml`",
        "`fern/products/waves/pages/v4.0.0/api-references/pulse-stt-ws.mdx`",
        "`fern/products/waves/pages/v4.0.0/speech-to-text/realtime/response-format.mdx`",
        "`fern/products/waves/pages/v4.0.0/speech-to-text/features/word-boosting.mdx`",
        "New changelog entry under `fern/products/waves/pages/v4.0.0/changelog-entries/`",
    ],
    "lightning-tts": [
        "`fern/apis/waves/openapi/lightning-v3.1-openapi.yaml`",
        "`fern/apis/waves/asyncapi/lightning-v3.1-ws.yaml`",
        "`fern/products/waves/pages/v4.0.0/text-to-speech/`",
        "New changelog entry under `fern/products/waves/pages/v4.0.0/changelog-entries/`",
    ],
    "atoms": [
        "`fern/apis/atoms/openapi/openapi.yaml`",
        "`fern/products/atoms/pages/`",
        "New changelog entry under `fern/products/atoms/pages/intro/reference/changelog-entries/`",
    ],
}


SERVICE_DISPLAY_NAMES: dict[str, str] = {
    "pulse-stt-ws": "Pulse STT",
    "lightning-tts": "Lightning TTS",
    "atoms": "Atoms",
}


def render_markdown(all_diffs: list[dict], live: dict) -> str:
    service = live.get("service") or "probe"
    label = SERVICE_DISPLAY_NAMES.get(service, "Probe")
    if not all_diffs:
        return f"✅ {label}: no behavior change vs baseline."
    lines = [f"⚠️ **{label}: behavior change detected**", ""]
    by_label: dict[str, list[dict]] = {}
    for d in all_diffs:
        by_label.setdefault(d["label"], []).append(d)
    for case_label, items in sorted(by_label.items()):
        lines.append(f"### `{case_label}`")
        for it in items:
            lines.append(
                f"- **{it['field']}**: baseline=`{it['baseline']}` -> live=`{it['live']}`"
            )
        lines.append("")
    docs = DOCS_TO_AUDIT_BY_SERVICE.get(service, [])
    if docs:
        lines.append("**Doc files to audit if this signals a real surface change:**")
        lines.append("")
        for d in docs:
            lines.append(f"- {d}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("baseline", help="committed baseline JSON")
    parser.add_argument("live", help="freshly probed JSON")
    parser.add_argument("--markdown", action="store_true", help="print markdown report")
    args = parser.parse_args()

    baseline = json.loads(Path(args.baseline).read_text())
    live = json.loads(Path(args.live).read_text())

    if baseline.get("schema_version") != live.get("schema_version"):
        print(
            f"Schema version differs: baseline={baseline.get('schema_version')} "
            f"live={live.get('schema_version')}. Cannot diff.",
            file=sys.stderr,
        )
        return 2

    # Pick the right SHAPE_FIELDS list per service. Both files should
    # agree on `service`; if they don't, the probe and baseline are out
    # of sync and we bail.
    service = baseline.get("service") or live.get("service")
    if baseline.get("service") and live.get("service") and baseline["service"] != live["service"]:
        print(
            f"Service differs: baseline={baseline.get('service')} "
            f"live={live.get('service')}. Cannot diff.",
            file=sys.stderr,
        )
        return 2
    shape_fields = SHAPE_FIELDS_BY_SERVICE.get(service or "", DEFAULT_SHAPE_FIELDS)

    b_idx = index_by_label(baseline)
    l_idx = index_by_label(live)

    all_diffs = []
    for label in sorted(set(b_idx) | set(l_idx)):
        if label not in b_idx:
            all_diffs.append(
                {"label": label, "field": "<new case>", "baseline": "(none)", "live": "(present)"}
            )
            continue
        if label not in l_idx:
            all_diffs.append(
                {"label": label, "field": "<missing case>", "baseline": "(present)", "live": "(none)"}
            )
            continue
        all_diffs.extend(diff_records(b_idx[label], l_idx[label], shape_fields))

    if args.markdown:
        print(render_markdown(all_diffs, live))
    else:
        if not all_diffs:
            print("OK: no behavior change.")
        else:
            for d in all_diffs:
                print(json.dumps(d))

    return 0 if not all_diffs else 1


if __name__ == "__main__":
    sys.exit(main())
