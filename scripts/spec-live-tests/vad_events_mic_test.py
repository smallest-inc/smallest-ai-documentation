"""Interactive live-mic test for Pulse STT `vad_events=true`.

Opens the Pulse STT WebSocket with `vad_events=true`, captures audio from
the default microphone at 16 kHz mono 16-bit PCM, streams it in 200ms
chunks, and prints `speech_started` / `speech_ended` events and partial
transcripts as they arrive. Press Ctrl+C to stop.

Run:

    pip install 'websockets>=14.0,<16.0' sounddevice numpy
    export SMALLEST_API_KEY=...
    python3 scripts/spec-live-tests/vad_events_mic_test.py

Output format:

    [ 0.064s] ▶ speech_started
    [ 0.342s] partial: hello
    [ 0.821s] FINAL: hello world
    [ 2.180s] ■ speech_ended
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
import sys
import time

import numpy as np
import sounddevice as sd
import websockets

WS_BASE = "wss://api.smallest.ai/waves/v1/stt/live"
SAMPLE_RATE = 16000
CHUNK_MS = 200
SAMPLES_PER_CHUNK = SAMPLE_RATE * CHUNK_MS // 1000  # 3200 samples
STOP = asyncio.Event()


def fmt(t0: float) -> str:
    return f"[{time.monotonic() - t0:6.3f}s]"


async def mic_to_ws(ws, audio_q: asyncio.Queue) -> None:
    while not STOP.is_set():
        chunk: bytes = await audio_q.get()
        if chunk is None:
            break
        try:
            await ws.send(chunk)
        except websockets.ConnectionClosed:
            break


async def ws_to_stdout(ws, t0: float) -> None:
    async for raw in ws:
        if isinstance(raw, (bytes, bytearray)):
            continue
        try:
            m = json.loads(raw)
        except json.JSONDecodeError:
            continue
        t = m.get("type")
        if t == "speech_started":
            print(f"{fmt(t0)} ▶ speech_started   server_ts={m['timestamp']:.3f}s")
        elif t == "speech_ended":
            print(f"{fmt(t0)} ■ speech_ended     server_ts={m['timestamp']:.3f}s")
        else:
            tag = "FINAL " if m.get("is_final") else "partial"
            text = m.get("transcription") or m.get("transcript")
            if text:
                print(f"{fmt(t0)} {tag}: {text}")


async def run(api_key: str) -> int:
    qs = "&".join(
        [
            "model=pulse",
            "language=en",
            "encoding=linear16",
            f"sample_rate={SAMPLE_RATE}",
            "vad_events=true",
        ]
    )
    url = f"{WS_BASE}?{qs}"
    headers = {"Authorization": f"Bearer {api_key}"}

    audio_q: asyncio.Queue = asyncio.Queue(maxsize=100)
    loop = asyncio.get_running_loop()

    def on_audio(indata, frames, time_info, status):
        if status:
            print(f"  [mic] {status}", file=sys.stderr)
        # int16 mono -> bytes
        pcm = (indata[:, 0] * 32767.0).clip(-32768, 32767).astype(np.int16).tobytes()
        try:
            loop.call_soon_threadsafe(audio_q.put_nowait, pcm)
        except asyncio.QueueFull:
            pass

    print(f"Connecting to Pulse STT (vad_events=true) at {SAMPLE_RATE} Hz...")
    async with websockets.connect(url, additional_headers=headers) as ws:
        print("Connected. Speak into the default microphone. Ctrl+C to stop.")
        print()
        t0 = time.monotonic()

        stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="float32",
            blocksize=SAMPLES_PER_CHUNK,
            callback=on_audio,
        )
        stream.start()

        try:
            await asyncio.gather(
                mic_to_ws(ws, audio_q),
                ws_to_stdout(ws, t0),
            )
        finally:
            stream.stop()
            stream.close()
            try:
                await ws.send(json.dumps({"type": "close_stream"}))
            except Exception:
                pass

    return 0


def install_sigint() -> None:
    def _handler(*_):
        if not STOP.is_set():
            print("\nStopping...")
            STOP.set()

    signal.signal(signal.SIGINT, _handler)


def main() -> int:
    api_key = os.environ.get("SMALLEST_API_KEY")
    if not api_key:
        print("SMALLEST_API_KEY env var required", file=sys.stderr)
        return 2
    install_sigint()
    try:
        return asyncio.run(run(api_key))
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
