"""Pages-vs-versions mirror drift check for v4 docs (PR-scoped).

Every MDX page under fern/products/waves/pages/v4.0.0/ has a counterpart
under fern/products/waves/versions/v4.0.0/. The two are supposed to stay
byte-identical (versions/ is the v4 release mirror — same content viewed
through the version selector).

When a PR edits a page in pages/ but forgets to mirror the change into
versions/ (or vice versa), the docs site renders the new content under
/waves and the stale copy under /waves/v-4-0-0. Customers landing via the
version selector see outdated content with no warning.

This check is PR-scoped: it only flags drift in files that THIS PR
touched. Pre-existing baseline drift across other files is not the
concern of any individual PR — the goal here is to stop new drift from
sneaking in. (A separate batch cleanup of pre-existing drift is queued
as a follow-up.)

Defaults to comparing against `origin/main`; override with `--base REF`.

Files allowed to differ: changelog-entries (versions/ deliberately
freezes those at release time), and binary assets (audio, video).

Exit non-zero only on drifts the PR introduced or failed to mirror.
"""
from __future__ import annotations
import argparse
import filecmp
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAGES = ROOT / "fern/products/waves/pages/v4.0.0"
VERSIONS = ROOT / "fern/products/waves/versions/v4.0.0"

# Subdirs allowed to differ between pages/ and versions/.
# changelog-entries: versions/ pins to release-time entries by design.
# audio, video, images: binary asset folders that may live in only one tree.
# Match on directory boundary (trailing /) or exact filename to avoid
# `changelog-entries` falsely matching `changelog-entries-archive/foo.mdx`.
ALLOWED_DIFF_PREFIXES = (
    "changelog-entries/",
    "changelog/announcements",  # mainline announcements, not mirror-versioned
    "audio/",
    "video/",
    "images/",
)


def is_allowed_diff(rel_path: str) -> bool:
    """True if rel_path falls under a directory listed in ALLOWED_DIFF_PREFIXES.
    Uses trailing-slash-aware matching so similar-named siblings don't collide."""
    return any(
        rel_path == p.rstrip("/") or rel_path.startswith(p)
        for p in ALLOWED_DIFF_PREFIXES
    )


def _verify_ref(ref: str) -> None:
    """Ensure `ref` resolves locally. Hard-fail (not silent) if it doesn't —
    a missing base ref means the diff scope is undefined and we'd otherwise
    silently report 'no files changed' on every run, defeating the check."""
    r = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", ref],
        cwd=ROOT, capture_output=True, text=True,
    )
    if r.returncode != 0:
        sys.stderr.write(
            f"ERROR: base ref {ref!r} not found locally. "
            f"In CI, ensure 'fetch-depth: 0' on actions/checkout and that the "
            f"target branch is fetched. Locally, run: git fetch origin\n"
        )
        sys.exit(2)


def changed_files(base_ref: str) -> set[str]:
    """Files changed in HEAD vs base_ref, relative to repo root.

    Errors are fatal — a silent empty set would let CI pass without checking
    anything (defect #1 in the review pass that motivated this hardening)."""
    _verify_ref(base_ref)
    r = subprocess.run(
        ["git", "diff", "--name-only", f"{base_ref}...HEAD"],
        cwd=ROOT, capture_output=True, text=True,
    )
    if r.returncode != 0:
        sys.stderr.write(f"ERROR: git diff against {base_ref} failed:\n{r.stderr}\n")
        sys.exit(2)
    return {l.strip() for l in r.stdout.splitlines() if l.strip()}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="origin/main",
                        help="git ref to diff against (default: origin/main)")
    parser.add_argument("--all", action="store_true",
                        help="check all files, not just PR-changed (for batch audits)")
    args = parser.parse_args()

    if not PAGES.exists() or not VERSIONS.exists():
        print(f"missing tree: {PAGES} or {VERSIONS}")
        return 1

    if args.all:
        # Audit mode: check every paired file.
        scope = None
    else:
        scope = changed_files(args.base)
        if not scope:
            print("PASS — no files changed vs base, nothing to check")
            return 0

    drifted: list[str] = []

    pages_files = {p.relative_to(PAGES).as_posix() for p in PAGES.rglob("*") if p.is_file()}
    versions_files = {p.relative_to(VERSIONS).as_posix() for p in VERSIONS.rglob("*") if p.is_file()}

    def in_scope(rel: str, prefix: str) -> bool:
        if scope is None:
            return True
        return f"{prefix}/{rel}" in scope

    # Only flag content drift between PAIRED files. Files that legitimately
    # exist in only one tree (e.g. model cards in pages/ only) are a
    # structural choice, not a mirror bug, and we don't try to second-
    # guess them here.
    for rel in sorted(pages_files & versions_files):
        if is_allowed_diff(rel):
            continue
        if not (in_scope(rel, "fern/products/waves/pages/v4.0.0") or
                in_scope(rel, "fern/products/waves/versions/v4.0.0")):
            continue
        if not filecmp.cmp(PAGES / rel, VERSIONS / rel, shallow=False):
            drifted.append(rel)

    print("=" * 78)
    mode = "AUDIT" if scope is None else f"PR-SCOPED (vs {args.base})"
    print(f"v4 docs mirror check [{mode}]")
    print("=" * 78)

    if drifted:
        print(f"\n[drift] {len(drifted)} file(s) differ between pages/ and versions/:")
        for rel in drifted:
            print(f"  {rel}")

    print()
    if not drifted:
        print("PASS — pages/ and versions/ are in sync for PR-changed files")
        return 0
    print(f"FAIL — {len(drifted)} paired file(s) drifted on PR-changed files. Sync the trees:")
    print("  cp fern/products/waves/pages/v4.0.0/<file> fern/products/waves/versions/v4.0.0/<file>")
    print("  (or vice versa, depending on which is the source of truth)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
