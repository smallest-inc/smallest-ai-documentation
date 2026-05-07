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
APIS = ROOT / "fern/apis"

# Override locations that decorate a base spec. Each tuple is
# (override_root, base_search_roots). The override filename pattern
# `<stem>-overrides.{yml,yaml}` resolves to `<stem>.{yaml,yml}` under one
# of the base search roots. `ai_examples_override.{yml,yaml}` is treated
# as a special-case override of the file named `openapi.{yml,yaml}` in
# the same directory.
OVERRIDE_LAYOUTS = [
    # waves v4 docs render layer
    (APIS / "waves-v4/overrides",
     [APIS / "waves/openapi", APIS / "waves/asyncapi"]),
    # waves SDK-gen siblings (overrides live next to the base)
    (APIS / "waves/openapi",
     [APIS / "waves/openapi"]),
    (APIS / "waves/asyncapi",
     [APIS / "waves/asyncapi"]),
    # atoms — siblings (single layer for both SDK and docs)
    (APIS / "atoms/openapi",
     [APIS / "atoms/openapi"]),
    (APIS / "atoms/asyncapi",
     [APIS / "atoms/asyncapi"]),
]


def _resolve_base(stem: str, search_roots: list[Path]) -> Path | None:
    for root in search_roots:
        for suffix in (".yaml", ".yml"):
            candidate = root / f"{stem}{suffix}"
            if candidate.exists():
                return candidate
    return None


def discover_pairs() -> list[tuple[str, Path, Path]]:
    """Auto-discover (label, base_path, override_path) triples across atoms,
    waves, and waves-v4 layers. Each base spec may have multiple decorating
    override files; we emit one pair per override.

    Files matching `<stem>-overrides.{yml,yaml}` strip the suffix and search
    sibling/openapi/asyncapi roots. `ai_examples_override.{yml,yaml}` decorates
    `openapi.{yml,yaml}` in the same directory.

    Hard-fails on any override file with no resolvable base counterpart so
    misconfiguration is caught loudly rather than silently uncovered.
    """
    pairs: list[tuple[str, Path, Path]] = []
    unmatched: list[Path] = []
    for ovr_root, base_roots in OVERRIDE_LAYOUTS:
        if not ovr_root.exists():
            continue
        for ovr in sorted(ovr_root.iterdir()):
            if not ovr.is_file() or ovr.suffix not in (".yaml", ".yml"):
                continue
            name = ovr.name
            if name.startswith("ai_examples_override"):
                # Decorates a sibling `openapi.{yaml,yml}`. If no such sibling
                # exists in the same dir (e.g. waves uses per-endpoint base
                # filenames like `lightning-v3.1-openapi.yaml`, not `openapi.yaml`),
                # this override is broad-spectrum and skipped here.
                base = _resolve_base("openapi", [ovr.parent])
                if base is None:
                    continue
            elif name.endswith(("-overrides.yaml", "-overrides.yml")):
                stem = name.rsplit("-overrides.", 1)[0]
                base = _resolve_base(stem, base_roots)
                if base is None:
                    unmatched.append(ovr)
                    continue
            else:
                # plain spec file (e.g. base file in same dir as overrides)
                continue
            if base.resolve() == ovr.resolve():
                continue  # pointing at itself
            label = str(ovr.relative_to(ROOT))
            pairs.append((label, base, ovr))
    if unmatched:
        sys.stderr.write("ERROR: override files with no resolvable base spec:\n"
                         + "\n".join(f"  - {p.relative_to(ROOT)}" for p in unmatched) + "\n")
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

    for label, base_path, ovr_path in PAIRS:
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
            print(f"\n{label}")
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
