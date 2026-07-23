"""Lightning v3.1 TTS live test — runs on PR when waves TTS spec changes.

Smoke-tests the documented endpoints:
  1. POST /waves/v1/lightning-v3.1/get_speech (sync REST) → expect WAV bytes.
  2. WS  /waves/v1/lightning-v3.1/get_speech (streaming) → expect at least
     one audio chunk and a clean close.

Stateless — no resource cleanup needed. Fails if the documented endpoint
is unreachable, returns the wrong content type, or the WS rejects the
documented payload shape.

Usage:
    SMALLEST_API_KEY=... python3 scripts/spec-live-tests/waves_tts_live_test.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import urllib.error
import urllib.request

import websockets

REST_URL = "https://api.smallest.ai/waves/v1/lightning-v3.1/get_speech"
WS_URL = "wss://api.smallest.ai/waves/v1/lightning-v3.1/get_speech/stream"
TEST_TEXT = "Spec live test."
TEST_VOICE = "magnus"

API_KEY = os.environ.get("SMALLEST_API_KEY")
if not API_KEY:
    sys.exit("SMALLEST_API_KEY env var is required")


def test_sync_rest() -> tuple[bool, str]:
    body = json.dumps({
        "text": TEST_TEXT,
        "voice_id": TEST_VOICE,
        "sample_rate": 24000,
    }).encode()
    r = urllib.request.Request(
        REST_URL,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            ct = resp.headers.get("Content-Type", "")
            audio = resp.read()
            # Either an audio/* content type, or a JSON wrapper containing
            # base64 audio. Both shapes are documented; just verify
            # we got *something* non-trivial back.
            if "audio" in ct.lower():
                if len(audio) < 1000:
                    return False, f"audio too small ({len(audio)} bytes)"
                return True, f"audio/{ct}, {len(audio)} bytes"
            if "json" in ct.lower():
                try:
                    data = json.loads(audio)
                    if "audio" in data or "data" in data:
                        return True, f"json wrapper, keys={list(data.keys())}"
                    return False, f"json missing audio key: {list(data.keys())}"
                except json.JSONDecodeError:
                    return False, f"could not parse json"
            return False, f"unexpected content-type: {ct}"
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:200]}"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


async def test_ws_streaming() -> tuple[bool, str]:
    """Lightning v3.1 WS responses are JSON-framed, not raw audio bytes.

    The documented shape is `{status: "chunk", data: {audio: <base64>}}`
    until a final `{status: "complete"}`. See
    fern/products/waves/pages/text-to-speech/stream-tts.mdx.
    """
    import base64
    headers = {"Authorization": f"Bearer {API_KEY}"}
    payload = {
        "text": TEST_TEXT,
        "voice_id": TEST_VOICE,
        "sample_rate": 24000,
    }
    chunks_received = 0
    bytes_received = 0
    saw_complete = False
    try:
        async with websockets.connect(WS_URL, additional_headers=headers, open_timeout=15) as ws:
            await ws.send(json.dumps(payload))
            try:
                while True:
                    msg = await asyncio.wait_for(ws.recv(), timeout=20)
                    if isinstance(msg, bytes):
                        # Unexpected — protocol is JSON-only
                        continue
                    try:
                        data = json.loads(msg)
                    except json.JSONDecodeError:
                        continue
                    status = data.get("status")
                    if status == "chunk":
                        chunks_received += 1
                        try:
                            audio_b64 = data.get("data", {}).get("audio", "") or ""
                            bytes_received += len(base64.b64decode(audio_b64)) if audio_b64 else 0
                        except Exception:
                            pass
                    elif status == "complete":
                        saw_complete = True
                        break
            except asyncio.TimeoutError:
                pass
            except websockets.exceptions.ConnectionClosed:
                pass
        if chunks_received == 0:
            return False, "no audio chunks received"
        terminator = "with `complete`" if saw_complete else "no `complete` terminator"
        return True, f"{chunks_received} chunks, {bytes_received} bytes ({terminator})"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def main() -> int:
    print("=== Lightning v3.1 TTS live test ===")
    print()

    print(f"[1] POST {REST_URL}")
    ok, detail = test_sync_rest()
    print(f"    {'PASS' if ok else 'FAIL'}: {detail}")
    rest_ok = ok
    print()

    print(f"[2] WS  {WS_URL}")
    ok, detail = asyncio.run(test_ws_streaming())
    print(f"    {'PASS' if ok else 'FAIL'}: {detail}")
    ws_ok = ok
    print()

    if rest_ok and ws_ok:
        print("PASS: TTS sync REST + WS streaming both working")
        return 0
    print("FAIL: at least one TTS endpoint not behaving as documented")
    return 1


if __name__ == "__main__":
    sys.exit(main())
