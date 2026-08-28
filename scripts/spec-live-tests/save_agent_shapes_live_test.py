"""Save-agent shapes — live test against PUT /agent/{id}/branches/{branchId}/draft.

Verifies that:
  A. A correct-per-docs payload (native JSON types) is accepted (200).
  B-D. Cheerio's failure modes (stringified array, stringified boolean, double-wrap
       array) are refused with the exact Zod-style error strings we quote in the docs.
  E. `timezone: "Asia/Kolkata"` (Vimal's shape, matching our pre-fix docs) is
     refused — proves the timezone type must be an object.
  F. `timezone: {label, offset}` is accepted — proves the correct shape works.
  G. `language.default: "te"` is accepted — proves the 18-code enum is real and
     the docs must not narrow it to 9.

Every check is a claim we make in openapi.yaml. If any fails, the docs are wrong
against production and the PR should not merge.

Creates a throwaway agent (`docs-shape-test-DEL`), runs the matrix, then
archives the agent. Safe to run against prod: register-call is not invoked and
the agent is never assigned a phone number.

Usage:
    SMALLEST_API_KEY=sk_... python3 scripts/spec-live-tests/save_agent_shapes_live_test.py
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

BASE = os.environ.get("BASE_URL", "https://api.smallest.ai").rstrip("/") + "/atoms/v1"
KEY = os.environ.get("SMALLEST_API_KEY")
if not KEY:
    sys.exit("SMALLEST_API_KEY env var is required (an sk_ key)")


def req(method: str, path: str, body: dict | None = None, timeout: int = 20):
    r = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
        headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return resp.status, json.load(resp)
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


# ---- Setup: create + resolve branch ------------------------------------
print("\n[Setup] Create throwaway agent + resolve branch")
s, d = req("POST", "/agent", {"name": "docs-shape-test-DEL", "workflowType": "single_prompt"})
if s != 201 or not isinstance(d.get("data"), str):
    sys.exit(f"cannot create test agent: status={s} body={json.dumps(d)[:200]}")
agent_id = d["data"]
print(f"  agent {agent_id}")

s, d = req("GET", f"/agent/{agent_id}/branches")
if s != 200:
    sys.exit(f"cannot resolve branches: status={s}")
branch_id = d["data"]["branches"][0]["branch"]["_id"]
print(f"  branch {branch_id}")


def put_draft(body: dict) -> tuple[int, dict]:
    return req("PUT", f"/agent/{agent_id}/branches/{branch_id}/draft", body)


def error_str(body: dict) -> str:
    errs = body.get("errors") if isinstance(body, dict) else None
    if isinstance(errs, list) and errs:
        return errs[0]
    return json.dumps(body)[:200]


# ---- A. Correct-per-docs (native JSON types) ---------------------------
print("\n[A] Correct-per-docs body: native JSON types")

s, d = put_draft({
    "globalPrompt": "You are a test agent",
    "language": {"default": "en", "supported": ["en"], "switching": {"isEnabled": False}},
})
check("A1 native JSON types → 200", s == 200, f"got {s}")


# ---- B–D. Cheerio's failure modes --------------------------------------
print("\n[B–D] Cheerio's stringified failure modes")

s, d = put_draft({"language": {"default": "en", "supported": "en", "switching": {"isEnabled": False}}})
err = error_str(d)
check(
    "B language.supported=\"en\" → 400 'Expected array, received string'",
    s == 400 and "Expected array, received string" in err,
    f"got status={s} err={err[:180]!r}",
)

s, d = put_draft({"language": {"default": "en", "supported": ["en"], "switching": {"isEnabled": "false"}}})
err = error_str(d)
check(
    "C switching.isEnabled=\"false\" → 400 'Expected boolean, received string'",
    s == 400 and "Expected boolean, received string" in err,
    f"got status={s} err={err[:180]!r}",
)

s, d = put_draft({"language": {"default": "en", "supported": ["[\"en\"]"], "switching": {"isEnabled": False}}})
err = error_str(d)
check(
    "D supported[0]=\"[\\\"en\\\"]\" → 400 'Invalid enum value'",
    s == 400 and "Invalid enum value" in err,
    f"got status={s} err={err[:180]!r}",
)


# ---- E–F. Vimal's timezone shape ---------------------------------------
print("\n[E–F] timezone type contract")

s, d = put_draft({"timezone": "Asia/Kolkata"})
err = error_str(d)
check(
    "E timezone as string → 400 'Expected object, received string'",
    s == 400 and "Expected object, received string" in err,
    f"got status={s} err={err[:180]!r}",
)

s, d = put_draft({"timezone": {"label": "(GMT+5:30) Asia/Kolkata", "offset": 330}})
check("F timezone as {label, offset} → 200", s == 200, f"got {s}")


# ---- G. 18-code language enum ------------------------------------------
print("\n[G] Full 18-code language enum accepted")

# Codes previously undocumented (docs had 9, backend has 18): te, kn, ml, fr, de, it, nl, pt, ru
UNDOCUMENTED_BEFORE = ["te", "kn", "ml", "fr", "de", "it", "nl", "pt", "ru"]
for code in UNDOCUMENTED_BEFORE:
    s, d = put_draft({"language": {"default": code, "supported": [code], "switching": {"isEnabled": False}}})
    check(f"G.{code} accepted as language.default", s == 200, f"got {s}")


# ---- Cleanup -----------------------------------------------------------
print("\n[Cleanup] Archive test agent")
s, d = req("DELETE", f"/agent/{agent_id}/archive")
print(f"  archive: {s}")


# ---- Summary -----------------------------------------------------------
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

print("\nAll save-agent shape claims in openapi.yaml match live production.")
