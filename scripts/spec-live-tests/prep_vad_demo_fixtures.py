"""Prepare audio + event-capture fixtures for the VAD events interactive demo.

Generates three audio variants using Lightning v3.1 Pro (voice: maverick),
runs each through the live Pulse STT WebSocket with vad_events=true and
word_timestamps=true, and writes the captured event stream as a typed TS
module under fern/components/vad-events-demo/fixtures/.

Variants:

  - clean      : one short utterance + 1.5 s trailing silence
                 (one speech_started + one speech_ended).
  - multi-turn : two utterances separated by 1.0 s silence
                 (two pairs of acoustic events).
  - no-tail    : one utterance with no trailing silence
                 (speech_started fires; speech_ended does NOT —
                 illustrates the caveat in the page Notes).

Run:

    export SMALLEST_API_KEY=...
    python3 scripts/spec-live-tests/prep_vad_demo_fixtures.py

Requires: ffmpeg on PATH, websockets (>=14,<16). MP3 bytes are embedded as
base64 data URLs in each fixture, so the docs build has no runtime asset
dependency.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import subprocess
import sys
import wave
from pathlib import Path

import websockets
import urllib.request

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = REPO_ROOT / "fern" / "components" / "vad-events-demo" / "fixtures"
WORK_DIR = Path("/tmp/vad-demo-prep")

TTS_URL = "https://api.smallest.ai/waves/v1/lightning-v3.1/get_speech"
TTS_VOICE_ID = "maverick"
TTS_MODEL = "lightning_v3.1_pro"

WS_BASE = "wss://api.smallest.ai/waves/v1/stt/live"
SAMPLE_RATE = 24000
CHUNK_MS = 200
WAVEFORM_BARS = 200

# Conversation lines per variant. Natural phrasing with fillers so the
# samples sound like real product calls, not test reads.
DIALOGUE = {
    "clean": [
        "Hey, so um, I was looking at the dashboard, and yeah, the numbers look pretty solid actually.",
    ],
    "multi-turn": [
        "Hi there, can you hear me okay?",
        "Great. So let's um, get started with the demo then.",
    ],
    "no-tail": [
        "Yeah so basically what I'm trying to say is",
    ],
}


def sh(cmd: list[str]) -> None:
    print("  $", " ".join(cmd))
    subprocess.check_call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def tts(text: str, out_mp3: Path, api_key: str) -> None:
    """Generate one MP3 via Lightning v3.1 Pro + maverick."""
    body = json.dumps({
        "text": text,
        "voice_id": TTS_VOICE_ID,
        "model": TTS_MODEL,
        "sample_rate": SAMPLE_RATE,
        "output_format": "mp3",
    }).encode()
    req = urllib.request.Request(
        TTS_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        if resp.status != 200:
            raise RuntimeError(f"TTS failed: HTTP {resp.status}")
        out_mp3.write_bytes(resp.read())
    print(f"  tts {out_mp3.name}  ({out_mp3.stat().st_size} bytes)  text={text!r}")


def mp3_to_wav(mp3: Path, wav: Path) -> None:
    sh([
        "ffmpeg", "-y", "-i", str(mp3),
        "-ar", str(SAMPLE_RATE), "-ac", "1", "-acodec", "pcm_s16le",
        str(wav),
    ])


def silence_wav(seconds: float, out: Path) -> None:
    sh([
        "ffmpeg", "-y", "-f", "lavfi",
        "-i", f"anullsrc=channel_layout=mono:sample_rate={SAMPLE_RATE}",
        "-t", str(seconds), "-acodec", "pcm_s16le", str(out),
    ])


def trim_trailing_silence(wav_in: Path, wav_out: Path, threshold_db: int = -45) -> None:
    """Strip trailing silence so a 'no-tail' clip really ends mid-thought."""
    sh([
        "ffmpeg", "-y", "-i", str(wav_in),
        "-af", f"areverse,silenceremove=start_periods=1:start_duration=0.05:start_threshold={threshold_db}dB,areverse",
        "-acodec", "pcm_s16le", str(wav_out),
    ])


def concat_wavs(inputs: list[Path], out: Path) -> None:
    list_file = WORK_DIR / f"_concat_{out.name}.txt"
    list_file.write_text("".join(f"file '{p}'\n" for p in inputs))
    sh([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(list_file),
        "-acodec", "pcm_s16le", str(out),
    ])


def wav_to_mp3(wav: Path, mp3: Path) -> None:
    sh([
        "ffmpeg", "-y", "-i", str(wav),
        "-codec:a", "libmp3lame", "-b:a", "64k",
        str(mp3),
    ])


def build_variants(api_key: str) -> dict[str, Path]:
    """Return dict of variant-name -> path to the prepared WAV ready for streaming."""
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    silence_15 = WORK_DIR / "silence_1500.wav"
    silence_10 = WORK_DIR / "silence_1000.wav"
    silence_wav(1.5, silence_15)
    silence_wav(1.0, silence_10)

    out: dict[str, Path] = {}

    # clean: one TTS clip + 1.5s trailing silence
    clean_mp3 = WORK_DIR / "clean_raw.mp3"
    clean_raw_wav = WORK_DIR / "clean_raw.wav"
    clean_wav = WORK_DIR / "clean.wav"
    tts(DIALOGUE["clean"][0], clean_mp3, api_key)
    mp3_to_wav(clean_mp3, clean_raw_wav)
    concat_wavs([clean_raw_wav, silence_15], clean_wav)
    out["clean"] = clean_wav

    # multi-turn: TTS turn 1 + 1.0s silence + TTS turn 2 + 1.5s silence
    t1_mp3 = WORK_DIR / "multi_turn_1_raw.mp3"
    t2_mp3 = WORK_DIR / "multi_turn_2_raw.mp3"
    t1_wav = WORK_DIR / "multi_turn_1_raw.wav"
    t2_wav = WORK_DIR / "multi_turn_2_raw.wav"
    multi_wav = WORK_DIR / "multi-turn.wav"
    tts(DIALOGUE["multi-turn"][0], t1_mp3, api_key)
    tts(DIALOGUE["multi-turn"][1], t2_mp3, api_key)
    mp3_to_wav(t1_mp3, t1_wav)
    mp3_to_wav(t2_mp3, t2_wav)
    concat_wavs([t1_wav, silence_10, t2_wav, silence_15], multi_wav)
    out["multi-turn"] = multi_wav

    # no-tail: TTS clip with trailing silence STRIPPED so it really ends
    # mid-utterance. This is what triggers the documented caveat: model
    # never observes silence, so no speech_ended is emitted.
    nt_mp3 = WORK_DIR / "no_tail_raw.mp3"
    nt_raw_wav = WORK_DIR / "no_tail_raw.wav"
    nt_wav = WORK_DIR / "no-tail.wav"
    tts(DIALOGUE["no-tail"][0], nt_mp3, api_key)
    mp3_to_wav(nt_mp3, nt_raw_wav)
    trim_trailing_silence(nt_raw_wav, nt_wav)
    out["no-tail"] = nt_wav

    return out


def amplitude_envelope(wav: Path, bars: int) -> list[float]:
    with wave.open(str(wav), "rb") as wf:
        assert wf.getnchannels() == 1 and wf.getsampwidth() == 2
        n = wf.getnframes()
        chunk = max(1, n // bars)
        out: list[float] = []
        for _ in range(bars):
            raw = wf.readframes(chunk)
            if not raw:
                break
            peak = 0
            for i in range(0, len(raw) - 1, 2):
                v = int.from_bytes(raw[i : i + 2], "little", signed=True)
                a = -v if v < 0 else v
                if a > peak:
                    peak = a
            out.append(round(peak / 32767, 4))
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
    qs = "&".join([
        "model=pulse",
        "language=en",
        "encoding=linear16",
        f"sample_rate={sr}",
        "vad_events=true",
        "word_timestamps=true",
    ])
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
    """Reduce a wire message to the demo's display shape, preserving real timing."""
    t = msg.get("type")
    if t in ("speech_started", "speech_ended"):
        return {
            "type": t,
            "timestamp": msg["timestamp"],
            "session_id": msg.get("session_id", ""),
        }
    text = msg.get("transcription") or msg.get("transcript")
    if not text:
        return None
    # Real timing: use the last word's end time when word_timestamps=true
    # gave us a words array, otherwise fall back to None (caller will skip
    # this transcript when timestamping).
    last_word_end: float | None = None
    words = msg.get("words")
    if isinstance(words, list) and words:
        end = words[-1].get("end")
        if isinstance(end, (int, float)):
            last_word_end = float(end)
    return {
        "type": "transcription",
        "transcript": text,
        "is_final": bool(msg.get("is_final")),
        "is_last": bool(msg.get("is_last")),
        "session_id": msg.get("session_id", ""),
        "timestamp_real": last_word_end,
    }


