"""Atoms (agent platform) — read-only API surface probe.

For each safe (read-only) endpoint of interest, calls the live API and
records observable shape:

- HTTP status code + content type
- Whether the response is the expected envelope `{status, data}`
- Top-level keys on the data payload (so additions / removals / renames
  flag a diff)
- Item count buckets for list endpoints (so "list went from non-empty
  to empty" or vice versa flags a diff without coupling to exact counts)

Output is one canonical JSON record per endpoint. The diff layer
(`diff.py`) compares against `baseline-atoms.json` and flags any change.

Why this exists
---------------
Same rationale as the Pulse STT and Lightning TTS probes: the API can
silently drop a response field, rename one, change a default, or add a
required-but-undocumented param. Customers hit the change before docs
catch up. A weekly probe surfaces this without anyone having to remember
to look. Atoms is the platform we get the most "but the docs said…"
support tickets about, so wiring it up was overdue.

Important — read-only only
--------------------------
This probe never POSTs, PATCHes, or DELETEs. All test cases are GET
endpoints that return list/info data. We deliberately don't probe
mutation endpoints (POST /agent, POST /conversation/outbound, DELETE
/agent/{id}, etc.) because they'd create or destroy real resources on
the operator's account every Monday at 03:30 UTC.

Future extension: bootstrap the test-case list from
smallest-inc/testAutomation's machine-readable test inventory
(`atoms-probe-targets.json` if/when published). For now the test
cases are encoded directly here based on the OpenAPI surface.

Usage:
    SMALLEST_API_KEY=... python3 scripts/probes/atoms.py [--out FILE]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

import requests

BASE_URL = "https://api.smallest.ai/atoms/v1"

# Each case is (label, path, query). All GET, all read-only.
# Labels are the stable key in the baseline JSON — do not rename
# without re-baselining.
TEST_CASES: list[tuple[str, str, dict]] = [
    ("get-user",                "/user",                  {}),
    ("get-organization",        "/organization",          {}),
    ("get-agent-templates",     "/agent/template",        {}),
    ("get-agents",              "/agent",                 {}),
    ("get-conversations",       "/conversation",          {"limit": 5}),
    ("get-events",              "/events",                {"limit": 5}),
    ("get-campaigns",           "/campaign",              {}),
    ("get-knowledgebases",      "/knowledgebase",         {}),
    ("get-phone-numbers",       "/product/phone-numbers", {}),
    ("get-webhooks",            "/webhook",               {}),
    ("get-audiences",           "/audience",              {}),
]


def count_class(n: int) -> str:
    """Bucket item counts so transient list-size drift doesn't false-flag.

    The probe doesn't care if you have 5 vs 7 agents week to week. It
    cares about empty-vs-nonempty (auth issue? account wiped?) and
    obviously huge (list endpoint suddenly paginating differently).
    """
    if n == 0:
        return "empty"
    if n < 10:
        return "few"
    if n < 100:
        return "many"
    return "lots"


def probe_get(path: str, query: dict, api_key: str) -> dict:
    started = time.monotonic()
    try:
        r = requests.get(
            BASE_URL + path,
            headers={"Authorization": f"Bearer {api_key}"},
            params=query,
            timeout=30,
        )
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}
    elapsed_ms = int((time.monotonic() - started) * 1000)
    rec: dict = {
        "ok": r.ok,
        "status_code": r.status_code,
        "elapsed_ms": elapsed_ms,
        "content_type": r.headers.get("Content-Type", ""),
    }
    # Try to parse JSON. Atoms returns {status, data, [message]} envelopes.
    try:
        body = r.json()
    except Exception:
        rec["body_first200"] = r.text[:200]
        return rec

    if isinstance(body, dict):
        rec["envelope_keys"] = sorted(body.keys())
        rec["envelope_status"] = body.get("status")
        data = body.get("data")
        if isinstance(data, list):
            rec["data_kind"] = "list"
            rec["count_class"] = count_class(len(data))
            # First item's keys (if present) — surface schema additions/removals
            if data and isinstance(data[0], dict):
                rec["item_keys_first"] = sorted(data[0].keys())
        elif isinstance(data, dict):
            rec["data_kind"] = "object"
            rec["data_keys"] = sorted(data.keys())
        elif data is None:
            rec["data_kind"] = "null"
        else:
            rec["data_kind"] = type(data).__name__
    elif isinstance(body, list):
        # Some endpoints might return a bare list; record that.
        rec["envelope_keys"] = []
        rec["data_kind"] = "list"
        rec["count_class"] = count_class(len(body))
        if body and isinstance(body[0], dict):
            rec["item_keys_first"] = sorted(body[0].keys())
    else:
        rec["body_first200"] = r.text[:200]
    return rec


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out")
    args = parser.parse_args()

    api_key = os.environ["SMALLEST_API_KEY"]
    results = []
    for label, path, query in TEST_CASES:
        print(f"  probing: {label} ({path})", file=sys.stderr)
        rec = probe_get(path, query, api_key)
        results.append({"label": label, "path": path, "query": query, **rec})

    output = {
        "schema_version": 1,
        "service": "atoms",
        "endpoint_base": BASE_URL,
        "results": results,
    }
    blob = json.dumps(output, indent=2, sort_keys=True)
    if args.out:
        with open(args.out, "w") as f:
            f.write(blob + "\n")
        print(f"Wrote {args.out}", file=sys.stderr)
    else:
        print(blob)


if __name__ == "__main__":
    main()
