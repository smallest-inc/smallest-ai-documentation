#!/usr/bin/env python3
"""Copy or verify the engineering-owned Waves API contracts."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DESTINATION = REPO_ROOT / "fern/apis/waves/generated"
FILES = ("openapi.json", "asyncapi.json")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source",
        type=Path,
        default=REPO_ROOT.parent / "waves-platform/apps/main-backend/api-contract",
        help="Directory containing openapi.json and asyncapi.json",
    )
    parser.add_argument("--check", action="store_true", help="Fail instead of copying on drift")
    return parser.parse_args()


def validate(documents: dict[str, dict]) -> None:
    openapi = documents["openapi.json"]
    asyncapi = documents["asyncapi.json"]
    if openapi.get("openapi") != "3.1.0":
        raise ValueError("openapi.json must use OpenAPI 3.1.0")
    if asyncapi.get("asyncapi") != "3.0.0":
        raise ValueError("asyncapi.json must use AsyncAPI 3.0.0")

    hashes = {
        document.get("x-smallest-source", {}).get("hash") for document in documents.values()
    }
    if len(hashes) != 1 or None in hashes:
        raise ValueError("generated contracts must carry the same x-smallest-source hash")

    required_paths = {
        "/waves/v1/tts",
        "/waves/v1/tts/live",
        "/waves/v1/pii/text",
        "/waves/v1/pii/audio",
    }
    if set(openapi.get("paths", {})) != required_paths:
        raise ValueError("openapi.json managed route surface changed; update docs overlays")
    if asyncapi.get("channels", {}).get("ttsStream", {}).get("address") != "/waves/v1/tts/live":
        raise ValueError("asyncapi.json does not contain the managed TTS WebSocket channel")


def main() -> int:
    args = parse_args()
    source = args.source.resolve()
    documents = {
        filename: json.loads((source / filename).read_text()) for filename in FILES
    }
    validate(documents)

    drifted = [
        filename
        for filename in FILES
        if not (DESTINATION / filename).exists()
        or (source / filename).read_bytes() != (DESTINATION / filename).read_bytes()
    ]
    if args.check:
        if drifted:
            print(f"Waves generated contract drift: {', '.join(drifted)}", file=sys.stderr)
            return 1
        print("Waves generated contracts are up to date.")
        return 0

    DESTINATION.mkdir(parents=True, exist_ok=True)
    for filename in drifted:
        shutil.copyfile(source / filename, DESTINATION / filename)
    source_hash = next(iter({d["x-smallest-source"]["hash"] for d in documents.values()}))
    print(f"Synced {len(drifted)} Waves contract file(s), source {source_hash}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
