# Wire `phonon-uv` into the docs changelog automation

If Hydra ships from `smallest-inc/phonon-uv` (separate repo from `waves-platform`), apply the two files below to that repo so its merged PRs show up in the docs changelog flow the same way atoms-platform and waves-platform PRs do.

If the team decides Hydra changes will continue to ship from `waves-platform` (one PR, one entry, surface = `hydra`), skip this guide — the docs side already routes `hydra` correctly per `scripts/probes/open_docs_changelog_pr.py`.

---

## 1. `.github/workflows/notify-docs-on-merge.yml`

Copy verbatim from `waves-platform`'s already-installed copy:

```yaml
# COPY THIS FILE INTO EACH UPSTREAM REPO at .github/workflows/notify-docs-on-merge.yml
#
# Required upstream-repo setup (one-time per repo):
#   1. Create a fine-grained PAT (or GitHub App installation token) with
#      "Contents: read" + "Metadata: read" on the upstream repo, and
#      "Repository dispatches: write" on the docs repo.
#   2. Add two secrets in this upstream repo:
#        DOCS_DISPATCH_TOKEN  — the PAT above
#        DOCS_REPO_OWNER_NAME — the docs repo as `owner/name` (e.g. set
#                              once in your internal runbook). Kept as a
#                              secret so this public-template file does
#                              not enumerate the docs/upstream relationship.
#   3. Commit this workflow file. From the next merged PR onwards, the
#      docs repo's pr-drift-detector.yml gets a repository_dispatch
#      event, runs the Claude classifier, and DMs the docs owner only if
#      verdict == DOCS_NEEDED or MAYBE.

name: Notify docs of merged PR

permissions: {}

on:
  pull_request:
    types: [closed]

jobs:
  signal-docs-repo:
    if: github.event.pull_request.merged == true
    runs-on: ubuntu-latest
    steps:
      - name: Dispatch upstream_pr_merged event to docs repo
        env:
          DOCS_DISPATCH_TOKEN: ${{ secrets.DOCS_DISPATCH_TOKEN }}
          DOCS_REPO_OWNER_NAME: ${{ secrets.DOCS_REPO_OWNER_NAME }}
        run: |
          : "${DOCS_REPO_OWNER_NAME:?DOCS_REPO_OWNER_NAME secret not set on this repo}"
          jq -n \
            --arg repo "${{ github.repository }}" \
            --arg pr_number "${{ github.event.pull_request.number }}" \
            --arg pr_title  "${{ github.event.pull_request.title }}" \
            --arg pr_url    "${{ github.event.pull_request.html_url }}" \
            --arg merged_by "${{ github.event.pull_request.merged_by.login }}" \
            --arg base_ref  "${{ github.event.pull_request.base.ref }}" \
            '{
              event_type: "upstream_pr_merged",
              client_payload: {
                repo: $repo,
                pr_number: ($pr_number | tonumber),
                pr_title: $pr_title,
                pr_url: $pr_url,
                merged_by: $merged_by,
                base_ref: $base_ref
              }
            }' > /tmp/dispatch.json
          curl -sSf -X POST \
            -H "Authorization: Bearer $DOCS_DISPATCH_TOKEN" \
            -H "Accept: application/vnd.github+json" \
            "https://api.github.com/repos/${DOCS_REPO_OWNER_NAME}/dispatches" \
            -d @/tmp/dispatch.json
```

> The fully-tested copy lives in `waves-platform` at `.github/workflows/notify-docs-on-merge.yml`. If anything in this guide drifts from the source-of-truth copy there, prefer the one in `waves-platform`.

---

## 2. `.github/PULL_REQUEST_TEMPLATE.md`

The `Changelog surface` picker for phonon-uv should be set to `hydra` (the only Hydra-related surface today). Copy the waves-platform template verbatim, then replace the **Changelog surface** block with:

```markdown
**Changelog surface** (pick one — this picks the docs page):
- [x] `hydra` → /waves/v-4-0-0/changelog/hydra (speech-to-speech)
```

(Single option, default-checked. The docs side accepts `hydra` and routes the entry into `fern/products/waves/pages/v4.0.0/changelog-entries/hydra/`. Mirror happens automatically.)

---

## 3. Secrets to set on `phonon-uv`

| Name | Value |
|---|---|
| `DOCS_DISPATCH_TOKEN` | A fine-grained PAT (or GitHub App token) with `Repository dispatches: write` on the docs repo + `Contents: read` and `Metadata: read` on this repo. |
| `DOCS_REPO_OWNER_NAME` | `smallest-inc/smallest-ai-documentation` |

---

## 4. Smoke test

After both files are merged + the secrets are set:

1. Merge any small PR into phonon-uv whose body includes a filled-in `## 📢 Changelog (customer-facing)` section.
2. Watch the docs repo's Actions tab → `PR drift detector` should fire within ~30 s.
3. The classifier short-circuits on the structured section, surfaces parsed fields in Slack, and opens a docs PR with the changelog entry pre-filled.
4. Review the docs PR, polish the prose, merge.

If you write `internal` in the changelog section instead, the docs side stays silent (no Slack ping, no PR opened). That's expected.

---

## What if the team decides Hydra continues to ship from `waves-platform`?

No action on phonon-uv. Authors of Hydra-related PRs in `waves-platform` pick the `hydra` surface in the existing template (assuming the waves-platform template gets updated to expose that option — see the docs-side note in PR #182). The docs flow is unchanged.
