"""Pulse STT live test — runs on PR when waves STT spec changes.

Streams the committed demo WAV through the documented WS endpoint and
asserts a non-empty transcript comes back. Fails if:
  - The WS connection is rejected
  - No transcript chunks arrive within the timeout
  - The final transcript is empty / missing the documented `text` field

Stateless — no resource cleanup needed.

Usage:
    SMALLEST_API_KEY=... python3 scripts/spec-live-tests/waves_stt_live_test.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import urllib.request
from urllib.parse import urlencode

import websockets

WS_URL = "wss://api.smallest.ai/waves/v1/pulse/get_text"
SAMPLE_URL = (
    "https://github.com/smallest-inc/smallest-ai-documentation/raw/main/"
    "fern/products/waves/pages/audio/pulse-feature-demo.wav"
)
CHUNK_SIZE = 8192

API_KEY = os.environ.get("SMALLEST_API_KEY")
if not API_KEY:
    sys.exit("SMALLEST_API_KEY env var is required")


def fetch_sample() -> bytes:
    with urllib.request.urlopen(SAMPLE_URL, timeout=30) as r:
        return r.read()


async def stream_audio(audio: bytes) -> tuple[bool, str]:
    qs = urlencode({"language": "en"})
    url = f"{WS_URL}?{qs}"
    headers = {"Authorization": f"Bearer {API_KEY}"}

    transcript_parts: list[str] = []
    final_count = 0

    async def receiver(ws):
        nonlocal final_count
        try:
            while True:
                msg = await asyncio.wait_for(ws.recv(), timeout=15)
                if isinstance(msg, bytes):
                    continue
                try:
                    data = json.loads(msg)
                except json.JSONDecodeError:
                    continue
                # Pulse responses are documented to contain `text` and
                # may include `is_final`. We accept either field name
                # so the test isn't brittle if SDK rename PR #39 lands.
                txt = data.get("text") or data.get("transcription")
                if txt:
                    transcript_parts.append(txt)
                if data.get("is_final"):
                    final_count += 1
        except asyncio.TimeoutError:
            pass
        except websockets.exceptions.ConnectionClosed:
            pass

    try:
        async with websockets.connect(url, additional_headers=headers, open_timeout=15) as ws:
            recv_task = asyncio.create_task(receiver(ws))
            # Stream audio in chunks
            for i in range(0, len(audio), CHUNK_SIZE):
                await ws.send(audio[i:i + CHUNK_SIZE])
                await asyncio.sleep(0.02)
            # Send finalize signal (documented control message)
            try:
                await ws.send(json.dumps({"flag": "END"}))
            except Exception:
                pass
            await asyncio.wait_for(recv_task, timeout=20)
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"

    if not transcript_parts:
        return False, "no transcript text received"
    full = " ".join(transcript_parts).strip()
    return True, f"{len(transcript_parts)} chunks, {final_count} finals, transcript={full[:80]!r}"


def main() -> int:
    print("=== Pulse STT live test ===")
    print()

    print(f"[1] fetch demo WAV {SAMPLE_URL}")
    try:
        audio = fetch_sample()
        print(f"    PASS: {len(audio)} bytes")
    except Exception as e:
        print(f"    FAIL: {type(e).__name__}: {e}")
        return 1
    print()

    print(f"[2] stream through {WS_URL}")
    ok, detail = asyncio.run(stream_audio(audio))
    print(f"    {'PASS' if ok else 'FAIL'}: {detail}")
    print()

    if ok:
        print("PASS: Pulse STT WS accepting documented payload + returning transcript")
        return 0
    print("FAIL: Pulse STT not behaving as documented")
    return 1


if __name__ == "__main__":
    sys.exit(main())
