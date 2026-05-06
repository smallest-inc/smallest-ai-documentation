"""Spec drift check — runs on PR.

Catches the silent-edit class of bug: the v4 docs render through
fern/apis/waves-v4/overrides/* which decorates fields in the base specs.
If a content field (description, default, enum, example) differs between
base and override, editing base alone is invisible on docs.

What this script does
---------------------
For each (base, v4-override) pair, it indexes both specs by JSON-path,
then flags any tracked content field where the values differ. For
AsyncAPI WS specs it also checks the cross-structural-path mapping
unique to Pulse STT WS: the override decorates
`channels.<chan>.parameters.<param>` while the base spec declares the
same param under `channels.<chan>.messages.<msg>.payload.properties.<param>`.

Exit code 1 + clear diff on any mismatch.

Usage:
    python3 scripts/spec-live-tests/spec_drift_check.py
"""
from __future__ import annotations
import sys
import yaml
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WAVES = ROOT / "fern/apis/waves"
V4 = ROOT / "fern/apis/waves-v4/overrides"

PAIRS = [
    ("add-voice-openapi-overrides.yaml", WAVES / "openapi/add-voice-openapi.yaml"),
    ("delete-cloned-voice-openapi-overrides.yaml", WAVES / "openapi/delete-cloned-voice-openapi.yaml"),
    ("get-cloned-voices-openapi-overrides.yaml", WAVES / "openapi/get-cloned-voices-openapi.yaml"),
    ("get-voices-openapi-overrides.yaml", WAVES / "openapi/get-voices-openapi.yaml"),
    ("lightning-v2-ws-overrides.yml", WAVES / "asyncapi/lightning-v2-ws.yaml"),
    ("lightning-v3.1-openapi-overrides.yaml", WAVES / "openapi/lightning-v3.1-openapi.yaml"),
    ("lightning-v3.1-ws-overrides.yml", WAVES / "asyncapi/lightning-v3.1-ws.yaml"),
    ("pulse-stt-openapi-overrides.yaml", WAVES / "openapi/pulse-stt-openapi.yaml"),
    ("pulse-stt-ws-overrides.yml", WAVES / "asyncapi/pulse-stt-ws.yaml"),
    ("voice-cloning-openapi-overrides.yaml", WAVES / "openapi/voice-cloning-openapi.yaml"),
    ("waves-api-overrides.yaml", WAVES / "openapi/waves-api.yaml"),
]

TRACK = ("description", "default", "example", "examples", "enum")


def walk(node, path=""):
    if isinstance(node, dict):
        yield path, node
        for k, v in node.items():
            yield from walk(v, f"{path}.{k}" if path else k)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from walk(v, f"{path}[{i}]")


def index(spec):
    return {p: n for p, n in walk(spec) if isinstance(n, dict)}


def asyncapi_param_xref(base, override):
    """For AsyncAPI WS specs, check override.channels.X.parameters.Y vs
    base.channels.X.messages.<msg>.payload.properties.Y.

    Yields (param_path, base_desc, override_desc) for each drift.
    """
    out = []
    for chan_name, chan in (override.get("channels") or {}).items():
        ovr_params = (chan or {}).get("parameters") or {}
        base_chan = (base.get("channels") or {}).get(chan_name) or {}
        msgs = base_chan.get("messages") or {}
        # find the request message (any message with payload.properties)
        properties = {}
        for msg in msgs.values():
            payload = (msg or {}).get("payload") or {}
            if isinstance(payload, dict) and isinstance(payload.get("properties"), dict):
                properties = payload["properties"]
                break
        for pname, pblock in ovr_params.items():
            if not isinstance(pblock, dict):
                continue
            ovr_desc = pblock.get("description")
            base_field = properties.get(pname) or {}
            base_desc = base_field.get("description") if isinstance(base_field, dict) else None
            if ovr_desc is not None and base_desc is not None and ovr_desc.strip() != base_desc.strip():
                out.append((f"channels.{chan_name}.parameters.{pname}", base_desc, ovr_desc))
    return out


def main() -> int:
    grand_drift = 0
    grand_orphan = 0
    print("=" * 78)
    print("Spec drift check — fern/apis/waves-v4/overrides vs fern/apis/waves base")
    print("=" * 78)

    for ovr_name, base_path in PAIRS:
        ovr_path = V4 / ovr_name
        if not ovr_path.exists() or not base_path.exists():
            continue
        with open(ovr_path) as f:
            ovr = yaml.safe_load(f) or {}
        with open(base_path) as f:
            base = yaml.safe_load(f) or {}

        ovr_idx = index(ovr)
        base_idx = index(base)

        drift = []
        for path, ovr_node in ovr_idx.items():
            base_node = base_idx.get(path)
            if base_node is None:
                continue
            for f in TRACK:
                if f in ovr_node:
                    if f not in base_node or base_node[f] != ovr_node[f]:
                        drift.append((path, f, base_node.get(f), ovr_node[f]))

        # AsyncAPI cross-structural-path check for parameters block
        xref = []
        if base_path.suffix in (".yaml", ".yml") and "asyncapi" in base.get("openapi", "") + str(base.get("asyncapi", "")):
            xref = asyncapi_param_xref(base, ovr)

        if drift or xref:
            print(f"\n{ovr_name}")
            for p, f, b, o in drift:
                bs = (str(b) if b is not None else "(missing)")[:90]
                os_ = str(o)[:90]
                print(f"  DRIFT .{p}.{f}")
                print(f"    base    : {bs}")
                print(f"    override: {os_}")
                grand_drift += 1
            for p, b, o in xref:
                print(f"  WS-XREF {p}")
                print(f"    base.messages.payload.properties: {(b or '(missing)')[:90]}")
                print(f"    override.parameters             : {o[:90]}")
                grand_drift += 1

    print()
    print("=" * 78)
    if grand_drift == 0:
        print(f"PASS — no drift between waves base specs and waves-v4 docs overrides")
        return 0
    print(f"FAIL — {grand_drift} drift fields found")
    print()
    print("Each drift means editing the base spec alone will not show up on docs.")
    print("Update both files in lockstep, or remove the override decoration.")
    print("=" * 78)
    return 1


if __name__ == "__main__":
    sys.exit(main())
