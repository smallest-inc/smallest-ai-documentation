"""Live test for Pulse STT WebSocket `vad_events=true`.

Connects to the production Pulse STT streaming endpoint with `vad_events=true`,
streams a real audio file as 16 kHz mono PCM frames, captures the message
sequence, and asserts:

  1. At least one `speech_started` message is emitted.
  2. At least one `speech_ended` message is emitted.
  3. Both message types include `type`, `session_id`, `timestamp` fields with
     the documented shape (string, string, number).
  4. Normal `transcription` messages still arrive alongside the VAD events.

Run:

    export SMALLEST_API_KEY=...
    python3 scripts/spec-live-tests/vad_events_live_test.py

Exit 0 = all assertions passed, doc claims match prod. Exit 1 = at least
one assertion failed; output prints which.

Requires: `websockets>=14.0,<16.0`. The audio sample is fetched from the
public cookbook repo so the script is self-contained.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import urllib.request
import wave
from pathlib import Path

import websockets

SAMPLE_URL = (
    "https://github.com/smallest-inc/cookbook/raw/main/"
    "speech-to-text/getting-started/samples/audio.wav"
)
SAMPLE_PATH = Path("/tmp/vad_events_test_audio.wav")

WS_BASE = "wss://api.smallest.ai/waves/v1/stt/live"
CHUNK_MS = 200
TIMEOUT_S = 30


def ensure_sample() -> Path:
    if not SAMPLE_PATH.exists():
        print(f"Downloading sample audio -> {SAMPLE_PATH}")
        urllib.request.urlretrieve(SAMPLE_URL, SAMPLE_PATH)
    return SAMPLE_PATH


def pcm_frames(path: Path, chunk_ms: int) -> tuple[list[bytes], int]:
    """Read a mono 16-bit PCM WAV. Returns (frames, sample_rate)."""
    with wave.open(str(path), "rb") as wf:
        assert wf.getnchannels() == 1, f"expected mono, got {wf.getnchannels()}ch"
        assert wf.getsampwidth() == 2, f"expected 16-bit PCM, got {wf.getsampwidth()*8}-bit"
        sample_rate = wf.getframerate()
        raw = wf.readframes(wf.getnframes())
    bytes_per_chunk = int(sample_rate * (chunk_ms / 1000.0)) * 2
    frames = [raw[i : i + bytes_per_chunk] for i in range(0, len(raw), bytes_per_chunk)]
    return frames, sample_rate


async def stream_and_collect(
    api_key: str, audio_chunks: list[bytes], sample_rate: int
) -> list[dict]:
    qs = "&".join(
        [
            "model=pulse",
            "language=en",
            "encoding=linear16",
            f"sample_rate={sample_rate}",
            "vad_events=true",
        ]
    )
    url = f"{WS_BASE}?{qs}"
    headers = {"Authorization": f"Bearer {api_key}"}
    received: list[dict] = []

    async with websockets.connect(url, additional_headers=headers) as ws:
        async def send_audio():
            for chunk in audio_chunks:
                await ws.send(chunk)
                await asyncio.sleep(CHUNK_MS / 1000.0)
            await ws.send(json.dumps({"type": "close_stream"}))

        async def recv_messages():
            try:
                async for raw in ws:
                    if isinstance(raw, (bytes, bytearray)):
                        continue
                    try:
                        msg = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    received.append(msg)
                    if msg.get("is_last") is True:
                        break
            except websockets.ConnectionClosed:
                pass

        await asyncio.wait_for(
            asyncio.gather(send_audio(), recv_messages()), timeout=TIMEOUT_S
        )

    return received


def assert_doc_claims(messages: list[dict]) -> int:
    started = [m for m in messages if m.get("type") == "speech_started"]
    ended = [m for m in messages if m.get("type") == "speech_ended"]
    transcripts = [
        m
        for m in messages
        if "transcript" in m or m.get("type") == "transcription" or "is_final" in m
    ]

    failures: list[str] = []

    if not started:
        failures.append("expected ≥1 speech_started message, got 0")
    if not ended:
        failures.append("expected ≥1 speech_ended message, got 0")
    if not transcripts:
        failures.append("expected ≥1 transcription message, got 0")

    for label, sample in (("speech_started", started[0] if started else None),
                         ("speech_ended", ended[0] if ended else None)):
        if sample is None:
            continue
        if not isinstance(sample.get("type"), str):
            failures.append(f"{label}: 'type' missing or not a string")
        if not isinstance(sample.get("session_id"), str):
            failures.append(f"{label}: 'session_id' missing or not a string")
        if not isinstance(sample.get("timestamp"), (int, float)):
            failures.append(f"{label}: 'timestamp' missing or not a number")

    print()
    print(f"Captured {len(messages)} message(s):")
    print(f"  speech_started: {len(started)}")
    print(f"  speech_ended:   {len(ended)}")
    print(f"  transcription:  {len(transcripts)}")
    if started:
        print(f"  first speech_started: {json.dumps(started[0])}")
    if ended:
        print(f"  first speech_ended:   {json.dumps(ended[0])}")
    if transcripts:
        print(f"  first transcript:     {json.dumps(transcripts[0])[:140]}")

    if failures:
        print()
        print("FAIL — doc claims not met:")
        for f in failures:
            print(f"  - {f}")
        return 1

    print()
    print("OK — doc claims match prod.")
    return 0


async def main() -> int:
    api_key = os.environ.get("SMALLEST_API_KEY")
    if not api_key:
        print("SMALLEST_API_KEY env var required", file=sys.stderr)
        return 2

    path = ensure_sample()
    chunks, sample_rate = pcm_frames(path, CHUNK_MS)
    # Append ~1.5s of silence so the model emits `speech_ended` for the trailing
    # voiced region. Without it, the audio ends mid-utterance and no silence
    # boundary is detected — see the doc note on acoustic boundaries.
    silence_bytes = b"\x00\x00" * int(sample_rate * 1.5)
    bytes_per_chunk = int(sample_rate * (CHUNK_MS / 1000.0)) * 2
    silence_chunks = [
        silence_bytes[i : i + bytes_per_chunk]
        for i in range(0, len(silence_bytes), bytes_per_chunk)
    ]
    chunks = chunks + silence_chunks
    print(f"Audio: {len(chunks)} chunks of {CHUNK_MS}ms @ {sample_rate} Hz "
          f"(speech + {len(silence_chunks) * CHUNK_MS} ms trailing silence)")
    messages = await stream_and_collect(api_key, chunks, sample_rate)
    return assert_doc_claims(messages)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
