"""Classify an upstream PR (atoms-platform / waves-platform / lightning-asr-offline / godspeed)
for likely docs / API-spec impact.

Reads PR metadata + diff and asks Claude:
  - Does this PR change a public API surface, default, response shape,
    error code, supported language list, or feature flag that the
    customer-facing docs reference?
  - If yes: which doc files are likely affected?
  - If no: stay silent.

Why this exists
---------------
Docs go stale silently when an upstream backend repo merges a new param,
deprecates an endpoint, or shifts a default. The weekly api-flag-probe
catches surface-level drift only at the live API. This classifier is the
event-driven pre-warning: the moment a PR merges upstream, ask Claude
"is this a docs concern?" and ping the docs owner only when it is.

Designed to be called from .github/workflows/pr-drift-detector.yml after
a `repository_dispatch: upstream_pr_merged` event with PR metadata in
github.event.client_payload.

Usage:
    ANTHROPIC_API_KEY=... \\
    UPSTREAM_REPO_HINTS_JSON='{"OWNER/REPO": ["fern/apis/.../pulse-stt-ws.yaml"]}' \\
    python3 scripts/probes/upstream_pr_classifier.py \\
        --repo OWNER/REPO \\
        --pr 142 \\
        --pr-title "Add some_new_flag" \\
        --pr-url https://github.com/OWNER/REPO/pull/142 \\
        --pr-body-file /tmp/pr-body.txt \\
        --pr-diff-file /tmp/pr-diff.txt \\
        --out-json /tmp/upstream-classification.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-sonnet-4-6"

# Map upstream repos to the doc trees they typically touch. The classifier
# uses these hints to suggest concrete file paths in the affected_doc_files
# output, so the DM ends up actionable instead of "go look around the
# whole repo."
#
# This source file lives in a public repo, so we deliberately avoid
# hardcoding upstream repo names here — they're loaded from a workflow
# secret at runtime (UPSTREAM_REPO_HINTS_JSON, set on the docs repo).
# Format of the secret: a JSON object mapping `owner/repo` -> list of
# doc-tree path hints. Operators control the mapping; this code stays
# generic.
def load_repo_doc_hints() -> dict[str, list[str]]:
    blob = os.environ.get("UPSTREAM_REPO_HINTS_JSON", "").strip()
    if not blob:
        return {}
    try:
        return json.loads(blob)
    except json.JSONDecodeError as e:
        print(f"WARN: UPSTREAM_REPO_HINTS_JSON is not valid JSON: {e}", file=sys.stderr)
        return {}


REPO_DOC_HINTS = load_repo_doc_hints()

SYSTEM_PROMPT = """You are the docs-impact reviewer for Smallest AI.

You receive a merged PR from an upstream backend or demos repo
(lightning-asr-offline / waves-platform / atoms-platform / godspeed).
Your job: decide whether this docs repo needs an update, and if so,
which files.

Return ONE of three verdicts:

DOCS_NEEDED — the PR introduces, removes, renames, or changes the default
of any of:
  - A public API endpoint, query parameter, or request/response field
  - A WebSocket message type or event
  - A supported language code, voice ID, model name, or output format
  - A feature flag (`punctuation`, `format`, `redact_pii`, etc.)
  - An error code or error message string
  - A rate limit or concurrency constraint
  - A default value the docs explicitly state
  - A breaking change to an existing surface
Or if the PR adds an entirely new feature/endpoint/SDK surface.

MAYBE — the PR is internal refactor / perf / test / log changes that
*could* leak into customer-visible behavior but probably don't. Examples:
internal helper rename, dependency bump, test-only changes that touch
public interfaces in passing.

NO_DOCS_IMPACT — the PR is purely internal: tests, CI config, README,
infra, comments, internal modules with no API surface change.

For DOCS_NEEDED, list specific doc files in the docs repo that need
review. Use the `repo_doc_hints` provided to pick the paths most likely
to need edits (don't invent paths outside that hint set unless the PR
clearly affects something else).

