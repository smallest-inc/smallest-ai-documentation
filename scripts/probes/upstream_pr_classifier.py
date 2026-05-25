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
import re
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


# ---------------------------------------------------------------------------
# Changelog-section parser
#
# Both upstream PR templates (atoms-platform, waves-platform — merged
# 2026-05-18/20) start the PR body with a `## 📢 Changelog (customer-facing)`
# section. Authors either fill it in with structured fields or write the
# single word `internal` to opt out.
#
# When this section is present and well-formed we trust it absolutely:
#   • "internal" → NO_DOCS_IMPACT, skip the LLM (cost saving + author intent)
#   • structured → DOCS_NEEDED, skip the LLM, surface parsed fields downstream
#
# When it's missing we fall through to the legacy LLM-only path so older PRs
# (or repos that haven't adopted the template yet) still get classified.
# ---------------------------------------------------------------------------

# Tolerate either the rendered emoji or the GitHub shortcode, with or without
# the "(customer-facing)" suffix in case teams later trim it.
_CHANGELOG_HEADING_RE = re.compile(
    r"^##\s*(?:📢|:loudspeaker:)\s*Changelog(?:\s*\(customer-facing\))?\s*$",
    re.MULTILINE,
)
# The labelled fields in the template, in order. Each label below corresponds
# to a **bold** marker in the template body.
_TEMPLATE_FIELDS = [
    ("ticket",            "Linear ticket"),
    ("title",             "Title"),
    ("category",          "Category"),
    ("changelog_surface", "Changelog surface"),   # waves-platform only
    ("body",              "Customer-facing body"),
    ("code_sample",       "Code sample"),
    ("ships",             "Ships"),
    ("migration",         "Migration required"),
    ("byline",            "Byline"),
]
# Each field label can be followed by a `(parenthesized hint)` and a `:` then
# whitespace, on the same line as `**Label**`. We capture everything after
# the colon until the next field marker.
_FIELD_RE_CACHE: dict[str, re.Pattern] = {}


def _field_re(label: str) -> re.Pattern:
    if label not in _FIELD_RE_CACHE:
        # Anchored: line starts with `**Label**` (after optional whitespace),
        # then tolerates a parenthesized hint, then an optional colon, then
        # captures the body until the next `**Label**` field or section end.
        # The parenthesized hint is OUTSIDE the bold (after `**`) in our
        # templates, so we skip it explicitly here.
        _FIELD_RE_CACHE[label] = re.compile(
            r"^\s*\*\*" + re.escape(label) + r"[^*]*\*\*"  # **Label** (label may have appended " (dedup key — …)")
            r"\s*(?:\([^)]*\))?"                            # optional `(parenthesized hint)` outside the bold
            r"\s*:?\s*\n?(.*?)"                             # optional colon, then body
            r"(?=^\s*\*\*[A-Z]|\Z)",                        # until next field marker / EOF
            re.MULTILINE | re.DOTALL,
        )
    return _FIELD_RE_CACHE[label]


def _strip_html_comments(text: str) -> str:
    return re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)


def _strip_template_artifacts(value: str) -> str:
    """Drop placeholder bracket-hints, HTML comments, and leftover whitespace."""
    value = _strip_html_comments(value)
    # Drop common placeholder bracket-hints the template leaves in
    # (`<!-- "live now" | ... -->` survives strip; this catches inline `<...>`).
    value = re.sub(r"^<[^>]+>$", "", value, flags=re.MULTILINE)
    return value.strip()


