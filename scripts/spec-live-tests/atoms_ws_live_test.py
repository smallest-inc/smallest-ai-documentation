"""Atoms Agent WebSocket live test — runs on PR when atoms WS spec changes.

Validates the realtime agent endpoint at `WSS /atoms/v1/agent/connect`
that powers the WebSocket SDK and four mobile integration guides
(React Native, iOS, Android, Flutter). Spec lives at
`fern/apis/atoms/asyncapi/agent-ws.yaml`.

Connects against a long-lived test-fixture agent (configured with the
working tenant defaults — LLM, voice, transcriber, prompt) instead of
creating a fresh agent each run. The fixture's agent_id is baked in
as `DEFAULT_TEST_AGENT_ID` below; override via `ATOMS_WS_TEST_AGENT_ID`
env var if needed.

Flow per run:
  1. Connect to `WSS /atoms/v1/agent/connect?agent_id=<fixture>` with
     `Authorization: Bearer <key>` header.
  2. Assert `session.created` arrives within timeout. The session_id
     and call_id from this event are logged so backend devs can grep
     their logs against any failure.
  3. Observe documented server-pushed message types (`agent_start_talking`,
     `output_audio.delta`, etc.) for the rest of the window.
  4. Send `session.close` to end cleanly.

Retries: 3x with exponential backoff on 5xx / transport errors. 4xx
fails fast (real auth/config bug). Hard pass/fail — no soft-pass.

Usage:
    SMALLEST_API_KEY=... python3 scripts/spec-live-tests/atoms_ws_live_test.py
    SMALLEST_API_KEY=... ATOMS_WS_TEST_AGENT_ID=<id> python3 scripts/...
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from urllib.parse import urlencode

import websockets

WS_URL = "wss://api.smallest.ai/atoms/v1/agent/connect"

# Long-lived configured fixture on the test tenant. Has the working
# tenant defaults (gpt-4.1 SLM, lightning-v3.1 / daniel voice, deepgram
# transcriber, default prompt). Verified handshake works — session.created
# returns immediately. Name on the platform: "CI-ws-test-fixture-DO-NOT-DELETE".
# DO NOT DELETE this agent — CI hard-fails if it's gone.
DEFAULT_TEST_AGENT_ID = "69fc27fb038062dc952d2bba"

API_KEY = os.environ.get("SMALLEST_API_KEY")
if not API_KEY:
    sys.exit("SMALLEST_API_KEY env var is required")

# Override via env var if the CI tenant ever needs a different fixture.
AGENT_ID = os.environ.get("ATOMS_WS_TEST_AGENT_ID") or DEFAULT_TEST_AGENT_ID


# Documented message types from agent-ws.yaml. Sourced by grepping
# `const:` declarations in the spec — keep this list in sync when the
# spec adds/removes message variants.
EXPECTED_SERVER_TYPES = {
    "session.created",
    "session.closed",
    "agent_start_talking",
    "agent_stop_talking",
    "output_audio.delta",
    "interruption",
    "transcript",
    "error",
}


async def _attempt_session(url: str, headers: dict) -> tuple[bool, dict]:
    seen_types: set[str] = set()
    session_created = False
    session_id: str | None = None
    call_id: str | None = None
    error_msg: str | None = None
    try:
        async with websockets.connect(url, additional_headers=headers, open_timeout=15) as ws:
            try:
                deadline = time.time() + 8
                while time.time() < deadline:
                    msg = await asyncio.wait_for(ws.recv(), timeout=max(0.5, deadline - time.time()))
                    if isinstance(msg, bytes):
                        continue
                    try:
                        data = json.loads(msg)
                    except json.JSONDecodeError:
                        continue
                    t = data.get("type")
                    if t:
                        seen_types.add(t)
                    if t == "session.created":
                        session_created = True
                        session_id = data.get("session_id")
                        call_id = data.get("call_id")
                    if t == "error":
                        error_msg = data.get("error", {}).get("message") or str(data)
            except asyncio.TimeoutError:
                pass
            except websockets.exceptions.ConnectionClosed:
                pass

            try:
                await ws.send(json.dumps({"type": "session.close"}))
            except Exception:
                pass
    except Exception as e:
        return False, {"error": f"{type(e).__name__}: {e}"}

    return True, {
        "seen_types": sorted(seen_types),
        "session_created": session_created,
        "session_id": session_id,
        "call_id": call_id,
        "error_msg": error_msg,
    }


async def run_session() -> tuple[bool, dict]:
    qs = urlencode({"agent_id": AGENT_ID})
    url = f"{WS_URL}?{qs}"
    headers = {"Authorization": f"Bearer {API_KEY}"}

    last_result: dict = {}
    for attempt in range(1, 4):
        ok, result = await _attempt_session(url, headers)
        if ok:
            return True, result
        last_result = result
        err = result.get("error") or ""
        # 4xx → bail immediately, retrying won't help
        if "HTTP 4" in err:
            return False, result
        # 5xx or transport error → wait and retry
        if attempt < 3:
            wait = attempt * 3
            print(f"  attempt {attempt}: {err[:100]} — retrying in {wait}s")
            await asyncio.sleep(wait)
    return False, last_result


def is_session_bootstrap_5xx(error_msg: str) -> bool:
    return "HTTP 500" in error_msg or "HTTP 502" in error_msg or "HTTP 503" in error_msg


def main() -> int:
    print("=== Atoms Agent WebSocket live test ===")
    print(f"WS:       {WS_URL}")
    print(f"agent_id: {AGENT_ID} {'(env override)' if AGENT_ID != DEFAULT_TEST_AGENT_ID else '(default fixture)'}")
    print()

    ok, result = asyncio.run(run_session())
    if not ok:
        err = result.get("error") or ""
        print(f"  {err}")
        if is_session_bootstrap_5xx(err):
            print()
            print("=" * 72)
            print("HARD FAIL: endpoint returned 5xx after 3 retries.")
            print("           Auth + reachability OK (no 4xx, request reached server).")
            print("           Likely backend bug, NOT a docs/spec issue:")
            print("             - Express route ordering: /agent/connect matched")
            print("               by /agent/:id catch-all → CastError on findById")
            print("             - Or session orchestrator can't bootstrap the agent")
            print("           Check Sentry for `CastError GET /atoms/v1/agent/connect`")
            print("           in atoms-backend project (recent events match this run).")
            print("           Force-merge is allowed when this is the only red check")
            print("           AND backend team has acknowledged the upstream bug.")
            print("=" * 72)
        return 1

    print(f"  session.created: {result['session_created']}")
    print(f"  session_id:      {result.get('session_id')}")
    print(f"  call_id:         {result.get('call_id')}")
    print(f"  message types:   {result['seen_types']}")
    if result.get("error_msg"):
        print(f"  server-side error msg: {result['error_msg']}")

    if not result["session_created"]:
        print()
        print("FAIL: server did not emit `session.created` within timeout")
        return 1

    undocumented = set(result["seen_types"]) - EXPECTED_SERVER_TYPES
    if undocumented:
        print()
        print(f"WARN: undocumented server message types: {undocumented}")
        print("      Either docs (agent-ws.yaml) or platform is out of sync.")

    print()
    print("PASS: WS handshake works, documented message types arrive")
    return 0


if __name__ == "__main__":
    sys.exit(main())
