"""Classify Pulse STT / Lightning TTS probe diffs as NEWSWORTHY or NOISE.

Reads the markdown diff reports produced by `diff.py --markdown`, sends them
to the Anthropic API with a domain-specific prompt, and emits JSON with a
verdict (NEWSWORTHY / NOISE / NONE) plus a short summary suitable for a
Slack DM body.

Why this exists
---------------
The api-flag-probe workflow already detects *that* a probe field changed,
but it can't tell if the change is signal (a real API behavior shift the
docs need to react to) or noise (test-clip variance, model retraining
drift, language-detection wobble). A blanket "any diff fires Slack" is
the worst of both worlds — it floods the channel with non-actionable
alerts and trains people to ignore the bot.

This step calls Claude with the diff content and the explicit
newsworthy/noise rules the team agreed on. NEWSWORTHY → Slack DM +
optional auto-PR. NOISE/NONE → workflow stays silent.

Usage:
    ANTHROPIC_API_KEY=... python3 scripts/probes/classify.py \\
        --stt-diff /tmp/diff-report.md \\
        --tts-diff /tmp/diff-tts-report.md \\
        --out-json /tmp/classification.json \\
        --run-url https://github.com/.../actions/runs/123
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-sonnet-4-6"

# Hard rules. Anything not on the NEWSWORTHY list is NOISE by definition.
# Keep this in lockstep with the criteria in the api-flag-probe routine
# prompt so the workflow and the (now-disabled) routine make the same
# call.
SYSTEM_PROMPT = """You classify weekly probe diffs from the Smallest AI docs CI.

You receive markdown diffs from two probes against the live API:
1. Pulse STT (speech-to-text) — formatting / language / keyword flags
2. Lightning v3.1 TTS — sync REST + SSE streaming surface

Return ONE of three verdicts plus a short rationale.

GOLDEN RULE
-----------
Any **spec-level change** the docs need to react to is NEWSWORTHY. That includes any of: a parameter being added / removed / renamed; a default value flipping; a response field being added / removed / renamed; an error code or status code changing; a default routing decision changing (e.g., what the server does when a parameter is omitted). Customer-facing samples that omit a param now hit a different default — every sample needs review. Treat default-value drift the same as a spec change.