def _looks_internal_only(section_text: str) -> bool:
    """True if the only meaningful content in the section is 'internal'."""
    cleaned = _strip_html_comments(section_text).strip()
    # Strip line-leading bullet / quote / heading markers, but preserve
    # in-word hyphens so 'internal-only' still matches.
    cleaned = re.sub(r"^[\s>#]*[-*]\s*", "", cleaned, flags=re.MULTILINE)
    # Strip bold/italic/code markers (keep alnum + hyphen + space).
    cleaned = re.sub(r"[*`\[\]]", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip().lower()
    return cleaned in {"internal", "internal only", "internal-only"}


def _parse_category(raw: str) -> str | None:
    """Pick the first checked category from the markdown checklist."""
    for line in raw.splitlines():
        if re.match(r"^\s*-\s*\[x\]\s*", line, re.IGNORECASE):
            return re.sub(r"^\s*-\s*\[x\]\s*", "", line, flags=re.IGNORECASE).strip()
    return None


def _parse_surface(raw: str) -> str | None:
    """Pick the first checked 'Changelog surface' value from the markdown checklist."""
    for line in raw.splitlines():
        if re.match(r"^\s*-\s*\[x\]\s*", line, re.IGNORECASE):
            # Surface lines look like: "- [x] `general` → /waves/.../general"
            m = re.search(r"`([^`]+)`", line)
            if m:
                return m.group(1)
            # Fallback: take the first word after the checkbox
            stripped = re.sub(r"^\s*-\s*\[x\]\s*", "", line, flags=re.IGNORECASE).strip()
            return stripped.split()[0] if stripped else None
    return None


def _parse_code_sample(raw: str) -> str | None:
    """Extract the fenced code block under the 'Code sample' field."""
    m = re.search(r"```[a-zA-Z0-9_+-]*\n(.*?)\n```", raw, re.DOTALL)
    if not m:
        return None
    code = m.group(1).strip()
    return code or None


def parse_changelog_section(body: str) -> dict | None:
    """Parse the PR-template changelog section.

    Returns:
      None              — section not present at all (legacy PR, fall back to LLM)
      {"kind": "internal"}                — author marked PR as internal-only
      {"kind": "structured", "fields": …} — structured fields parsed
    """
    if not body:
        return None
    m = _CHANGELOG_HEADING_RE.search(body)
    if not m:
        return None
    # Capture from end of heading to the next `##` heading or to end-of-body
    section = body[m.end():]
    next_heading = re.search(r"^##\s+(?!📢|:loudspeaker:)", section, re.MULTILINE)
    if next_heading:
        section = section[:next_heading.start()]
    # Also stop at horizontal-rule separator the template uses
    hr = re.search(r"^\s*---\s*$", section, re.MULTILINE)
    if hr:
        section = section[:hr.start()]

    if _looks_internal_only(section):
        return {"kind": "internal"}

    # Try to extract each labelled field
    fields: dict[str, str] = {}
    for key, label in _TEMPLATE_FIELDS:
        fm = _field_re(label).search(section)
        if not fm:
            continue
        raw = fm.group(1)
        if key == "code_sample":
            value = _parse_code_sample(raw)
        elif key == "category":
            value = _parse_category(raw)
        elif key == "changelog_surface":
            value = _parse_surface(raw)
        else:
            value = _strip_template_artifacts(raw)
        if value:
            fields[key] = value

    # A section that has only field labels and no actual content (i.e. the
    # author opened the template, didn't fill it in, and didn't type
    # 'internal') isn't actionable; treat as missing.
    if not fields:
        return None
    return {"kind": "structured", "fields": fields}


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

    # Read PR body BEFORE the API-key gate so we can short-circuit on the
    # changelog template even when the LLM is unavailable.
    pr_body = ""
    if args.pr_body_file and Path(args.pr_body_file).exists():
        # Read the full body for the changelog parser; we cap separately
        # before passing to the LLM below.
        pr_body = Path(args.pr_body_file).read_text()

    # --- Template-aware short-circuit ----------------------------------------
    # If the upstream PR uses the new `## 📢 Changelog (customer-facing)`
    # template, trust author intent over LLM classification.
    changelog = parse_changelog_section(pr_body)
    if changelog:
        if changelog["kind"] == "internal":
            result = {
                "verdict": "NO_DOCS_IMPACT",
                "summary": (
                    "Author marked PR as internal-only in the changelog template "
                    "(`## 📢 Changelog` section contained the word 'internal')."
                ),
                "affected_doc_files": [],
                "questions_for_human": [],
                "changelog": {"kind": "internal"},
            }
        else:
            fields = changelog["fields"]
            title = fields.get("title") or args.pr_title
            body_line = fields.get("body") or "(no customer-facing body filled in)"
            result = {
                "verdict": "DOCS_NEEDED",
                "summary": f"{title} — {body_line[:240]}",
                "affected_doc_files": [],  # filled by entry-generator step downstream
                "questions_for_human": [],
                "changelog": {"kind": "structured", "fields": fields},
            }
        Path(args.out_json).write_text(json.dumps(result, indent=2))
        print(f"Verdict: {result['verdict']}  (from changelog template, LLM skipped)")
        print(f"Summary: {result['summary']}")
        return 0
    # ------------------------------------------------------------------------

    # No template section — fall back to the legacy LLM classifier.
    api_key_for_llm = api_key  # already validated above
    pr_body = pr_body[:8000]   # now cap for the LLM prompt

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
    }, api_key_for_llm)

    for key in ("verdict", "summary", "affected_doc_files", "questions_for_human"):
        if key not in result:
            print(f"ERROR: classifier response missing key '{key}': {result}", file=sys.stderr)
            return 1
    if result["verdict"] not in ("DOCS_NEEDED", "MAYBE", "NO_DOCS_IMPACT"):
        print(f"ERROR: unexpected verdict '{result['verdict']}'", file=sys.stderr)
        return 1
    result.setdefault("changelog", None)  # signal: no template section present

    Path(args.out_json).write_text(json.dumps(result, indent=2))
    print(f"Verdict: {result['verdict']}")
    print(f"Summary: {result['summary']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
