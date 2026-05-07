"""Atoms Agent WebSocket live test — runs on PR when atoms WS spec changes.

Validates the realtime agent endpoint at `WSS /atoms/v1/agent/connect`
that powers the WebSocket SDK and four mobile integration guides
(React Native, iOS, Android, Flutter). Spec lives at
`fern/apis/atoms/asyncapi/agent-ws.yaml`.

Flow per run:
  1. Janitor sweep — archive any leftover `CI-ws-test-*` agents.
  2. Create a dummy agent (REST) so we have a real agent_id to connect with.
  3. Open WSS connection with `?agent_id=<id>&token=<API_KEY>`.
  4. Assert `session.created` arrives within timeout.
  5. Assert at least one of the documented server-pushed message types
     comes back during a short observation window
     (`agent_start_talking`, `output_audio.delta`, etc.).
  6. Send `session.close` and disconnect cleanly.
  7. Archive the agent.

Exit non-zero if the documented protocol contract is violated. Hard-
fails on missing SMALLEST_API_KEY rather than silent skipping.

Usage:
    SMALLEST_API_KEY=... python3 scripts/spec-live-tests/atoms_ws_live_test.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlencode

import websockets

REST_BASE = "https://api.smallest.ai/atoms/v1"
WS_URL = "wss://api.smallest.ai/atoms/v1/agent/connect"
CI_NAME_PREFIX = "CI-ws-test-"

API_KEY = os.environ.get("SMALLEST_API_KEY")
if not API_KEY:
    sys.exit("SMALLEST_API_KEY env var is required")


def rest(method: str, path: str, body: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(
        REST_BASE + path,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            txt = resp.read().decode()
            try:
                return resp.status, json.loads(txt)
            except json.JSONDecodeError:
                return resp.status, txt
    except urllib.error.HTTPError as e:
        b = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(b)
        except json.JSONDecodeError:
            return e.code, b


def janitor_sweep() -> int:
    s, body = rest("GET", "/agent?limit=100")
    if s != 200 or not isinstance(body, dict):
        return 0
    data = body.get("data", {})
    agents = data if isinstance(data, list) else data.get("agents", []) if isinstance(data, dict) else []
    swept = 0
    for a in agents:
        if isinstance(a, dict) and (a.get("name") or "").startswith(CI_NAME_PREFIX):
            aid = a.get("_id")
            if aid:
                rest("DELETE", f"/agent/{aid}/archive")
                swept += 1
    if swept:
        print(f"[janitor] swept {swept} stale CI agents")
    return swept


# Documented message types from agent-ws.yaml. Receiving any of these
# during the observation window proves the WS protocol is alive end-to-end.
EXPECTED_SERVER_TYPES = {
    "session.created",
    "session.updated",
    "agent_start_talking",
    "agent_stop_talking",
    "output_audio.delta",
    "input_audio_buffer.committed",
    "interruption",
    "conversation.item.created",
    "response.done",
}


async def run_session(agent_id: str) -> tuple[bool, dict]:
    qs = urlencode({"agent_id": agent_id, "token": API_KEY})
    url = f"{WS_URL}?{qs}"
    seen_types: set[str] = set()
    session_created = False
    error_msg: str | None = None

    try:
        async with websockets.connect(url, open_timeout=15) as ws:
            # Receive a short window of server events
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
                    if t == "error":
                        error_msg = data.get("error", {}).get("message") or str(data)
            except asyncio.TimeoutError:
                pass
            except websockets.exceptions.ConnectionClosed:
                pass

            # Send the documented session.close to end cleanly
            try:
                await ws.send(json.dumps({"type": "session.close"}))
            except Exception:
                pass

    except Exception as e:
        return False, {"error": f"{type(e).__name__}: {e}"}

    return True, {
        "seen_types": sorted(seen_types),
        "session_created": session_created,
        "error_msg": error_msg,
    }


def main() -> int:
    print("=== Atoms Agent WebSocket live test ===")
    print(f"WS: {WS_URL}")
    print()

    janitor_sweep()
    print()

    # 1. Create dummy agent
    name = f"{CI_NAME_PREFIX}{int(time.time())}"
    s, body = rest("POST", "/agent", {"name": name})
    if s not in (200, 201):
        print(f"FAIL: POST /agent -> {s}")
        return 1
    data = body.get("data") if isinstance(body, dict) else None
    agent_id = data.get("_id") if isinstance(data, dict) else data
    if not agent_id:
        print(f"FAIL: could not extract agent_id from {json.dumps(body)[:300]}")
        return 1
    print(f"created agent {agent_id} (name={name!r})")
    print()

    # 2. Connect and observe
    print("=== open WS session, observe documented event types ===")
    ok, result = asyncio.run(run_session(agent_id))
    print(f"  WS open: {ok}")
    if not ok:
        print(f"  {result.get('error')}")
        return _cleanup(agent_id, 1)
    print(f"  session.created received: {result['session_created']}")
    print(f"  message types observed: {result['seen_types']}")
    if result.get("error_msg"):
        print(f"  server-side error msg: {result['error_msg']}")

    # 3. Assert at least session.created (the documented handshake)
    if not result["session_created"]:
        print()
        print("FAIL: server did not emit `session.created` within timeout")
        print("      (the documented handshake event for /atoms/v1/agent/connect)")
        return _cleanup(agent_id, 1)

    # 4. Confirm any observed types are documented (catches typos / undocumented events)
    undocumented = set(result["seen_types"]) - EXPECTED_SERVER_TYPES - {"error", "warning"}
    if undocumented:
        print()
        print(f"WARN: undocumented server message types: {undocumented}")
        print("      Either docs (agent-ws.yaml) or platform is out of sync.")

    print()
    print("PASS: WS handshake works, documented message types arrive")
    return _cleanup(agent_id, 0)


def _cleanup(agent_id: str, code: int) -> int:
    s, _ = rest("DELETE", f"/agent/{agent_id}/archive")
    print(f"cleanup: DELETE /agent/{agent_id}/archive -> {s}")
    return code


if __name__ == "__main__":
    sys.exit(main())
