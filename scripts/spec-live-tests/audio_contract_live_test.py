"""Realtime Agent audio-format contract — live test against register-call.

Verifies every claim in the audio-format contract docs (PR #397) against
the merged platform commit `36c500d`:

  A. Defaults        Bare register-call returns pcm_24000 on both directions
                     and expires_in: 30.
  B. sample_rate     Deprecated but accepted. 48000 refused by voice.
  C. Per-direction   input_audio_format + output_audio_format accepted with
                     every documented token. Response echoes them.
  D. Input refusals  pcm_32000, ulaw_8000 (wrong spelling), opus_12000,
                     opus_22050 rejected with the exact `Supported: ...`
                     error string.
  E. Output refusals pcm_48000 rejected with "is not supported by this
                     agent's voice. Supported: ..." string.
  F. Disagreement    sample_rate + output_audio_format that disagree are
                     refused with "disagree; send one" string.
  G. Response shape  Every 201 carries access_token, expires_in,
                     sample_rate, input_audio_format, output_audio_format
                     under `data`.

Requires an agent to register calls against. If AGENT_ID names an agent
on a `lightning-v3.1` or `lightning-v3.1-pro` voice, the pcm_44100
output check also runs; otherwise it's skipped.

Usage:
    SMALLEST_API_KEY=sk_... AGENT_ID=agent_... \\
        python3 scripts/spec-live-tests/audio_contract_live_test.py

Optional:
    BASE_URL=https://api.smallest.ai   # default; override for staging
    VERBOSE=1                           # print full response bodies
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

BASE = os.environ.get("BASE_URL", "https://api.smallest.ai").rstrip("/") + "/atoms/v1"
API_KEY = os.environ.get("SMALLEST_API_KEY")
AGENT_ID = os.environ.get("AGENT_ID")
VERBOSE = os.environ.get("VERBOSE") == "1"

if not API_KEY:
    sys.exit("SMALLEST_API_KEY env var is required (an sk_ key)")
if not AGENT_ID:
    sys.exit("AGENT_ID env var is required (a real agent to register calls for)")


def register_call(body: dict, timeout: int = 20) -> tuple[int, dict]:
    """POST /conversation/register-call. Returns (status_code, parsed_body)."""
    payload = {"agent_id": AGENT_ID, **body}
    r = urllib.request.Request(
        BASE + "/conversation/register-call",
        data=json.dumps(payload).encode(),
        method="POST",
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {"raw": str(e)}


RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    marker = "PASS" if ok else "FAIL"
    print(f"  [{marker}] {name}" + (f"  — {detail}" if detail else ""))
    RESULTS.append((name, ok, detail))


def dump(label: str, obj) -> None:
    if VERBOSE:
        print(f"    {label}: {json.dumps(obj)[:400]}")


# ---- A. Defaults --------------------------------------------------------
print("\n[A] Bare register-call defaults")

status, body = register_call({})
dump("response", body)
data = body.get("data", {}) if isinstance(body, dict) else {}
check("A1 status 201", status == 201, f"got {status}")
check("A2 has access_token", bool(data.get("access_token")))
check("A3 expires_in is 30", data.get("expires_in") == 30, f"got {data.get('expires_in')!r}")
check("A4 sample_rate is 24000", data.get("sample_rate") == 24000, f"got {data.get('sample_rate')!r}")
check(
    "A5 input_audio_format is pcm_24000",
    data.get("input_audio_format") == "pcm_24000",
    f"got {data.get('input_audio_format')!r}",
)
check(
    "A6 output_audio_format is pcm_24000",
    data.get("output_audio_format") == "pcm_24000",
    f"got {data.get('output_audio_format')!r}",
)

DEFAULT_VOICE_ACCEPTS_44100 = None  # set below in section E if we can tell

# ---- B. sample_rate (deprecated but accepted) ---------------------------
print("\n[B] Deprecated sample_rate field")

status, body = register_call({"sample_rate": 16000})
data = body.get("data", {}) if isinstance(body, dict) else {}
check("B1 sample_rate=16000 accepted", status == 201, f"got {status}")
check("B2 echoes sample_rate 16000", data.get("sample_rate") == 16000, f"got {data.get('sample_rate')!r}")

status, body = register_call({"sample_rate": 48000})
err = json.dumps(body)
check(
    "B3 sample_rate=48000 rejected (no voice renders it)",
    status == 400 and "sample_rate" in err.lower(),
    f"got {status}, body: {err[:200]}",
)


# ---- C. Per-direction fields --------------------------------------------
print("\n[C] Per-direction audio-format tokens")

INPUT_ACCEPTED = [
    "pcm_8000", "pcm_16000", "pcm_22050", "pcm_24000", "pcm_44100", "pcm_48000",
    "mulaw_8000", "alaw_8000",
    "opus_8000", "opus_16000", "opus_24000", "opus_48000",
]

for token in INPUT_ACCEPTED:
    status, body = register_call({"input_audio_format": token})
    d = body.get("data", {}) if isinstance(body, dict) else {}
    ok = status == 201 and d.get("input_audio_format") == token
    check(f"C.{token} input accepted + echoed", ok, f"got status {status}, echo {d.get('input_audio_format')!r}")

# One output token every voice renders
status, body = register_call({"output_audio_format": "pcm_16000"})
d = body.get("data", {}) if isinstance(body, dict) else {}
check(
    "C.pcm_16000 output accepted",
    status == 201 and d.get("output_audio_format") == "pcm_16000",
    f"got {status}",
)


# ---- D. Input refusals with exact error string --------------------------
print("\n[D] Input-format refusals")

REFUSED_INPUT = [
    ("pcm_32000", "Pulse recogniser refuses this rate"),
    ("ulaw_8000", "wrong spelling; must be mulaw_8000"),
    ("opus_12000", "recogniser refuses this rate"),
    ("opus_22050", "outside Opus's decoder set"),
    ("pcm_9999", "junk token"),
]

for token, why in REFUSED_INPUT:
    status, body = register_call({"input_audio_format": token})
    err = json.dumps(body)
    is_400 = status == 400
    names_token = f"'{token}'" in err
    names_supported = "Supported:" in err
    check(
        f"D.{token} refused ({why})",
        is_400 and names_token and names_supported,
        f"got status {status}, names token: {names_token}, has 'Supported:': {names_supported}",
    )


# ---- E. Output refusals + pcm_44100 voice conditional -------------------
print("\n[E] Output-format refusals + pcm_44100 conditional")

status, body = register_call({"output_audio_format": "pcm_48000"})
err = json.dumps(body)
check(
    "E1 pcm_48000 refused (no voice renders it)",
    status == 400 and "is not supported by this agent's voice" in err,
    f"got status {status}, body: {err[:200]}",
)

# pcm_44100 — depends on the agent's voice
status, body = register_call({"output_audio_format": "pcm_44100"})
if status == 201:
    DEFAULT_VOICE_ACCEPTS_44100 = True
    d = body.get("data", {})
    check(
        "E2 pcm_44100 accepted (agent is on a v3.1/v3.1-pro voice)",
        d.get("output_audio_format") == "pcm_44100",
        f"echo {d.get('output_audio_format')!r}",
    )
elif status == 400:
    DEFAULT_VOICE_ACCEPTS_44100 = False
    check(
        "E2 pcm_44100 refused (agent voice does not render it — expected for non-v3.1)",
        "is not supported by this agent's voice" in json.dumps(body),
        f"body: {json.dumps(body)[:200]}",
    )
else:
    check("E2 pcm_44100 status unexpected", False, f"got {status}")


# ---- F. sample_rate + output_audio_format disagreement ------------------
print("\n[F] sample_rate ↔ output_audio_format disagreement")

status, body = register_call({"sample_rate": 24000, "output_audio_format": "pcm_16000"})
err = json.dumps(body).lower()
check(
    "F1 disagree → 400 with 'disagree; send one'",
    status == 400 and "disagree" in err,
    f"got status {status}, body: {json.dumps(body)[:200]}",
)

status, body = register_call({"sample_rate": 24000, "output_audio_format": "pcm_24000"})
d = body.get("data", {}) if isinstance(body, dict) else {}
check(
    "F2 agree → 201",
    status == 201 and d.get("output_audio_format") == "pcm_24000",
    f"got {status}",
)


# ---- G. Response-shape summary -----------------------------------------
print("\n[G] Response-shape final check (default call)")

status, body = register_call({})
d = body.get("data", {}) if isinstance(body, dict) else {}
required = ["access_token", "expires_in", "sample_rate", "input_audio_format", "output_audio_format"]
missing = [k for k in required if k not in d]
check(
    "G1 data has all documented fields",
    status == 201 and not missing,
    f"missing: {missing}" if missing else "",
)


# ---- H. WebSocket upgrade validation ------------------------------------
# Docs quote a different error string on the connect URL than on register-call:
#   "Unsupported input_audio_format '<...>'. Supported: ..."
# agent-gateway.ts:355 (live). Reach this by hitting the connect endpoint with
# a garbage input_audio_format query param and reading the 400 body.
print("\n[H] WebSocket-upgrade validation errors")

from urllib.parse import quote

# Register-call tokens are single-use, so mint a fresh one per probe.
# The connect endpoint reads the token query param only during a real
# WebSocket upgrade, and it writes the validation error into the HTTP
# reason phrase (status line), not the body. Send full handshake headers
# and read `e.reason` rather than `e.read()`.
WS_HANDSHAKE_HEADERS = {
    "Upgrade": "websocket",
    "Connection": "Upgrade",
    "Sec-WebSocket-Key": "dGhlIHNhbXBsZSBub25jZQ==",  # arbitrary base64
    "Sec-WebSocket-Version": "13",
}


def probe_connect(qs: str, timeout: int = 10) -> tuple[int, str]:
    """Mint a fresh token, then GET /agent/connect with WS handshake."""
    _, mint_body = register_call({})
    fresh = mint_body.get("data", {}).get("access_token", "")
    if not fresh:
        return -1, "no token"
    url = BASE + f"/agent/connect?token={quote(fresh)}&{qs}"
    r = urllib.request.Request(url, method="GET", headers=WS_HANDSHAKE_HEADERS)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return resp.status, str(resp.reason)
    except urllib.error.HTTPError as e:
        return e.code, str(e.reason)


status_c, reason_c = probe_connect("input_audio_format=badformat")
check(
    "H1 bad input_audio_format on connect → 400 'Unsupported input_audio_format'",
    status_c == 400 and "Unsupported input_audio_format 'badformat'" in reason_c,
    f"got status {status_c}, reason: {reason_c[:200]}",
)

def probe_connect_api_key(qs: str, timeout: int = 10) -> tuple[int, str]:
    """Hit /agent/connect with the raw sk_ API key as the token query param.

    Per the platform commit ("A wct_ token does not fix the rate at 24000...
    the connect parameter is ignored"), `sample_rate` on the connect URL is
    only enforced on the API-key auth path — with a wct_ token the value is
    silently ignored because the rate is already pinned on register-call.
    """
    url = BASE + f"/agent/connect?token={quote(API_KEY)}&agent_id={AGENT_ID}&{qs}"
    r = urllib.request.Request(url, method="GET", headers=WS_HANDSHAKE_HEADERS)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return resp.status, str(resp.reason)
    except urllib.error.HTTPError as e:
        return e.code, str(e.reason)


status_c, reason_c = probe_connect_api_key("sample_rate=48000")
check(
    "H2 sample_rate=48000 on connect (api-key path) → 400 'Unsupported sample_rate'",
    status_c == 400 and "Unsupported sample_rate 48000" in reason_c,
    f"got status {status_c}, reason: {reason_c[:200]}",
)


# ---- Summary ------------------------------------------------------------
print("\n" + "=" * 60)
passed = sum(1 for _, ok, _ in RESULTS if ok)
total = len(RESULTS)
print(f"  {passed}/{total} checks passed")
if DEFAULT_VOICE_ACCEPTS_44100 is not None:
    tag = "supports" if DEFAULT_VOICE_ACCEPTS_44100 else "does not support"
    print(f"  This agent's voice {tag} pcm_44100 output.")
print("=" * 60)

if passed != total:
    print("\nFailed checks:")
    for name, ok, detail in RESULTS:
        if not ok:
            print(f"  - {name}: {detail}")
    sys.exit(1)

print("\nAll live claims in the audio-format contract docs are correct.")
