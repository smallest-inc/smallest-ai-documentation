"""Lightning v3.1 TTS — sync REST + SSE streaming flag probe.

For each parameter combination of interest, calls the live API and
records observable shape:

- Did the request succeed?
- What HTTP status / Content-Type came back?
- Is the response payload non-empty and the right size class?
- Does the SSE stream emit chunks and a final complete signal?

Output is one canonical JSON record per case. The diff layer
(`diff.py`) compares against a committed baseline and flags any change.

Why this exists
---------------
Same rationale as the Pulse STT probe: the API can change defaults,
silently accept-then-ignore params, or shift response shape, and the
docs only catch up after a customer reports a broken example. A weekly
probe surfaces these without anyone having to remember to look.

Usage:
    SMALLEST_API_KEY=... python3 scripts/probes/lightning_tts.py [--out FILE]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

import requests

SYNC_ENDPOINT = "https://api.smallest.ai/waves/v1/lightning-v3.1/get_speech"
SSE_ENDPOINT = "https://api.smallest.ai/waves/v1/lightning-v3.1/stream"

DEFAULT_TEXT = "Modern problems require modern solutions."

# Each case is (label, mode, body). `mode` selects which transport.
# Labels are the stable key in the baseline JSON — do not rename
# without re-baselining.
TEST_CASES: list[tuple[str, str, dict]] = [
    # --- Sync ---
    (
        "sync-default-pcm",
        "sync",
        {"text": DEFAULT_TEXT, "voice_id": "magnus", "sample_rate": 24000},
    ),
    (
        "sync-output-format-wav",
        "sync",
        {"text": DEFAULT_TEXT, "voice_id": "magnus", "sample_rate": 24000, "output_format": "wav"},
    ),
    (
        "sync-output-format-mp3",
        "sync",
        {"text": DEFAULT_TEXT, "voice_id": "magnus", "sample_rate": 24000, "output_format": "mp3"},
    ),
    (
        "sync-output-format-mulaw",
        "sync",
        {"text": DEFAULT_TEXT, "voice_id": "magnus", "sample_rate": 8000, "output_format": "mulaw"},
    ),
    (
        "sync-sample-rate-44100",
        "sync",
        {"text": DEFAULT_TEXT, "voice_id": "magnus", "sample_rate": 44100, "output_format": "wav"},
    ),
    (
        "sync-speed-1.5",
        "sync",
        {"text": DEFAULT_TEXT, "voice_id": "magnus", "sample_rate": 24000, "speed": 1.5},
    ),
    (
        "sync-language-auto",
        "sync",
        {"text": DEFAULT_TEXT, "voice_id": "magnus", "sample_rate": 24000, "language": "auto"},
    ),
    (
        "sync-language-en-explicit",
        "sync",
        {"text": DEFAULT_TEXT, "voice_id": "magnus", "sample_rate": 24000, "language": "en"},
    ),
    (
        "sync-invalid-voice-id",
        "sync",
        {"text": DEFAULT_TEXT, "voice_id": "this-voice-does-not-exist-2026", "sample_rate": 24000},
    ),
    # --- SSE streaming ---
    (
        "sse-default",
        "sse",
        {"text": DEFAULT_TEXT, "voice_id": "magnus", "sample_rate": 24000},
    ),
    (
        "sse-mp3",
        "sse",
        {"text": DEFAULT_TEXT, "voice_id": "magnus", "sample_rate": 24000, "output_format": "mp3"},
    ),
]


def size_class(n_bytes: int) -> str:
    """Coarse bucket — `tiny` for error blobs, `small/medium/large` for audio.

    We don't care about exact byte counts week-to-week (audio compression
    drifts), only the order of magnitude. Bucketing avoids false-positive
    diffs on transient byte-count changes.
    """
    if n_bytes < 256:
        return "tiny"
    if n_bytes < 50_000:
        return "small"
    if n_bytes < 500_000:
        return "medium"
    return "large"


def probe_sync(body: dict, api_key: str) -> dict:
    started = time.monotonic()
    try:
        r = requests.post(
            SYNC_ENDPOINT,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=body,
            timeout=60,
        )
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}
    elapsed_ms = int((time.monotonic() - started) * 1000)
    rec: dict = {
        "ok": r.ok,
        "status_code": r.status_code,
        "elapsed_ms": elapsed_ms,
        "content_type": r.headers.get("Content-Type", ""),
        "content_length_bytes": len(r.content),
    }
    if r.ok and r.content:
        rec["payload_first8_hex"] = r.content[:8].hex()
        rec["size_class"] = size_class(len(r.content))
    elif not r.ok:
        try:
            rec["error_body"] = r.text[:300]
        except Exception:
            rec["error_body"] = "(unreadable)"
        rec["size_class"] = size_class(len(r.content))
    return rec


def probe_sse(body: dict, api_key: str) -> dict:
    """Probe the SSE streaming endpoint.

    Wire format (verified live as of 2026-04-30): per-chunk frames are
    `event: audio` followed by `data: {"audio": "<base64-pcm>"}`, then
    a single terminator `data: {"status":"200","done":true}` (no
    event: line). Older docs incorrectly assumed the legacy nested
    shape `data: {"status":"chunk","data":{"audio":...}}` — we tolerate
    that too in case the API ever switches back.
    """
    started = time.monotonic()
    try:
        r = requests.post(
            SSE_ENDPOINT,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
            },
            json=body,
            stream=True,
            timeout=60,
        )
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}
    rec: dict = {
        "ok": r.ok,
        "status_code": r.status_code,
        "content_type": r.headers.get("Content-Type", ""),
    }
    if not r.ok:
        rec["error_body"] = r.text[:300]
        return rec
    chunk_count = 0
    saw_complete = False
    bytes_seen = 0
    saw_event_audio = False
    for raw in r.iter_lines():
        if not raw:
            continue
        try:
            line = raw.decode() if isinstance(raw, bytes) else raw
        except Exception:
            continue
        if line.startswith("event: audio"):
            saw_event_audio = True
            continue
        if not line.startswith("data:"):
            continue
        try:
            payload = json.loads(line.split(":", 1)[1].lstrip())
        except json.JSONDecodeError:
            continue
        if payload.get("done"):
            saw_complete = True
            break
        if "audio" in payload:
            chunk_count += 1
            bytes_seen += len(payload["audio"] or "")
        # Tolerate legacy nested shape if the API ever switches back.
        elif payload.get("status") == "chunk":
            chunk_count += 1
            bytes_seen += len(payload.get("data", {}).get("audio", "") or "")
        elif payload.get("status") == "complete":
            saw_complete = True
            break
        if chunk_count > 200:
            # Safety cap; we only care that streaming works, not the full payload.
            break
    rec["elapsed_ms"] = int((time.monotonic() - started) * 1000)
    rec["sse_chunk_count"] = chunk_count
    rec["sse_saw_complete"] = saw_complete
    rec["sse_saw_event_audio"] = saw_event_audio
    rec["sse_total_audio_b64_chars"] = bytes_seen
    return rec


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out")
    args = parser.parse_args()

    api_key = os.environ["SMALLEST_API_KEY"]
    results = []
    for label, mode, body in TEST_CASES:
        print(f"  probing: {label} ({mode})", file=sys.stderr)
        if mode == "sync":
            rec = probe_sync(body, api_key)
        elif mode == "sse":
            rec = probe_sse(body, api_key)
        else:
            raise RuntimeError(f"unknown mode: {mode}")
        results.append({"label": label, "mode": mode, "params": body, **rec})

    output = {
        "schema_version": 1,
        "service": "lightning-tts",
        "endpoints": {"sync": SYNC_ENDPOINT, "sse": SSE_ENDPOINT},
        "results": results,
    }
    blob = json.dumps(output, indent=2, sort_keys=True)
    if args.out:
        with open(args.out, "w") as f:
            f.write(blob + "\n")
        print(f"Wrote {args.out}", file=sys.stderr)
    else:
        print(blob)


if __name__ == "__main__":
    main()
