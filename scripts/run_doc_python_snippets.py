"""Extract ```python code blocks from MDX files and run each against the live API.

Usage:
    SMALLEST_API_KEY=... python3 scripts/run_doc_python_snippets.py FILE.mdx [FILE2.mdx ...]

Skips snippets that need hardware not available on CI runners (`import pyaudio`).
Returns nonzero exit if any executed snippet fails.

Why this exists
---------------
Embedded Python samples in our v4 docs are the surface developers actually
copy-paste. If they drift from the live API, every reader hits a broken
example before they ever look at us. This harness extracts the exact
fenced ```python block as-is from the MDX (no rewrites, no env injection
beyond what the script does itself) and runs it. If the sample's
documented setup ("export SMALLEST_API_KEY", "pip install foo") is
satisfied in the CI step, the sample runs verbatim and either works or
breaks the build.

Design notes
------------
- Only `python` blocks. JS/Node/cURL blocks are out of scope here; testing
  those needs different runtimes and they have far fewer drift modes.
- Skips by static rule: `import pyaudio` (CI runners have no mic). New
  hardware-only samples should be skipped by adding a similar import
  signature here.
- One subprocess per block, 90 s timeout each. Output captured and
  printed only on failure so green runs stay quiet.
- Block detection is intentionally tolerant of Fern's `language label`
  syntax (```python python, ```python "Python (PyAudio)", etc.).
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

# Match ```python (optional space + label until end-of-line) ... ```
PY_BLOCK_RE = re.compile(
    r"```python(?:[^\n]*)?\n(.*?)\n```",
    re.DOTALL,
)

# If a block contains any of these strings, skip with a note.
SKIP_SIGNATURES: dict[str, str] = {
    "import pyaudio": "needs microphone hardware (PyAudio)",
    # Add more as we encounter them, e.g. "soundfile.SoundFile" if a
    # block depends on a local-only fixture.
}


def block_skip_reason(code: str) -> str | None:
    for sig, reason in SKIP_SIGNATURES.items():
        if sig in code:
            return reason
    return None


def run_block(code: str, label: str, timeout: int = 90) -> tuple[bool, str]:
    """Run a single Python snippet. Returns (ok, log)."""
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(code)
        tmp_path = f.name
    try:
        result = subprocess.run(
            ["python3", tmp_path],
            timeout=timeout,
            capture_output=True,
            text=True,
            env=dict(os.environ),
        )
        ok = result.returncode == 0
        if ok:
            return True, ""
        # Trim long output for log readability
        stdout_tail = result.stdout[-1500:] if result.stdout else "(empty)"
        stderr_tail = result.stderr[-1500:] if result.stderr else "(empty)"
        log = (
            f"  exit code: {result.returncode}\n"
            f"  --- stdout (tail) ---\n{stdout_tail}\n"
            f"  --- stderr (tail) ---\n{stderr_tail}"
        )
        return False, log
    except subprocess.TimeoutExpired:
        return False, f"  timed out after {timeout}s"
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run embedded Python snippets in MDX docs against the live API."
    )
    parser.add_argument("paths", nargs="+", help="MDX files to scan")
    parser.add_argument("--timeout", type=int, default=90, help="per-snippet timeout (s)")
    args = parser.parse_args(argv)

    if not os.environ.get("SMALLEST_API_KEY"):
        print("ERROR: SMALLEST_API_KEY not set", file=sys.stderr)
        return 2

    total = passed = skipped = 0
    failures: list[tuple[str, str]] = []

    for path_str in args.paths:
        path = Path(path_str)
        if not path.exists():
            print(f"WARNING: {path} does not exist, skipping", file=sys.stderr)
            continue
        text = path.read_text()
        blocks = list(PY_BLOCK_RE.finditer(text))
        if not blocks:
            print(f"-- {path}: no python blocks")
            continue
        print(f"-- {path}: {len(blocks)} python block(s)")
        for idx, m in enumerate(blocks, 1):
            code = m.group(1)
            label = f"{path}::block-{idx}"
            reason = block_skip_reason(code)
            if reason:
                print(f"   SKIP {label}: {reason}")
                skipped += 1
                continue
            total += 1
            ok, log = run_block(code, label, timeout=args.timeout)
            if ok:
                print(f"   PASS {label}")
                passed += 1
            else:
                print(f"   FAIL {label}")
                print(log)
                failures.append((label, log))

    print()
    print(f"Summary: {passed}/{total} passed, {skipped} skipped, {len(failures)} failed")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
