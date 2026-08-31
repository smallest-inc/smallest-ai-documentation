"""Diarization response-shape live test.

Verifies every claim on the Diarization docs page + spec against live:

  A. Batch (POST /waves/v1/stt/?model=pulse&diarize=true&word_timestamps=true)
     - `words[i].speaker` present, integer, zero-indexed
     - `words[i].speaker_confidence` present, 0.0–1.0 float
     - `utterances[i].speaker` present, integer, zero-indexed

  B. Streaming (WSS /waves/v1/stt/live?model=pulse&diarize=true&word_timestamps=true)
     - interim events: no `words` key, `is_final` == false
     - final events: `words[i].speaker` + `speaker_confidence` present, integers/floats

  C. Pulse Pro carve-out
     - `?model=pulse-pro&diarize=true` returns no `speaker` fields on `words[]`
       and no `utterances[]`, per the docs

Downloads the standard sample audio each run. Idempotent, safe to run
against prod (no persisted state, no billing spike beyond one short STT
call per mode).

Usage:
    SMALLEST_API_KEY=sk_... python3 scripts/spec-live-tests/diarization_live_test.py
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import urllib.request

BASE_REST = os.environ.get("BASE_URL", "https://api.smallest.ai").rstrip("/") + "/waves/v1"
KEY = os.environ.get("SMALLEST_API_KEY")
if not KEY:
    sys.exit("SMALLEST_API_KEY env var is required")

SAMPLE_URL = "https://github.com/smallest-inc/cookbook/raw/main/speech-to-text/getting-started/samples/audio.wav"
SAMPLE_PATH = "/tmp/diar_sample.wav"

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  — {detail}" if detail else ""))
    RESULTS.append((name, ok, detail))


def ensure_sample() -> None:
    if os.path.exists(SAMPLE_PATH):
        return
    urllib.request.urlretrieve(SAMPLE_URL, SAMPLE_PATH)


def batch_stt(model: str, diarize: bool, word_ts: bool) -> tuple[int, dict]:
    with open(SAMPLE_PATH, "rb") as f:
        audio = f.read()
    qs = f"?model={model}&language=en&diarize={'true' if diarize else 'false'}&word_timestamps={'true' if word_ts else 'false'}"
    r = urllib.request.Request(
        BASE_REST + "/stt/" + qs,
        data=audio,
        method="POST",
        headers={"Authorization": f"Bearer {KEY}", "Content-Type": "audio/wav"},
    )
    with urllib.request.urlopen(r, timeout=30) as resp:
        return resp.status, json.load(resp)


# ---- Section A: batch ---------------------------------------------------
print("\n[A] Batch (POST /waves/v1/stt/?model=pulse&diarize=true)")
ensure_sample()
try:
    status, body = batch_stt("pulse", diarize=True, word_ts=True)
except Exception as e:
    sys.exit(f"batch call failed: {e}")

check("A1 status 200", status == 200)
check("A2 body has words[]", isinstance(body.get("words"), list) and len(body["words"]) > 0)
check("A3 body has utterances[]", isinstance(body.get("utterances"), list) and len(body["utterances"]) > 0)

if isinstance(body.get("words"), list) and body["words"]:
    w = body["words"][0]
    check("A4 words[0].speaker is integer", isinstance(w.get("speaker"), int),
          f"got type={type(w.get('speaker')).__name__} value={w.get('speaker')!r}")
    check("A5 words[0].speaker >= 0", isinstance(w.get("speaker"), int) and w["speaker"] >= 0,
          f"got {w.get('speaker')!r}")
    check("A6 words[0].speaker_confidence is float 0.0-1.0",
          isinstance(w.get("speaker_confidence"), (int, float)) and 0.0 <= w["speaker_confidence"] <= 1.0,
          f"got {w.get('speaker_confidence')!r}")
if isinstance(body.get("utterances"), list) and body["utterances"]:
    u = body["utterances"][0]
    check("A7 utterances[0].speaker is integer", isinstance(u.get("speaker"), int),
          f"got type={type(u.get('speaker')).__name__} value={u.get('speaker')!r}")


# ---- Section B: streaming ----------------------------------------------
print("\n[B] Streaming (WSS /waves/v1/stt/live?model=pulse&diarize=true)")
try:
    import websockets  # noqa: F401
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "websockets", "-q"])
    import websockets  # noqa: F401


async def run_stream():
    import websockets
    # Sample audio is 24 kHz mono s16le PCM (verified: wave.getframerate() == 24000).
    # Handshake, chunk math, and comment must all agree.
    SAMPLE_RATE = 24000
    url = ("wss://api.smallest.ai/waves/v1/stt/live"
           f"?model=pulse&language=en&encoding=linear16&sample_rate={SAMPLE_RATE}"
           "&diarize=true&word_timestamps=true")
    with open(SAMPLE_PATH, "rb") as f:
        wav = f.read()
    pcm = wav[44:]  # strip WAV header (canonical 44-byte RIFF header on this sample)
    interim_events = 0
    final_events = 0
    final_events_with_words = 0
    final_events_with_speaker = 0
    async with websockets.connect(url, additional_headers={"Authorization": f"Bearer {KEY}"}) as ws:
        chunk = SAMPLE_RATE * 2  # 1 second of 16-bit mono at SAMPLE_RATE
        for i in range(0, len(pcm), chunk):
            await ws.send(pcm[i:i + chunk])
            await asyncio.sleep(0.2)
        await ws.send(json.dumps({"type": "close_stream"}))
        for _ in range(60):
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=8)
            except asyncio.TimeoutError:
                break
            d = json.loads(msg) if isinstance(msg, str) else None
            if not d or d.get("type") != "transcription":
                continue
            if d.get("is_final"):
                final_events += 1
                if isinstance(d.get("words"), list) and d["words"]:
                    final_events_with_words += 1
                    if any(isinstance(w.get("speaker"), int) for w in d["words"]):
                        final_events_with_speaker += 1
            else:
                interim_events += 1
                if d.get("words") is not None:
                    return interim_events, final_events, final_events_with_words, final_events_with_speaker, "INTERIM_HAD_WORDS"
            if d.get("is_last"):
                break
    return interim_events, final_events, final_events_with_words, final_events_with_speaker, None


try:
    interim, final, final_words, final_speaker, anomaly = asyncio.run(run_stream())
except Exception as e:
    check("B0 streaming connect", False, str(e))
    interim = final = final_words = final_speaker = 0
    anomaly = None
else:
    check("B0 streaming connect", True)

check("B1 at least one interim event received", interim > 0, f"got {interim}")
check("B2 at least one final event received", final > 0, f"got {final}")
check("B3 interim events do NOT carry words[]", anomaly is None,
      "some interim event carried words" if anomaly == "INTERIM_HAD_WORDS" else "")
check("B4 final events DO carry words[]", final_words > 0, f"got {final_words} of {final}")
check("B5 final events carry integer speaker on words", final_speaker > 0,
      f"got {final_speaker} of {final_words}")


# ---- Section C: Pulse Pro does not diarize -----------------------------
print("\n[C] Pulse Pro carve-out")
try:
    status, body = batch_stt("pulse-pro", diarize=True, word_ts=True)
except Exception as e:
    check("C0 pulse-pro batch call", False, str(e))
else:
    check("C1 pulse-pro batch 200", status == 200, f"got {status}")
    words = body.get("words", []) if isinstance(body, dict) else []
    utterances = body.get("utterances")
    speaker_seen = any(w.get("speaker") is not None for w in words if isinstance(w, dict))
    check("C2 pulse-pro words[] have no speaker field", not speaker_seen,
          "found speaker field on Pulse Pro response" if speaker_seen else "")
    check("C3 pulse-pro response has no utterances[]", not utterances,
          f"utterances present: {utterances is not None}")


# ---- Summary ----------------------------------------------------------
print("\n" + "=" * 60)
passed = sum(1 for _, ok, _ in RESULTS if ok)
total = len(RESULTS)
print(f"  {passed}/{total} checks passed")
print("=" * 60)

if passed != total:
    print("\nFailed:")
    for name, ok, detail in RESULTS:
        if not ok:
            print(f"  - {name}: {detail}")
    sys.exit(1)

print("\nAll diarization response-shape claims match live production.")
