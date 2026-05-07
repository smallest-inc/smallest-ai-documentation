#!/usr/bin/env python3
"""
Pulse STT REST — does the `encoding` query param actually do anything?

Sends the same audio in 4 shapes:

  1. WAV (with header)            no encoding     baseline transcription expected
  2. Raw PCM s16le 16kHz mono     no encoding     should fail/empty if REST is purely container-driven
  3. Raw PCM s16le 16kHz mono     encoding=linear16
  4. Raw PCM s16le 16kHz mono     encoding=__bogus__  must NOT 400 if param is silently ignored

Pass criteria (interpreting "REST honors encoding"):
  - row 3 returns a non-empty transcription (would prove encoding is honored on REST)
  - row 4 returns 400 (would prove the enum is validated)

Pass criteria (interpreting "REST silently ignores encoding"):
  - rows 2, 3, 4 all return 200 with empty transcription
  - row 4 does not 400

Requires:
  - SMALLEST_API_KEY env var
  - ffmpeg on PATH (used to produce the headerless PCM)
  - requests
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import requests

API_KEY = os.environ.get("SMALLEST_API_KEY")
if not API_KEY:
    print("FATAL: set SMALLEST_API_KEY", file=sys.stderr)
    sys.exit(2)

REST = "https://api.smallest.ai/waves/v1/pulse/get_text"
DEMO_WAV_URL = (
    "https://github.com/smallest-inc/smallest-ai-documentation/raw/main/"
    "fern/products/waves/pages/audio/pulse-feature-demo.wav"
)


def fetch_demo_audio(workdir: Path) -> tuple[Path, Path]:
    wav = workdir / "demo.wav"
    pcm = workdir / "demo.pcm"
    if not wav.exists():
        r = requests.get(DEMO_WAV_URL, timeout=60)
        r.raise_for_status()
        wav.write_bytes(r.content)
    # WAV → headerless s16le 16kHz mono via ffmpeg
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", str(wav),
            "-ar", "16000", "-ac", "1",
            "-f", "s16le", "-acodec", "pcm_s16le",
            str(pcm),
        ],
        check=True,
    )
    return wav, pcm


def post(audio: bytes, content_type: str, params: dict[str, str]) -> tuple[int, dict]:
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    r = requests.post(
        f"{REST}?{qs}",
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": content_type,
        },
        data=audio,
        timeout=120,
    )
    try:
        body = r.json()
    except Exception:
        body = {"raw": r.text[:200]}
    return r.status_code, body


def summarise(label: str, status: int, body: dict) -> dict:
    txt = body.get("transcription") or ""
    return {
        "case": label,
        "http": status,
        "transcription_chars": len(txt),
        "first_60": txt[:60],
        "errors": body.get("errors") or body.get("error"),
    }


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        workdir = Path(tmp)
        wav, pcm = fetch_demo_audio(workdir)
        wav_bytes = wav.read_bytes()
        pcm_bytes = pcm.read_bytes()

        cases = [
            ("WAV (header)            | no encoding",      wav_bytes, "audio/wav",                {"language": "en"}),
            ("Raw PCM (headerless)    | no encoding",      pcm_bytes, "application/octet-stream", {"language": "en"}),
            ("Raw PCM (headerless)    | encoding=linear16", pcm_bytes, "application/octet-stream", {"language": "en", "encoding": "linear16", "sample_rate": "16000"}),
            ("Raw PCM (headerless)    | encoding=__bogus__", pcm_bytes, "application/octet-stream", {"language": "en", "encoding": "__bogus__"}),
        ]

        rows = []
        for label, audio, ctype, params in cases:
            status, body = post(audio, ctype, params)
            rows.append(summarise(label, status, body))

        print(f"{'case':<48} {'http':<6} {'len':<5} first 60 chars")
        print("-" * 110)
        for r in rows:
            print(f"{r['case']:<48} {r['http']:<6} {r['transcription_chars']:<5} {r['first_60']!r}")
            if r["errors"]:
                print(f"  errors: {r['errors']}")

        # Verdicts
        print()
        print("=" * 110)
        rest_baseline_works = rows[0]["transcription_chars"] > 0
        pcm_no_encoding = rows[1]["transcription_chars"]
        pcm_with_encoding = rows[2]["transcription_chars"]
        bogus_status = rows[3]["http"]

        if not rest_baseline_works:
            print("INCONCLUSIVE — WAV baseline returned empty; check API key / network.")
            return 2

        encoding_helps = pcm_with_encoding > pcm_no_encoding
        bogus_rejected = bogus_status >= 400

        if encoding_helps and bogus_rejected:
            print("REST HONORS encoding — passing it changes behavior, and bogus values are rejected.")
            return 0
        if not encoding_helps and not bogus_rejected:
            print("REST IGNORES encoding — same empty transcription with/without it, bogus values are silently accepted (200).")
            return 1
        print(f"MIXED: encoding_helps={encoding_helps}, bogus_rejected={bogus_rejected} — investigate.")
        return 3


if __name__ == "__main__":
    sys.exit(main())
