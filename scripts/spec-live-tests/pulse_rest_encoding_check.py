#!/usr/bin/env python3
"""
Pulse STT REST — does the `encoding` query param actually do anything?

The script sends the same audio (the public Pulse demo WAV) through the
REST endpoint in several shapes. If the server honors `encoding` on
REST, raw-PCM/raw-mu-law inputs paired with the matching encoding hint
should transcribe; bogus enum values should 400. If the server ignores
the param, every variant returns 200 (with empty transcription on
headerless inputs) and bogus values are silently accepted.

Cases:
  1. WAV (RIFF header)              no encoding                baseline
  2. Headerless PCM s16le 16 kHz    no encoding                container detect should fail
  3. Headerless PCM s16le 16 kHz    encoding=linear16          would prove honored
  4. Headerless PCM s16le 16 kHz    encoding=__bogus__         would prove enum validated
  5. Headerless mu-law 8 kHz        encoding=mulaw             telephony scenario
  6. Headerless A-law 8 kHz         encoding=alaw              telephony scenario

Run:
    SMALLEST_API_KEY=... python3 pulse_rest_encoding_check.py
    SMALLEST_API_KEY=... python3 pulse_rest_encoding_check.py --verbose
                         (prints full server response for each case)

Exit codes:
    0 — REST honors encoding
    1 — REST ignores encoding
    2 — inconclusive (baseline broken — check key/network)
    3 — mixed signal — investigate

Requires:
  - SMALLEST_API_KEY env var
  - ffmpeg on PATH (used to produce headerless audio)
  - requests
"""
import argparse
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


def _ffmpeg(args: list[str]) -> None:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args], check=True)


def fetch_demo_audio(workdir: Path) -> dict[str, Path]:
    wav = workdir / "demo.wav"
    pcm = workdir / "demo.pcm"
    mulaw = workdir / "demo.mulaw"
    alaw = workdir / "demo.alaw"
    if not wav.exists():
        r = requests.get(DEMO_WAV_URL, timeout=60)
        r.raise_for_status()
        wav.write_bytes(r.content)
    # WAV → headerless s16le 16 kHz mono
    _ffmpeg(["-i", str(wav), "-ar", "16000", "-ac", "1", "-f", "s16le", "-acodec", "pcm_s16le", str(pcm)])
    # WAV → headerless mu-law 8 kHz mono
    _ffmpeg(["-i", str(wav), "-ar", "8000", "-ac", "1", "-f", "mulaw", "-acodec", "pcm_mulaw", str(mulaw)])
    # WAV → headerless A-law 8 kHz mono
    _ffmpeg(["-i", str(wav), "-ar", "8000", "-ac", "1", "-f", "alaw", "-acodec", "pcm_alaw", str(alaw)])
    return {"wav": wav, "pcm": pcm, "mulaw": mulaw, "alaw": alaw}


def post(audio: bytes, content_type: str, params: dict[str, str]) -> tuple[int, dict, str]:
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"{REST}?{qs}"
    r = requests.post(
        url,
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
    return r.status_code, body, url


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
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Print full request URL + server JSON for every case")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as tmp:
        workdir = Path(tmp)
        files = fetch_demo_audio(workdir)
        wav_bytes = files["wav"].read_bytes()
        pcm_bytes = files["pcm"].read_bytes()
        mulaw_bytes = files["mulaw"].read_bytes()
        alaw_bytes = files["alaw"].read_bytes()

        cases = [
            ("WAV (header)            | no encoding",
             wav_bytes,   "audio/wav",                {"language": "en"}),
            ("Raw PCM (headerless)    | no encoding",
             pcm_bytes,   "application/octet-stream", {"language": "en"}),
            ("Raw PCM (headerless)    | encoding=linear16",
             pcm_bytes,   "application/octet-stream", {"language": "en", "encoding": "linear16", "sample_rate": "16000"}),
            ("Raw PCM (headerless)    | encoding=__bogus__",
             pcm_bytes,   "application/octet-stream", {"language": "en", "encoding": "__bogus__"}),
            ("Raw mu-law 8kHz         | encoding=mulaw",
             mulaw_bytes, "application/octet-stream", {"language": "en", "encoding": "mulaw",   "sample_rate": "8000"}),
            ("Raw A-law 8kHz          | encoding=alaw",
             alaw_bytes,  "application/octet-stream", {"language": "en", "encoding": "alaw",    "sample_rate": "8000"}),
        ]

        rows = []
        for label, audio, ctype, params in cases:
            status, body, url = post(audio, ctype, params)
            rows.append({**summarise(label, status, body), "url": url, "body": body, "audio_bytes": len(audio)})

        # Compact table
        print()
        print(f"{'case':<48} {'audio bytes':>12} {'http':>5} {'len':>5}  first 60 chars")
        print("-" * 130)
        for r in rows:
            print(f"{r['case']:<48} {r['audio_bytes']:>12} {r['http']:>5} {r['transcription_chars']:>5}  {r['first_60']!r}")
            if r["errors"]:
                print(f"  errors: {r['errors']}")

        # Verbose dumps for skeptics
        if args.verbose:
            print()
            print("=" * 130)
            print("Full server responses (for sharing as receipts)")
            print("=" * 130)
            for r in rows:
                print()
                print(f"# {r['case']}")
                print(f"  POST {r['url']}")
                print(f"  HTTP {r['http']}")
                print("  body:", json.dumps(r["body"], indent=2)[:1500])

        # Verdict
        print()
        print("=" * 130)
        rest_baseline_works = rows[0]["transcription_chars"] > 0
        pcm_no_encoding = rows[1]["transcription_chars"]
        pcm_with_encoding = rows[2]["transcription_chars"]
        bogus_status = rows[3]["http"]
        mulaw_with_encoding = rows[4]["transcription_chars"]
        alaw_with_encoding = rows[5]["transcription_chars"]

        if not rest_baseline_works:
            print("INCONCLUSIVE — WAV baseline returned empty; check API key / network.")
            return 2

        encoding_helps = pcm_with_encoding > pcm_no_encoding
        bogus_rejected = bogus_status >= 400
        telephony_works = mulaw_with_encoding > 0 or alaw_with_encoding > 0

        if (encoding_helps or telephony_works) and bogus_rejected:
            print("REST HONORS encoding — passing it changes behavior, and bogus values are rejected.")
            return 0
        if not encoding_helps and not telephony_works and not bogus_rejected:
            print("REST IGNORES encoding — every headerless input returns 200 with empty transcription regardless of encoding hint, and bogus values are silently accepted (200).")
            print()
            print("Cross-reference (waves-platform source): apps/main-backend/src/services/asr/asr.service.ts → transcribeViaRedis builds sessionParams without `encoding` or `sample_rate` keys; the worker therefore relies entirely on container-header detection.")
            return 1
        print(f"MIXED: encoding_helps={encoding_helps}, bogus_rejected={bogus_rejected}, telephony_works={telephony_works} — investigate.")
        return 3


if __name__ == "__main__":
    sys.exit(main())
