"""Prepare audio + event-capture fixtures for the VAD events interactive demo.

Generates 3 audio variants and runs each through the live Pulse STT WebSocket
with vad_events=true. Writes the audio (as MP3) and captured event streams
plus a precomputed amplitude array to fern/components/vad-events-demo/.

Variants:

  - clean      : single utterance + 1.5 s trailing silence (normal case;
                 one speech_started + one speech_ended).
  - multi-turn : two utterances separated by silence (two pairs of events).
  - no-tail    : single utterance, no trailing silence (speech_started fires;
                 speech_ended does NOT — illustrates the caveat in Notes).

Run:

    export SMALLEST_API_KEY=...
    python3 scripts/spec-live-tests/prep_vad_demo_fixtures.py

Requires: ffmpeg on PATH, websockets (>=14,<16). All output is committed to
the repo so the docs site does not need any runtime API access.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import urllib.request
import wave
from pathlib import Path

import websockets

REPO_ROOT = Path(__file__).resolve().parents[2]
ASSET_DIR = REPO_ROOT / "fern" / "components" / "vad-events-demo" / "assets"
FIXTURE_DIR = REPO_ROOT / "fern" / "components" / "vad-events-demo" / "fixtures"
WORK_DIR = Path("/tmp/vad-demo-prep")

COOKBOOK_URL = (
    "https://github.com/smallest-inc/cookbook/raw/main/"
    "speech-to-text/getting-started/samples/audio.wav"
)

WS_BASE = "wss://api.smallest.ai/waves/v1/stt/live"
SAMPLE_RATE = 24000
CHUNK_MS = 200
WAVEFORM_BARS = 200


def sh(cmd: list[str]) -> None:
    print("  $", " ".join(cmd))
    subprocess.check_call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def ensure_source() -> Path:
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    src = WORK_DIR / "source.wav"
    if not src.exists():
        print(f"Downloading source audio -> {src}")
        urllib.request.urlretrieve(COOKBOOK_URL, src)
    return src


def build_variants(src: Path) -> dict[str, Path]:
    """Return dict of variant-name -> path to the prepared WAV (PCM, 24 kHz mono int16)."""
    silence_1500ms = WORK_DIR / "silence_1500.wav"
    silence_1000ms = WORK_DIR / "silence_1000.wav"

    sh([
        "ffmpeg", "-y", "-f", "lavfi",
        "-i", f"anullsrc=channel_layout=mono:sample_rate={SAMPLE_RATE}",
        "-t", "1.5", "-acodec", "pcm_s16le", str(silence_1500ms),
    ])
    sh([
        "ffmpeg", "-y", "-f", "lavfi",
        "-i", f"anullsrc=channel_layout=mono:sample_rate={SAMPLE_RATE}",
        "-t", "1.0", "-acodec", "pcm_s16le", str(silence_1000ms),
    ])

    clean = WORK_DIR / "clean.wav"
    multi = WORK_DIR / "multi-turn.wav"
    no_tail = WORK_DIR / "no-tail.wav"

    # Source needs to be normalized to 24 kHz mono 16-bit PCM first
    src_norm = WORK_DIR / "source_norm.wav"
    sh([
        "ffmpeg", "-y", "-i", str(src),
        "-ar", str(SAMPLE_RATE), "-ac", "1", "-acodec", "pcm_s16le",
        str(src_norm),
    ])

    # clean = src + 1.5s silence
    _concat_wavs([src_norm, silence_1500ms], clean)
    # multi-turn = src + 1.0s silence + src + 1.5s silence
    _concat_wavs([src_norm, silence_1000ms, src_norm, silence_1500ms], multi)
    # no-tail = src only
    sh(["cp", str(src_norm), str(no_tail)])

    return {"clean": clean, "multi-turn": multi, "no-tail": no_tail}


def _concat_wavs(inputs: list[Path], out: Path) -> None:
    list_file = WORK_DIR / f"_concat_{out.name}.txt"
    list_file.write_text("".join(f"file '{p}'\n" for p in inputs))
    sh([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(list_file),
        "-acodec", "pcm_s16le", str(out),
    ])


def export_mp3(wav: Path, mp3: Path) -> None:
    mp3.parent.mkdir(parents=True, exist_ok=True)
    sh([
        "ffmpeg", "-y", "-i", str(wav),
        "-codec:a", "libmp3lame", "-b:a", "64k",
        str(mp3),
    ])


def amplitude_envelope(wav: Path, bars: int) -> list[float]:
    """Compute `bars` peak-amplitude samples (0..1) across the file."""
    with wave.open(str(wav), "rb") as wf:
        assert wf.getnchannels() == 1 and wf.getsampwidth() == 2
        n = wf.getnframes()
        chunk = max(1, n // bars)
        out: list[float] = []
        for _ in range(bars):
            raw = wf.readframes(chunk)
            if not raw:
                break
            # int16 little-endian; find peak abs
            peak = 0
            for i in range(0, len(raw) - 1, 2):
                v = int.from_bytes(raw[i : i + 2], "little", signed=True)
                a = -v if v < 0 else v
                if a > peak:
                    peak = a
            out.append(round(peak / 32767, 4))
    # Pad to exactly `bars` if file shorter than expected
    while len(out) < bars:
        out.append(0.0)
    return out[:bars]


def pcm_frames(wav: Path) -> tuple[list[bytes], int]:
    with wave.open(str(wav), "rb") as wf:
        sr = wf.getframerate()
        raw = wf.readframes(wf.getnframes())
    bytes_per_chunk = int(sr * CHUNK_MS / 1000) * 2
    chunks = [raw[i : i + bytes_per_chunk] for i in range(0, len(raw), bytes_per_chunk)]
    return chunks, sr


async def capture_events(api_key: str, wav: Path) -> tuple[list[dict], float]:
    chunks, sr = pcm_frames(wav)
    duration_s = sum(len(c) for c in chunks) / 2 / sr
    qs = "&".join(
        [
            "model=pulse", "language=en", "encoding=linear16",
            f"sample_rate={sr}", "vad_events=true",
        ]
    )
    url = f"{WS_BASE}?{qs}"
    headers = {"Authorization": f"Bearer {api_key}"}
    received: list[dict] = []

    async with websockets.connect(url, additional_headers=headers) as ws:
        async def send_audio():
            for chunk in chunks:
                await ws.send(chunk)
                await asyncio.sleep(CHUNK_MS / 1000)
            await ws.send(json.dumps({"type": "close_stream"}))

        async def recv():
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

        await asyncio.wait_for(asyncio.gather(send_audio(), recv()), timeout=60)

    return received, duration_s


def normalize_event(msg: dict) -> dict | None:
    """Reduce a captured wire message to the fields the demo needs."""
    t = msg.get("type")
    if t in ("speech_started", "speech_ended"):
        return {
            "type": t,
            "timestamp": msg["timestamp"],
            "session_id": msg.get("session_id", ""),
        }
    text = msg.get("transcription") or msg.get("transcript")
    if text:
        return {
            "type": "transcription",
            "transcript": text,
            "is_final": bool(msg.get("is_final")),
            "is_last": bool(msg.get("is_last")),
            "session_id": msg.get("session_id", ""),
        }
    return None


def estimate_transcript_timestamps(events: list[dict], duration_s: float) -> list[dict]:
    """Server transcripts have no top-level timestamp. Spread them across the audio duration
    in capture order so the demo can highlight them in sync with playback. Acoustic events
    keep their server timestamps."""
    n_t = sum(1 for e in events if e["type"] == "transcription")
    if n_t == 0:
        return events
    spacing = duration_s / (n_t + 1)
    next_t = spacing
    out: list[dict] = []
    for e in events:
        if e["type"] == "transcription":
            e = {**e, "timestamp_est": round(next_t, 3)}
            next_t += spacing
        out.append(e)
    return out


async def main() -> int:
    api_key = os.environ.get("SMALLEST_API_KEY")
    if not api_key:
        print("SMALLEST_API_KEY env var required", file=sys.stderr)
        return 2

    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    ASSET_DIR.mkdir(parents=True, exist_ok=True)

    src = ensure_source()
    variants = build_variants(src)

    for name, wav in variants.items():
        print(f"\n=== variant: {name} ===")
        # Audio asset
        mp3 = ASSET_DIR / f"{name}.mp3"
        export_mp3(wav, mp3)
        # Amplitude
        bars = amplitude_envelope(wav, WAVEFORM_BARS)
        # Live event capture
        raw_events, duration_s = await capture_events(api_key, wav)
        events = [e for m in raw_events if (e := normalize_event(m))]
        events = estimate_transcript_timestamps(events, duration_s)
        n_start = sum(1 for e in events if e["type"] == "speech_started")
        n_end = sum(1 for e in events if e["type"] == "speech_ended")
        n_tr = sum(1 for e in events if e["type"] == "transcription")
        print(f"  duration={duration_s:.2f}s  speech_started={n_start} speech_ended={n_end} transcription={n_tr}")
        fixture = {
            "name": name,
            "audio": f"./assets/{name}.mp3",
            "duration_s": round(duration_s, 3),
            "sample_rate": SAMPLE_RATE,
            "waveform": bars,
            "events": events,
        }
        (FIXTURE_DIR / f"{name}.json").write_text(json.dumps(fixture, indent=2))
        print(f"  wrote {FIXTURE_DIR / (name + '.json')}")

    print("\nFixtures written. Component can now consume them.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