def stamp_transcripts(events: list[dict], duration_s: float) -> list[dict]:
    """Attach `timestamp_est` so the demo can position transcripts on the
    timeline. Real word-end timestamps (`timestamp_real`) win; otherwise
    interleave between the surrounding acoustic events."""
    # Pass 1: precompute timeline anchors from acoustic events
    speech_started_t = [e["timestamp"] for e in events if e["type"] == "speech_started"]
    speech_ended_t = [e["timestamp"] for e in events if e["type"] == "speech_ended"]
    fallback_start = speech_started_t[0] if speech_started_t else 0.0
    fallback_end = speech_ended_t[-1] if speech_ended_t else duration_s

    # Pass 2: assign timestamp_est
    out: list[dict] = []
    last_t: float | None = None
    for e in events:
        if e["type"] == "transcription":
            real = e.pop("timestamp_real", None)
            if isinstance(real, (int, float)):
                ts = float(real)
            elif last_t is not None:
                # Step a small amount past the previous transcript
                ts = last_t + 0.05
            else:
                ts = fallback_start + 0.1
            ts = min(ts, fallback_end - 0.01)
            e["timestamp_est"] = round(ts, 3)
            last_t = ts
        out.append(e)
    return out


async def main() -> int:
    api_key = os.environ.get("SMALLEST_API_KEY")
    if not api_key:
        print("SMALLEST_API_KEY env var required", file=sys.stderr)
        return 2

    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)

    print("Generating audio (Lightning v3.1 Pro + maverick)...")
    variants = build_variants(api_key)

    for name, wav in variants.items():
        print(f"\n=== variant: {name} ===")
        # Read raw MP3 from the WAV via re-encode for the embedded fixture.
        mp3 = WORK_DIR / f"{name}.mp3"
        wav_to_mp3(wav, mp3)
        # Amplitude envelope from the WAV (true PCM samples).
        bars = amplitude_envelope(wav, WAVEFORM_BARS)
        # Live capture against prod with vad_events + word_timestamps.
        raw_events, duration_s = await capture_events(api_key, wav)
        events = [e for m in raw_events if (e := normalize_event(m))]
        events = stamp_transcripts(events, duration_s)
        # Sort by timeline timestamp so the demo's left-to-right replay
        # matches the audio. Wire order is preserved up to this point;
        # speech_ended can arrive after partial transcripts whose
        # word-end times sit much earlier, which would make the log jump
        # around during playback. Stable sort keeps tied timestamps in
        # wire order.
        def _ts(e: dict) -> float:
            return e["timestamp_est"] if e["type"] == "transcription" else e["timestamp"]
        events.sort(key=_ts)
        n_start = sum(1 for e in events if e["type"] == "speech_started")
        n_end = sum(1 for e in events if e["type"] == "speech_ended")
        n_tr = sum(1 for e in events if e["type"] == "transcription")
        print(f"  duration={duration_s:.2f}s  speech_started={n_start} speech_ended={n_end} transcription={n_tr}")
        # Embed MP3 as base64 data URL so the demo has no runtime asset dep.
        audio_data_url = "data:audio/mpeg;base64," + base64.b64encode(mp3.read_bytes()).decode("ascii")
        fixture = {
            "name": name,
            "audio": audio_data_url,
            "duration_s": round(duration_s, 3),
            "sample_rate": SAMPLE_RATE,
            "waveform": bars,
            "events": events,
        }
        ts_header = (
            "// Auto-generated by scripts/spec-live-tests/prep_vad_demo_fixtures.py.\n"
            "// Captured live from the production Pulse STT WebSocket with\n"
            "// vad_events=true and word_timestamps=true.\n"
            "// To regenerate: SMALLEST_API_KEY=... python3 scripts/spec-live-tests/prep_vad_demo_fixtures.py\n\n"
            "import type { Fixture } from \"../types\";\n\n"
            "export const fixture: Fixture = "
        )
        ts_path = FIXTURE_DIR / f"{name}.ts"
        ts_path.write_text(ts_header + json.dumps(fixture, indent=2) + " as const;\n")
        print(f"  wrote {ts_path}")

    print("\nFixtures written. Component can now consume them.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