Output format: a SINGLE valid JSON object with these keys, nothing else:
{
  "verdict": "DOCS_NEEDED" | "MAYBE" | "NO_DOCS_IMPACT",
  "summary": "1-2 sentences: what changed in the PR and why it matters (or doesn't) for docs.",
  "affected_doc_files": ["<path in docs repo, empty if NO_DOCS_IMPACT>"],
  "questions_for_human": ["<short question only if MAYBE — what info would let you decide DOCS_NEEDED vs NO_DOCS_IMPACT>"]
}

Be ruthless about NO_DOCS_IMPACT. Most upstream PRs don't need doc
updates. Only fire DOCS_NEEDED when there's a clear customer-visible
change."""

USER_TEMPLATE = """Upstream repo: {repo}
PR: #{pr_number} — {pr_title}
URL: {pr_url}

Likely-affected doc paths in this repo (hints, may or may not apply):
{repo_doc_hints}

PR body:
```
{pr_body}
```

PR diff (truncated to keep prompt size reasonable):
```
{pr_diff}
```

Classify per the rules. Return only the JSON object."""

# Cap the diff content so we don't blow the prompt window on huge PRs.
MAX_DIFF_CHARS = 30000


def call_anthropic(payload: dict, api_key: str) -> dict:
    body = {
        "model": MODEL,
        "max_tokens": 1024,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": USER_TEMPLATE.format(**payload)}],
    }
    req = urllib.request.Request(
        ANTHROPIC_URL,
        data=json.dumps(body).encode(),
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as e:
        body_txt = e.read().decode("utf-8", "replace")
        print(f"Anthropic API HTTP {e.code}: {body_txt[:500]}", file=sys.stderr)
        raise
    text = "".join(b["text"] for b in data["content"] if b["type"] == "text").strip()
    if text.startswith("```"):
        text = text.strip("`").lstrip("json").strip()
    return json.loads(text)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--repo", required=True, help="owner/name of the upstream repo")
    p.add_argument("--pr", required=True, type=int, help="PR number")
    p.add_argument("--pr-title", required=True)
    p.add_argument("--pr-url", required=True)
    p.add_argument("--pr-body-file", help="file containing PR body")
    p.add_argument("--pr-diff-file", help="file containing PR diff (will be truncated)")
    p.add_argument("--out-json", required=True)
    args = p.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        print("WARN: ANTHROPIC_API_KEY not set; defaulting to NO_DOCS_IMPACT.", file=sys.stderr)
        Path(args.out_json).write_text(json.dumps({
            "verdict": "NO_DOCS_IMPACT",
            "summary": "Classifier skipped — ANTHROPIC_API_KEY not set in workflow env.",
            "affected_doc_files": [],
            "questions_for_human": [],
        }, indent=2))
        return 0

    pr_body = ""
    if args.pr_body_file and Path(args.pr_body_file).exists():
        pr_body = Path(args.pr_body_file).read_text()[:8000]  # cap body too

    pr_diff = ""
    if args.pr_diff_file and Path(args.pr_diff_file).exists():
        pr_diff = Path(args.pr_diff_file).read_text()
        if len(pr_diff) > MAX_DIFF_CHARS:
            pr_diff = pr_diff[:MAX_DIFF_CHARS] + f"\n\n... (diff truncated at {MAX_DIFF_CHARS} chars)"

    hints = REPO_DOC_HINTS.get(args.repo, ["(no specific doc-tree hints for this repo)"])
    repo_doc_hints = "\n".join(f"  - {h}" for h in hints)

    result = call_anthropic({
        "repo": args.repo,
        "pr_number": args.pr,
        "pr_title": args.pr_title,
        "pr_url": args.pr_url,
        "repo_doc_hints": repo_doc_hints,
        "pr_body": pr_body or "(no body)",
        "pr_diff": pr_diff or "(no diff captured)",
    }, api_key)

    for key in ("verdict", "summary", "affected_doc_files", "questions_for_human"):
        if key not in result:
            print(f"ERROR: classifier response missing key '{key}': {result}", file=sys.stderr)
            return 1
    if result["verdict"] not in ("DOCS_NEEDED", "MAYBE", "NO_DOCS_IMPACT"):
        print(f"ERROR: unexpected verdict '{result['verdict']}'", file=sys.stderr)
        return 1

    Path(args.out_json).write_text(json.dumps(result, indent=2))
    print(f"Verdict: {result['verdict']}")
    print(f"Summary: {result['summary']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