NEWSWORTHY (Pulse STT)
- British-spelling flags `punctuation` or `capitalisation` now affect transcript output the way PR #116 specifies (https://github.com/smallest-inc/lightning-asr-offline/pull/116). Look at the `punctuation-false-british-pr116` and `capitalisation-false-british-pr116` test cases — if their transcripts now differ from the punctuated-American baseline, the British flags are wired.
- `format=false` cascades to disable ITN. Look at the `format-false-should-cascade-to-no-itn` case — `has_itn_currency`, `has_itn_date_or_time`, `has_pii_placeholder`, `has_pci_placeholder` ALL flip True→False with `looks_garbled` staying False.
- `saw_full_transcript_field` flipping on the `full-transcript-true` case (means the param now actually returns a field).
- **Default-value drift** — any change on a `*-defaults-*` test case (e.g., `lang-omitted-defaults-multi-eu`). Such cases probe what the server does when a parameter is OMITTED. A change here means the default flipped (real example: `language=auto` → `language=multi-eu`). Every doc sample that omits the param now hits the new default.
- New language codes appearing in `languages_seen` for any case (suggests the server's auto-detect scope expanded).
- `status_code` shifting from success to error (or vice versa) on any case — suggests a param became required, was deprecated, or validation tightened/loosened.
- `error_body` content changing materially on negative-test cases — suggests new validation rules or new error codes.

NEWSWORTHY (Lightning TTS)
- `status_code` change for any case (e.g. 200→4xx, 4xx→200).
- `content_type` change (e.g. audio/wav → audio/mpeg).
- `size_class` change (small audio → tiny error blob, or vice versa).
- `sse_saw_complete` flipping True/False.
- `sse_saw_event_audio` flipping True/False.
- **Default-value drift** — any change on a `*-default-*` case (e.g., `sync-default-pcm`). Means the server's response to "no extra params" shifted.

NOISE — do NOT classify as newsworthy
- `has_itn_currency` / `has_itn_date_or_time` toggling on a NON-defaults test case where no flag changed. The test text varied or model retraining drift; ITN itself didn't change. **(BUT: if the toggle is on a `*-defaults-*` case, that IS newsworthy — the default may have flipped.)**
- `looks_garbled` toggling on edge clips (model retraining drift).
- `languages_seen` narrowing from `{da,en}` → `{en}` on Pulse cases that send English audio (single-language detector wobble, not a behavior change). **(BUT: if a NEW language code appears, that IS newsworthy.)**
- `transcript_first120` / `transcript_len` differences (always noise — those fields are excluded from diff.py SHAPE_FIELDS anyway).
- New cases marked `<new case>` (test additions, not API changes).

NONE — both diffs are empty / the probe found nothing.

Output format: a SINGLE valid JSON object with these keys, nothing else:
{
  "verdict": "NEWSWORTHY" | "NOISE" | "NONE",
  "summary": "1-3 sentences describing what changed and why it matters (or why it's noise). Plain prose, no markdown headers.",
  "newsworthy_signals": ["<short phrase per newsworthy signal, empty if none>"],
  "doc_files_to_audit": ["<path per file the team should review, empty if none>"]
}

Be ruthless about NOISE. Almost every weekly diff is noise. Only fire NEWSWORTHY when the diff actually maps to one of the criteria above."""

USER_TEMPLATE = """Pulse STT diff:

```
{stt_diff}
```

Lightning TTS diff:

```
{tts_diff}
```

Run URL: {run_url}

Classify per the rules. Return only the JSON object."""


def call_anthropic(stt_diff: str, tts_diff: str, run_url: str, api_key: str) -> dict:
    body = {
        "model": MODEL,
        "max_tokens": 1024,
        "system": SYSTEM_PROMPT,
        "messages": [
            {
                "role": "user",
                "content": USER_TEMPLATE.format(
                    stt_diff=stt_diff or "(no diff — probe ran clean)",
                    tts_diff=tts_diff or "(no diff — probe ran clean)",
                    run_url=run_url or "(unknown)",
                ),
            }
        ],
    }
    req = urllib.request.Request(
        ANTHROPIC_URL,
        data=json.dumps(body).encode(),
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        method="POST",
    )
    # Don't catch HTTPError here — let it propagate so main() can apply
    # the degrade-to-NOISE policy uniformly. Other exceptions (network,
    # JSON parse) also bubble up and main() handles them too.
    with urllib.request.urlopen(req, timeout=60) as resp:
        payload = json.load(resp)
    text = "".join(b["text"] for b in payload["content"] if b["type"] == "text").strip()
    # Sometimes the model wraps JSON in ```json fences; strip them.
    if text.startswith("```"):
        text = text.strip("`").lstrip("json").strip()
    return json.loads(text)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stt-diff", required=True, help="path to Pulse STT diff markdown (from diff.py)")
    parser.add_argument("--tts-diff", required=True, help="path to Lightning TTS diff markdown (from diff.py)")
    parser.add_argument("--out-json", required=True, help="path to write the classification JSON")
    parser.add_argument("--run-url", default="", help="URL of the GH Actions run, used in the prompt")
    args = parser.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        # Fall back to NOISE so the workflow doesn't hard-fail when the
        # secret isn't set (e.g., on a fork). Operators see the warning in
        # the run log; nothing is sent to Slack.
        print("WARN: ANTHROPIC_API_KEY not set; defaulting to NOISE.", file=sys.stderr)
        result = {
            "verdict": "NOISE",
            "summary": "Classifier skipped — ANTHROPIC_API_KEY not set in workflow env.",
            "newsworthy_signals": [],
            "doc_files_to_audit": [],
        }
        Path(args.out_json).write_text(json.dumps(result, indent=2))
        return 0

    stt_diff = Path(args.stt_diff).read_text() if Path(args.stt_diff).exists() else ""
    tts_diff = Path(args.tts_diff).read_text() if Path(args.tts_diff).exists() else ""

    # Anthropic-side failures (billing/quota/rate-limit/transient outage)
    # should NOT crash the whole workflow — the diff is already in the run
    # summary + artifact. Degrade to NOISE with a clear "classifier
    # unavailable" summary so the operator sees the situation but the
    # workflow stays green.
    try:
        result = call_anthropic(stt_diff, tts_diff, args.run_url, api_key)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace") if not isinstance(e.fp, type(None)) else ""
        # Common billing/quota signal; keep the operator-visible summary
        # specific so it's clear what to do.
        kind = "billing/quota" if e.code == 400 and "credit balance" in body.lower() else f"HTTP {e.code}"
        print(f"WARN: Anthropic API {kind} error; degrading to NOISE.", file=sys.stderr)
        result = {
            "verdict": "NOISE",
            "summary": f"Classifier unavailable ({kind}). Diff is in the run summary + artifact for manual review. Anthropic raw error (truncated): {body[:300]}",
            "newsworthy_signals": [],
            "doc_files_to_audit": [],
        }
    except Exception as e:
        print(f"WARN: Classifier call failed ({type(e).__name__}: {e}); degrading to NOISE.", file=sys.stderr)
        result = {
            "verdict": "NOISE",
            "summary": f"Classifier unavailable ({type(e).__name__}). Diff is in the run summary + artifact for manual review.",
            "newsworthy_signals": [],
            "doc_files_to_audit": [],
        }

    # Validate shape — fail loudly if Claude returned something unexpected.
    for key in ("verdict", "summary", "newsworthy_signals", "doc_files_to_audit"):
        if key not in result:
            print(f"ERROR: classifier response missing key '{key}': {result}", file=sys.stderr)
            return 1
    if result["verdict"] not in ("NEWSWORTHY", "NOISE", "NONE"):
        print(f"ERROR: unexpected verdict '{result['verdict']}'", file=sys.stderr)
        return 1

    Path(args.out_json).write_text(json.dumps(result, indent=2))
    print(f"Verdict: {result['verdict']}")
    print(f"Summary: {result['summary']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
