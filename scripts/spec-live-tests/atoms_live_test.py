"""Atoms OpenAPI live test — runs on PR when fern/apis/atoms/** changes.

Verifies that fields documented in `CreateAgentRequest` (which propagate
into `DraftConfigRequest` via allOf) are actually accepted by the live
platform and persist on the draft. Catches the kind of drift PR #121
surfaced: the spec adds a field but the platform silently drops it, or
vice versa.

Flow per run:
  1. Janitor sweep — archive any leftover `CI-spec-test-*` agents from
     prior runs (cleanup is via DELETE /agent/{id}/archive, not /:id).
  2. Create a dummy agent with a CI-prefixed name.
  3. Find the `Main` branch (auto-created with the agent) and its head
     revision (auto-published on agent create).
  4. PUT every documented config field onto the branch's open draft in
     a single bulk request. The endpoint upserts the draft.
  5. GET /agent/{id}/diff?a=<branchId>:draft&b=<headRevisionId> and
     assert each field shows up in the diff with its newValue matching
     what we sent.
  6. Archive the agent (best-effort cleanup; janitor handles strays).

Exit non-zero if any field rejected or fails round-trip. The PR cannot
merge until either the spec or the platform is corrected.

Usage:
    SMALLEST_API_KEY=... python3 scripts/spec-live-tests/atoms_live_test.py
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = "https://api.smallest.ai/atoms/v1"
CI_NAME_PREFIX = "CI-spec-test-"

API_KEY = os.environ.get("SMALLEST_API_KEY")
if not API_KEY:
    sys.exit("SMALLEST_API_KEY env var is required")


def req(method: str, path: str, body: dict | None = None, timeout: int = 30):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(
        BASE + path,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            payload = resp.read().decode()
            try:
                return resp.status, json.loads(payload)
            except json.JSONDecodeError:
                return resp.status, payload
    except urllib.error.HTTPError as e:
        body_txt = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(body_txt)
        except json.JSONDecodeError:
            return e.code, body_txt


def janitor_sweep() -> int:
    """Archive any CI-prefixed agents leftover from previous runs.

    Returns the number swept. Best-effort; failures are logged not raised.
    """
    status, body = req("GET", "/agent?limit=100")
    if status != 200 or not isinstance(body, dict):
        print(f"[janitor] could not list agents (status={status}); skipping sweep")
        return 0
    data = body.get("data", {})
    agents = data if isinstance(data, list) else data.get("agents", []) if isinstance(data, dict) else []
    swept = 0
    for a in agents:
        if not isinstance(a, dict):
            continue
        name = a.get("name") or ""
        if not name.startswith(CI_NAME_PREFIX):
            continue
        aid = a.get("_id")
        if not aid:
            continue
        s, _ = req("DELETE", f"/agent/{aid}/archive")
        if 200 <= s < 300:
            swept += 1
        else:
            print(f"[janitor] archive {aid} ({name!r}) -> {s}")
    if swept:
        print(f"[janitor] swept {swept} stale CI agents")
    return swept


# Each case: (top-level field name, value to send).
# Each value is chosen so it's distinguishable from the platform default
# documented in the OpenAPI — that way the diff endpoint will flag it.
#
# NOTE: this list must be kept in sync with the documented fields in
# CreateAgentRequest in fern/apis/atoms/openapi/openapi.yaml. When you
# add a field to the spec, add a case here in the same PR or this test
# is a paper tiger.
CASES: list[tuple[str, object]] = [
    ("firstMessage", "CI test first message"),
    ("muteUserUntilFirstBotResponse", True),
    ("allowInterruptions", False),
    ("waitForUserToSpeakFirst", True),
    ("interruptionBackoffTimer", 5),
    ("smartTurnConfig", {"isEnabled": True, "waitTimeInSecs": 2.5}),
    ("voiceDetectionConfig", {
        "confidence": 0.55,
        "minVolume": 0.25,
        "triggerTimeInSecs": 0.35,
        "releaseTimeInSecs": 0.55,
    }),
    ("voiceMailDetectionConfig", {
        "enabled": True,
        "endText": "CI voicemail end text.",
    }),
    # Send the opposite of each field's platform default to force a diff entry.
    # denoisingConfig defaults to isEnabled: False; redactionConfig defaults to
    # isEnabled: True (DEFAULT_DENOISING_CONFIG / DEFAULT_REDACTION_CONFIG_IS_ENABLED
    # in atoms-types). Sending a value equal to the default produces no diff.
    ("denoisingConfig", {"isEnabled": True}),
    ("redactionConfig", {"isEnabled": False}),
    ("pronunciationDicts", [{"word": "CITEST", "pronunciation": "see-eye-test"}]),
    ("llmIdleTimeoutConfig", {
        "chatTimeoutTimeInSecs": 25,
        "webcallTimeoutTimeInSecs": 35,
        "telephonyTimeoutTimeInSecs": 45,
        "maxRetries": 3,
    }),
    ("sessionTimeoutConfig", {"timeoutTimeInSecs": 1500}),
    ("timezone", {"label": "Asia/Kolkata", "offset": 330}),
    ("synthesizer", {"sampleRate": 44100}),
]


def field_in_diff(diff_data: dict, field: str, expected) -> bool:
    """Check whether `field` shows up in any section's `changes` list with
    `newValue == expected` (or, for object/array fields, with at least
    one nested path that hangs off `field`).
    """
    diffs = diff_data.get("diffs", []) if isinstance(diff_data, dict) else []
    for section in diffs:
        for ch in section.get("changes", []):
            path = ch.get("path", "")
            new_val = ch.get("newValue")
            # exact field match — scalar case
            if path == field and new_val == expected:
                return True
            # nested-prefix match — object / array fields show up as
            # field.subkey or field[0].subkey paths
            if path.startswith(field + ".") or path.startswith(field + "["):
                return True
            # special case: the synthesizer block flattens .sampleRate
            # into a synthesizerSampleRate path
            if field == "synthesizer" and path == "synthesizerSampleRate":
                return True
    return False


def main() -> int:
    print("=== Atoms OpenAPI live test ===")
    print(f"base: {BASE}")
    print()

    janitor_sweep()
    print()

    # 1. Create agent
    name = f"{CI_NAME_PREFIX}{int(time.time())}"
    s, body = req("POST", "/agent", {"name": name})
    if s not in (200, 201):
        print(f"FAIL: POST /agent -> {s} body={json.dumps(body)[:300]}")
        return 1
    data = body.get("data") if isinstance(body, dict) else None
    agent_id = data.get("_id") if isinstance(data, dict) else data
    if not agent_id:
        print(f"FAIL: could not extract agent_id from {json.dumps(body)[:300]}")
        return 1
    print(f"created agent {agent_id} (name={name!r})")

    # 2. Find the Main branch and its head revision.
    # BranchSummary shape: {branch: {...}, isLive, hasOpenDraft,
    # revisionsCount, headRevisionNumber, createdByName, updatedByName}
    # The branch _id, isDefault, and headRevisionId live on inner .branch.
    s, body = req("GET", f"/agent/{agent_id}/branches")
    if s != 200:
        print(f"FAIL: GET /branches -> {s}")
        return _cleanup_and_exit(agent_id, 1)
    branches = body.get("data", {}).get("branches", []) if isinstance(body, dict) else []
    main = next(
        (b for b in branches if isinstance(b, dict) and b.get("branch", {}).get("isDefault")),
        None,
    )
    if not main:
        print(f"FAIL: no Main branch on new agent")
        return _cleanup_and_exit(agent_id, 1)
    main_branch_id = main["branch"].get("_id")
    head_revision_id = main["branch"].get("headRevisionId")
    if not (main_branch_id and head_revision_id):
        print(f"FAIL: Main branch missing _id / headRevisionId: {json.dumps(main)[:300]}")
        return _cleanup_and_exit(agent_id, 1)
    print(f"main branch _id={main_branch_id}, head revision={head_revision_id}")
    print()

    # 3. Bulk PUT every field onto the branch's draft (upserts open draft).
    patch_body = {field: value for field, value in CASES}
    s, body = req("PUT", f"/agent/{agent_id}/branches/{main_branch_id}/draft", patch_body)
    if s != 200:
        print(f"FAIL: PUT draft -> {s} body={json.dumps(body)[:500]}")
        return _cleanup_and_exit(agent_id, 1)
    print(f"PUT draft -> 200 (sent {len(CASES)} fields)")

    # 4. Read diff (head → draft) and verify each field shows up.
    # The `/diff` endpoint treats `a` as the base and `b` as the target,
    # so newValue reflects the `b` side. Put the draft on `b` so the
    # values we PUT'd show up as `newValue` for scalar assertions.
    diff_path = f"/agent/{agent_id}/diff?a={head_revision_id}&b={main_branch_id}:draft"
    s, body = req("GET", diff_path)
    if s != 200:
        print(f"FAIL: GET /diff -> {s}")
        return _cleanup_and_exit(agent_id, 1)
    diff_data = body.get("data", {}) if isinstance(body, dict) else {}

    failures: list[str] = []
    for field, expected in CASES:
        ok = field_in_diff(diff_data, field, expected)
        symbol = "✓" if ok else "✗"
        print(f"  {field:35s} round-tripped: {symbol}")
        if not ok:
            failures.append(field)

    print()
    if failures:
        print(f"FAIL: {len(failures)}/{len(CASES)} fields did NOT round-trip:")
        for f in failures:
            print(f"  - {f}")
        print()
        print("=== diff endpoint response (for debugging) ===")
        print(json.dumps(diff_data, indent=2)[:3000])
        return _cleanup_and_exit(agent_id, 1)

    print(f"PASS: {len(CASES)}/{len(CASES)} fields round-tripped")
    print()

    # 6. Assert the documented deleteAgent operation works.
    # Spec maps `operationId: deleteAgent` to DELETE /agent/{id}/archive.
    # Anything other than 2xx here means the docs are claiming a path
    # the platform doesn't serve.
    print("=== verify deleteAgent (DELETE /agent/{id}/archive) ===")
    s, body = req("DELETE", f"/agent/{agent_id}/archive")
    if not (200 <= s < 300):
        print(f"FAIL: DELETE /agent/{{id}}/archive -> {s} body={json.dumps(body)[:300]}")
        return 1
    print(f"  DELETE /agent/{{id}}/archive -> {s} ✓")

    # Confirm the agent is no longer in the listing (or marked archived).
    list_status, list_body = req("GET", "/agent?limit=200")
    still_there = False
    if list_status == 200 and isinstance(list_body, dict):
        data = list_body.get("data", {})
        agents = data if isinstance(data, list) else data.get("agents", [])
        still_there = any(
            isinstance(a, dict) and a.get("_id") == agent_id and not a.get("archived")
            for a in agents
        )
    if still_there:
        print(f"FAIL: agent {agent_id} still listed as non-archived after DELETE")
        return 1
    print(f"  agent no longer listed (or marked archived) ✓")

    print()
    print("PASS: spec live test complete")
    return 0


def _cleanup_and_exit(agent_id: str, code: int) -> int:
    """Best-effort archive of the test agent on failure paths.

    Successful runs delete via the explicit deleteAgent assertion above.
    """
    s, _ = req("DELETE", f"/agent/{agent_id}/archive")
    print(f"cleanup: DELETE /agent/{agent_id}/archive -> {s}")
    return code


if __name__ == "__main__":
    sys.exit(main())
