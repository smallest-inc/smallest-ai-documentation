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

# Fields where a change indicates a real behavior shift. Order matters
# only for diff-output stability.
SHAPE_FIELDS = [
    "ok",
    "error",
    "saw_full_transcript_field",
    "saw_from_finalize_field",
    "is_final_count",
    "max_is_final_word_count",
    "has_pii_placeholder",
    "has_pci_placeholder",
    "has_itn_currency",
    "has_itn_date_or_time",
    "looks_garbled",
    "languages_seen",
]


def index_by_label(payload: dict) -> dict[str, dict]:
    return {r["label"]: r for r in payload["results"]}


def diff_records(baseline: dict, live: dict) -> list[dict]:
    """Return list of {label, field, baseline, live} for each diff."""
    diffs = []
    for field in SHAPE_FIELDS:
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


def render_markdown(all_diffs: list[dict], live: dict) -> str:
    if not all_diffs:
        return "✅ Pulse STT probe: no behavior change vs baseline."
    lines = ["⚠️ **Pulse STT probe: behavior change detected**", ""]
    by_label: dict[str, list[dict]] = {}
    for d in all_diffs:
        by_label.setdefault(d["label"], []).append(d)
    for label, items in sorted(by_label.items()):
        lines.append(f"### `{label}`")
        for it in items:
            lines.append(
                f"- **{it['field']}**: baseline=`{it['baseline']}` -> live=`{it['live']}`"
            )
        lines.append("")
    lines.append("**Doc files to audit if this signals a real surface change:**")
    lines.append("")
    lines.append("- `fern/apis/waves-v4/overrides/pulse-stt-ws-overrides.yml`")
    lines.append("- `fern/apis/waves/asyncapi/pulse-stt-ws.yaml`")
    lines.append("- `fern/apis/waves/asyncapi/pulse-stt-ws-overrides.yml`")
    lines.append("- `fern/apis/waves/openapi/pulse-stt-openapi.yaml`")
    lines.append("- `fern/products/waves/pages/v4.0.0/api-references/pulse-stt-ws.mdx`")
    lines.append("- `fern/products/waves/pages/v4.0.0/speech-to-text/realtime/response-format.mdx`")
    lines.append("- `fern/products/waves/pages/v4.0.0/speech-to-text/features/word-boosting.mdx`")
    lines.append(
        "- New changelog entry under `fern/products/waves/pages/v4.0.0/changelog-entries/`"
    )
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
        all_diffs.extend(diff_records(b_idx[label], l_idx[label]))

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
