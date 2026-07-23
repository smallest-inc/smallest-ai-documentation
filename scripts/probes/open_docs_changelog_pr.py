"""Open a docs PR with a changelog entry generated from parsed upstream-PR template fields.

Triggered from .github/workflows/pr-drift-detector.yml AFTER upstream_pr_classifier.py
emits classification.json with verdict=DOCS_NEEDED and a structured `changelog` block.

Routing (where the entry lands):

  Upstream repo                Surface picker     Target directory
  ────────────────────────────────────────────────────────────────────────────
  smallest-inc/atoms-platform  (n/a)              fern/products/atoms/pages/intro/reference/changelog-entries/
  smallest-inc/waves-platform  general            fern/products/waves/pages/changelog-entries/general/
  smallest-inc/waves-platform  lightning-v3.1     fern/products/waves/pages/changelog-entries/lightning-v3.1/
  smallest-inc/waves-platform  pulse-stt          fern/products/waves/pages/changelog-entries/pulse-stt/
  smallest-inc/waves-platform  electron           fern/products/waves/pages/changelog-entries/electron/
  smallest-inc/waves-platform  hydra              fern/products/waves/pages/changelog-entries/hydra/
  (waves PR with unrecognised / empty surface)    → falls back to general/ with a warning

For waves entries we also mirror to fern/products/waves/pages/changelog-entries/<surface>/
so the version-pin and the live-tracking copies stay in sync (the v4_mirror_check.py
CI gate requires this).

Filename: YYYY-MM-DD-<slug>.mdx  where slug is derived from the parsed Title.

The script is idempotent on the *target file path*: if an entry already exists at
exactly the same path it overwrites in place. This lets a re-run after an edit
update the same PR rather than spawning a new one.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import datetime as dt
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

ATOMS_DIR = REPO_ROOT / "fern/products/atoms/pages/intro/reference/changelog-entries"
WAVES_PAGES_BASE = REPO_ROOT / "fern/products/waves/pages/changelog-entries"
WAVES_VERSIONS_BASE = REPO_ROOT / "fern/products/waves/pages/changelog-entries"
# Surfaces accepted from the waves-platform `Changelog surface` picker.
# Mirror this set when the source-repo PR template adds new options.
WAVES_SURFACES = {"general", "lightning-v3.1", "pulse-stt", "electron", "hydra"}
WAVES_FALLBACK_SURFACE = "general"  # used when the picker is empty / unrecognised


def slugify(text: str, max_len: int = 60) -> str:
    """Match the naming convention of existing entries (YYYY-MM-DD-<slug>.mdx)."""
    s = text.lower().strip()
    s = re.sub(r"[—–]", "-", s)            # em/en dashes → ascii hyphen
    s = re.sub(r"[^a-z0-9\s-]", "", s)     # drop everything that isn't slug-safe
    s = re.sub(r"\s+", "-", s)             # spaces → hyphens
    s = re.sub(r"-+", "-", s).strip("-")
    return s[:max_len].rstrip("-") or "entry"


def render_mdx(fields: dict, repo: str, pr_url: str) -> str:
    title = fields.get("title", "").strip()
    body = fields.get("body", "").strip()
    code = fields.get("code_sample", "").strip()
    ships = fields.get("ships", "").strip()
    migration = fields.get("migration", "").strip()
    byline = fields.get("byline", "").strip()
    category = fields.get("category", "").strip()

    description = body.split("\n")[0][:240] if body else title

    parts = [
        "---",
        f"title: {title}",
        f"date: {dt.date.today().isoformat()}",
        f"description: {description}",
        "---",
        "",
        body,
        "",
    ]
    if code:
        # The template's code fence may have included a language hint; if we
        # didn't see one, default to a generic fence.
        fence = "```\n" + code + "\n```"
        parts += [fence, ""]
    notes = []
    if ships:
        notes.append(f"**Ships:** {ships}")
    if migration:
        notes.append(f"**Migration:** {migration}")
    if category:
        notes.append(f"**Category:** {category}")
    if notes:
        parts += ["", *notes, ""]
    if byline:
        parts += [f"*— {byline}*", ""]
    parts += [
        f"<sub>Auto-generated from [{repo}#{pr_url.rsplit('/', 1)[-1]}]({pr_url}) via the PR-merged → docs changelog automation.</sub>",
        "",
    ]
    return "\n".join(parts)


def target_paths(repo: str, surface: str | None, slug: str) -> tuple[str | None, list[Path]]:
    """Compute the file path(s) the entry should land at.

    Returns:
        (effective_surface, paths)
        - effective_surface: the surface key actually used after any fallback.
          None for atoms (no surface concept). Callers should display this
          value (not the input `surface`) so the PR body matches where the
          file actually lands.
        - paths: one entry for atoms, two for waves (pages/ + versions/ mirror).
    """
    today = dt.date.today().isoformat()
    filename = f"{today}-{slug}.mdx"

    if repo.endswith("/atoms-platform"):
        return None, [ATOMS_DIR / filename]

    # waves-platform AND phonon-uv (the Hydra source repo) both land
    # entries in the waves doc tree. phonon-uv always routes to
    # surface=hydra; for waves-platform we trust the author's surface
    # picker, with a soft fallback when it's empty / unrecognised so the
    # workflow keeps moving instead of failing the job.
    if repo.endswith("/waves-platform") or repo.endswith("/phonon-uv"):
        if repo.endswith("/phonon-uv"):
            # phonon-uv only ships Hydra changes; ignore any surface from
            # the PR template (the template default is `hydra` anyway).
            effective = "hydra"
        elif surface in WAVES_SURFACES:
            effective = surface
        else:
            print(
                f"WARN: waves changelog surface {surface!r} not in known set "
                f"{sorted(WAVES_SURFACES)} — falling back to {WAVES_FALLBACK_SURFACE!r}.",
                file=sys.stderr,
            )
            effective = WAVES_FALLBACK_SURFACE
        return effective, [
            WAVES_PAGES_BASE / effective / filename,
            WAVES_VERSIONS_BASE / effective / filename,
        ]

    print(f"ERROR: unsupported repo for changelog auto-PR: {repo}", file=sys.stderr)
    sys.exit(2)


def run(*cmd, check=True, **kw):
    """Thin subprocess wrapper that surfaces stderr on failure."""
    result = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if check and result.returncode != 0:
        print(f"$ {' '.join(cmd)}\n{result.stderr}", file=sys.stderr)
        result.check_returncode()
    return result


def open_pr(branch: str, title: str, body: str, base: str = "main") -> str:
    """Open a PR via gh; return the PR URL."""
    r = run("gh", "pr", "create",
            "--base", base, "--head", branch,
            "--title", title, "--body", body)
    return r.stdout.strip()


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--classification-json", required=True)
    p.add_argument("--repo", required=True)
    p.add_argument("--pr-url", required=True)
    p.add_argument("--pr-title", required=True)
    p.add_argument("--pr-number", required=True)
    p.add_argument("--base", default="main", help="docs-repo base branch")
    p.add_argument("--dry-run", action="store_true", help="generate file(s) but don't push/open PR")
    args = p.parse_args()

    data = json.loads(Path(args.classification_json).read_text())
    if data.get("verdict") != "DOCS_NEEDED":
        print(f"Skipping: verdict is {data.get('verdict')!r}, not DOCS_NEEDED.")
        return 0
    changelog = data.get("changelog")
    if not changelog or changelog.get("kind") != "structured":
        print("Skipping: no structured changelog block in classification JSON.")
        return 0

    fields = changelog["fields"]
    title = fields.get("title", "").strip()
    if not title:
        print("Skipping: parsed changelog has no Title field.")
        return 0

    surface = fields.get("changelog_surface")
    slug = slugify(title)
    effective_surface, paths = target_paths(args.repo, surface, slug)

    rendered = render_mdx(fields, args.repo, args.pr_url)
    for path in paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered)
        print(f"wrote {path.relative_to(REPO_ROOT)}")

    if args.dry_run:
        print("Dry-run mode: stopping before git push / PR creation.")
        return 0

    # Create a branch off base, commit, push, open PR.
    branch = f"changelog/auto-{args.repo.split('/')[-1]}-pr-{args.pr_number}"
    run("git", "config", "user.email", "docs-bot@smallest.ai")
    run("git", "config", "user.name", "smallest-ai docs bot")
    run("git", "checkout", "-B", branch, f"origin/{args.base}")
    for path in paths:
        run("git", "add", str(path))
    msg = f"docs(changelog): {title}\n\nAuto-generated from {args.repo}#{args.pr_number}\n{args.pr_url}"
    run("git", "commit", "-m", msg)
    run("git", "push", "-u", "origin", branch, "--force-with-lease")

    pr_body = (
        f"Auto-opened by the upstream changelog automation in response to "
        f"[{args.repo}#{args.pr_number}]({args.pr_url}) — *{args.pr_title}*.\n\n"
        f"## Generated entry\n\n"
        f"- Title: **{title}**\n"
        + (f"- Category: {fields.get('category')}\n" if fields.get("category") else "")
        + (
            # Show the surface the file actually landed in. When the input
            # surface was unrecognised and we fell back, also annotate that
            # so the reviewer knows to (optionally) move the file post-merge.
            f"- Surface: `{effective_surface}`"
            + (f" *(fell back from `{surface}`)*" if surface and surface != effective_surface else "")
            + "\n"
            if effective_surface else ""
        )
        + (f"- Ships: {fields.get('ships')}\n" if fields.get("ships") else "")
        + (f"- Migration: {fields.get('migration')}\n" if fields.get("migration") else "")
        + (f"- Byline: {fields.get('byline')}\n" if fields.get("byline") else "")
        + "\n## Files\n"
        + "\n".join(f"- `{p.relative_to(REPO_ROOT)}`" for p in paths)
        + "\n\nReview the entry, polish the prose if needed, and merge. "
          "The upstream PR is already shipped — this PR exists so the public docs catch up."
    )
    pr_url = open_pr(branch, f"docs(changelog): {title}", pr_body, base=args.base)
    print(f"opened {pr_url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
