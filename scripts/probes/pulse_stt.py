"""Pulse STT WebSocket — formatting / language / keyword flag probe.

For each flag combination of interest, opens a WebSocket session, streams
the same demo audio, and records observable behavior:

- Did the request succeed without error?
- Is the response transcript empty, populated, or noticeably garbled?
- Is `language` echoed back in the final?
- Is `full_transcript` returned (it shouldn't be — server ignores the flag)?
- Are PII / PCI / ITN placeholders present in the transcript?
- How many `is_final` chunks fired and what was the largest? (catches
  `finalize_on_words=false` regressions and `max_words` cap regressions)
- Did any response carry `from_finalize: true`? (catches regressions
  where the manual finalize control message stops being labeled)

The output is one canonical JSON record per combination. The diff layer
(`diff.py`) compares against a committed baseline and flags any change.

Usage:
    SMALLEST_API_KEY=... python3 scripts/probes/pulse_stt.py [--out FILE]

Prints the JSON records to stdout, or writes to --out if provided.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from urllib.parse import urlencode

import requests
import websockets

BASE_WS_URL = "wss://api.smallest.ai/waves/v1/pulse/get_text"
SAMPLE_URL = (
    "https://github.com/smallest-inc/smallest-ai-documentation/raw/main/"
    "fern/products/waves/pages/audio/pulse-feature-demo.wav"
)

# Test cases: each entry is (label, query-params dict). Labels are the
# stable key in the baseline JSON — do not rename without updating the
# baseline.
TEST_CASES: list[tuple[str, dict]] = [
    (
        "baseline-en",
        {"language": "en", "encoding": "linear16", "sample_rate": "24000"},
    ),
    (
        "lang-omitted-defaults-multi-eu",
        {"encoding": "linear16", "sample_rate": "24000"},
    ),
    (
        "lang-multi-eu-explicit",
        {"language": "multi-eu", "encoding": "linear16", "sample_rate": "24000"},
    ),
    (
        "lang-multi",
        {"language": "multi", "encoding": "linear16", "sample_rate": "24000"},
    ),
    # Note: multi-indic and multi-asian are only available on the
    # pre-recorded HTTP endpoint, not this WebSocket endpoint. We don't
    # probe them here — they belong in a future pre-recorded probe.
    (
        "full-transcript-true-should-be-ignored",
        {
            "language": "en",
            "encoding": "linear16",
            "sample_rate": "24000",
            "full_transcript": "true",
        },
    ),
    (
        "format-false-should-disable-pnc-but-not-itn",
        {
            "language": "en",
            "encoding": "linear16",
            "sample_rate": "24000",
            "format": "false",
            "itn_normalize": "true",
        },
    ),
    (
        "punctuate-false-american",
        {
            "language": "en",
            "encoding": "linear16",
            "sample_rate": "24000",
            "punctuate": "false",
        },
    ),
    (
        "capitalize-false-american",
        {
            "language": "en",
            "encoding": "linear16",
            "sample_rate": "24000",
            "capitalize": "false",
        },
    ),
    (
        "punctuation-false-british-pr116",
        {
            "language": "en",
            "encoding": "linear16",
            "sample_rate": "24000",
            "punctuation": "false",
        },
    ),
    (
        "capitalisation-false-british-pr116",
        {
            "language": "en",
            "encoding": "linear16",
            "sample_rate": "24000",
            "capitalisation": "false",
        },
    ),
    (
        "redact-pii-pci-itn",
        {
            "language": "en",
            "encoding": "linear16",
            "sample_rate": "24000",
            "redact_pii": "true",
            "redact_pci": "true",
            "itn_normalize": "true",
        },
    ),
    (
        "keywords-string-format-correct",
        {
            "language": "en",
            "encoding": "linear16",
            "sample_rate": "24000",
            "keywords": "I:20,smiling:26",
        },
    ),
    (
        "keywords-array-stringified-wrong-format",
        {
            "language": "en",
            "encoding": "linear16",
            "sample_rate": "24000",
            "keywords": '["I:20,smiling:26"]',
        },
    ),
    # Finalize-control flags. Three regressions to guard against:
    #   1. `finalize_on_words=false` stops suppressing auto-finalize
    #      → is_final_count climbs back up to baseline.
    #   2. `max_words=20` stops capping the residual end transcript
    #      → max_is_final_word_count exceeds 20.
    #   3. `from_finalize: true` stops appearing on responses to manual
    #      `{"type":"finalize"}` → saw_from_finalize_field flips False.
    (
        "finalize-on-words-false-suppresses-auto",
        {
            "language": "en",
            "encoding": "linear16",
            "sample_rate": "24000",
            "finalize_on_words": "false",
        },
    ),
    (
        "max-words-20-soft-cap",
        {
            "language": "en",
            "encoding": "linear16",
            "sample_rate": "24000",
            "max_words": "20",
        },
    ),
    (
        "from-finalize-presence-on-manual",
        {
            "language": "en",
            "encoding": "linear16",
            "sample_rate": "24000",
            "finalize_on_words": "false",
            # send_finalize_at_chunk consumed by run_one() — not a server
            # param. Stripped before the URL is built.
            "_send_finalize_at_chunk": 30,
        },
    ),
]


async def run_one(label: str, params: dict, audio: bytes, api_key: str) -> dict:
    # Strip non-server keys (e.g. _send_finalize_at_chunk is consumed
    # locally to schedule a manual finalize message mid-stream).
    server_params = {k: v for k, v in params.items() if not k.startswith("_")}
    send_finalize_at_chunk = params.get("_send_finalize_at_chunk")

    qs = urlencode(server_params)
    url = f"{BASE_WS_URL}?{qs}" if qs else BASE_WS_URL
    headers = {"Authorization": f"Bearer {api_key}"}

    finals: list[dict] = []
    saw_full_transcript_field = False
    saw_from_finalize_field = False
    error: str | None = None

    try:
        async with websockets.connect(url, additional_headers=headers, open_timeout=10) as ws:

            async def sender():
                step = 4096
                chunks_sent = 0
                for i in range(0, len(audio), step):
                    try:
                        await ws.send(audio[i : i + step])
                    except websockets.ConnectionClosed:
                        return
                    chunks_sent += 1
                    await asyncio.sleep(0.04)
                    # Send manual finalize control message at the
                    # configured chunk index, if any. Used by the
                    # from-finalize-presence test case.
                    if send_finalize_at_chunk is not None and chunks_sent == send_finalize_at_chunk:
                        try:
                            await ws.send(json.dumps({"type": "finalize"}))
                        except websockets.ConnectionClosed:
                            return
                try:
                    await ws.send(json.dumps({"type": "close_stream"}))
                except websockets.ConnectionClosed:
                    pass

            send_task = asyncio.create_task(sender())
            try:
                while True:
                    msg = await asyncio.wait_for(ws.recv(), timeout=45)
                    data = json.loads(msg)
                    if "full_transcript" in data:
                        saw_full_transcript_field = True
                    if data.get("from_finalize") is True:
                        saw_from_finalize_field = True
                    if data.get("status") == "error" or data.get("error"):
                        error = json.dumps(data)[:200]
                    if data.get("is_final"):
                        finals.append(
                            {
                                "transcript": data.get("transcript", ""),
                                "language": data.get("language"),
                            }
                        )
                    if data.get("is_last"):
                        break
            except asyncio.TimeoutError:
                error = "recv timeout"
            send_task.cancel()
            try:
                await send_task
            except asyncio.CancelledError:
                pass
    except Exception as e:
        error = f"{type(e).__name__}: {str(e)[:200]}"

    # Reduce finals to a stable summary
    joined = "".join(f["transcript"] or "" for f in finals).strip()
    languages = sorted({f["language"] for f in finals if f["language"]})

    # Heuristic shape signals — checked by the diff layer to detect
    # behavior changes without being too fragile to model retraining.
    has_pii_placeholder = "[FIRSTNAME_" in joined or "[LASTNAME_" in joined
    has_pci_placeholder = "[CREDITCARDCVV_" in joined
    has_itn_currency = "$" in joined
    has_itn_date = "[DATE_" in joined or any(c in joined for c in ["[TIME_"])
    looks_garbled = (
        joined.count("⁇") > 5
        or joined.count("'I") > 5
        or joined.count('"I') > 5
    )

    is_final_count = len(finals)
    word_counts = [len((f["transcript"] or "").split()) for f in finals]
    max_is_final_word_count = max(word_counts) if word_counts else 0

    return {
        "label": label,
        "params": {k: v for k, v in params.items() if not k.startswith("_")},
        "ok": error is None,
        "error": error,
        "transcript_len": len(joined),
        "transcript_first120": joined[:120],
        "languages_seen": languages,
        "saw_full_transcript_field": saw_full_transcript_field,
        "saw_from_finalize_field": saw_from_finalize_field,
        "is_final_count": is_final_count,
        "max_is_final_word_count": max_is_final_word_count,
        "has_pii_placeholder": has_pii_placeholder,
        "has_pci_placeholder": has_pci_placeholder,
        "has_itn_currency": has_itn_currency,
        "has_itn_date_or_time": has_itn_date,
        "looks_garbled": looks_garbled,
    }


async def main_async(out_path: str | None) -> None:
    api_key = os.environ["SMALLEST_API_KEY"]

    # Fetch the demo audio once — every test case streams the same bytes.
    print(f"Downloading demo audio: {SAMPLE_URL}", file=sys.stderr)
    resp = requests.get(SAMPLE_URL, timeout=30)
    resp.raise_for_status()
    raw = resp.content
    if raw[:4] != b"RIFF":
        raise RuntimeError(
            f"Sample audio at {SAMPLE_URL} is not a RIFF WAV "
            f"(got {raw[:8]!r}). Has the file moved?"
        )
    audio = raw[44:]  # skip 44-byte WAV header

    results = []
    for label, params in TEST_CASES:
        print(f"  probing: {label}", file=sys.stderr)
        rec = await run_one(label, params, audio, api_key)
        results.append(rec)

    output = {
        "schema_version": 1,
        "service": "pulse-stt-ws",
        "endpoint": BASE_WS_URL,
        "results": results,
    }
    blob = json.dumps(output, indent=2, sort_keys=True)
    if out_path:
        with open(out_path, "w") as f:
            f.write(blob + "\n")
        print(f"Wrote {out_path}", file=sys.stderr)
    else:
        print(blob)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", help="Write results JSON to this path instead of stdout")
    args = parser.parse_args()
    asyncio.run(main_async(args.out))


if __name__ == "__main__":
    main()
