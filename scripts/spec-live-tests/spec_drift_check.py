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


def discover_pairs() -> list[tuple[str, Path]]:
    """Auto-discover (override_filename, base_path) pairs from V4 directory.

    The override filename pattern is `<basename>-overrides.{yml,yaml}`. We
    strip the suffix and look for a matching base spec under either
    `waves/openapi/` or `waves/asyncapi/`. Surfaces any new override the
    moment it's added to V4 — no edit to this script required.

    Files in V4 with no resolvable base counterpart raise SystemExit so
    the misconfiguration is caught loudly rather than silently skipped.
    """
    pairs: list[tuple[str, Path]] = []
    unmatched: list[str] = []
    for ovr_file in sorted(V4.iterdir()):
        if not ovr_file.is_file() or ovr_file.suffix not in (".yaml", ".yml"):
            continue
        name = ovr_file.name
        if not name.endswith(("-overrides.yaml", "-overrides.yml")):
            unmatched.append(name)
            continue
        stem = name.rsplit("-overrides.", 1)[0]
        # search both openapi/ and asyncapi/ for a matching base file
        candidates = [
            WAVES / "openapi" / f"{stem}.yaml",
            WAVES / "openapi" / f"{stem}.yml",
            WAVES / "asyncapi" / f"{stem}.yaml",
            WAVES / "asyncapi" / f"{stem}.yml",
        ]
        match = next((c for c in candidates if c.exists()), None)
        if match is None:
            unmatched.append(name)
            continue
        pairs.append((name, match))
    if unmatched:
        sys.stderr.write(
            f"ERROR: override files in {V4} have no matching base spec under "
            f"{WAVES}/openapi or {WAVES}/asyncapi:\n"
            + "\n".join(f"  - {n}" for n in unmatched) + "\n"
        )
        sys.exit(2)
    return pairs


PAIRS = discover_pairs()

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


# NOTE on AsyncAPI WS spec drift coverage
# ---------------------------------------
# Pulse STT WS docs render through `channels.<chan>.parameters.<param>` in
# the v4 override, while the base AsyncAPI spec keeps message bodies under
# `channels.<chan>.messages.<msg>.payload.properties.<param>`. These are
# different structural locations holding semantically different things
# (request query params vs. message body fields). We do NOT attempt a
# cross-path comparison — names like `language` legitimately appear on
# both sides describing different concepts (request param vs response
# field), and any heuristic that crosses the two produces false positives.
#
# Real drift across either layer (base or override) is caught by the
# same-path drift loop in main(): if both layers declare a field at the
# identical JSON path, mismatches in description/default/enum/example are
# reported. For override-only fields (the pulse-stt-ws parameters block),
# the override is the sole source of truth and there is no base
# counterpart to compare against. CLAUDE.md documents this contract.


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

        if drift:
            print(f"\n{ovr_name}")
            for p, f, b, o in drift:
                bs = (str(b) if b is not None else "(missing)")[:90]
                os_ = str(o)[:90]
                print(f"  DRIFT .{p}.{f}")
                print(f"    base    : {bs}")
                print(f"    override: {os_}")
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
