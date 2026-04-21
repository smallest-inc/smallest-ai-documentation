# Contributing

Internal contributor guide for the Smallest AI documentation repo.

## Commit messages

Use Conventional Commits. Keep them tight.

```
type(scope): subject line under 72 characters

Optional body. Only when WHY is not obvious from the diff.
Max 3 short paragraphs, ~80 columns.
```

**Types**: `docs`, `fix`, `feat`, `refactor`, `chore`, `ci`, `revert`.

**Scopes**: `atoms`, `waves`, `nav`, `ci`, `openapi`, `asyncapi`.

**Body required when**:

- The WHY is non-obvious (incident, regression, customer report, backend spec mismatch).
- Breaking change (add `!` after type or a `BREAKING CHANGE:` footer).
- References an external source (backend PR, spec version, ticket).

**Body not required for** typo fixes, renames, dead-code removal, link fixes, and most doc-only PRs.

**Do not** enumerate every file touched, recite validation steps, or include "pre-commit checklist" text. The diff and CI cover that.

### Examples

Good:

```
fix(atoms): correct Fern slug /web-socket-sdk (was /websocket-sdk)
```

```
feat(atoms): agent versioning — drafts, publish, activate

Backend PR atoms-platform#2449 shipped the drafts + versions model.
Every config change now flows through a draft; publishing creates a
new immutable version. Prior PATCH /agent/{id} returns 400 on
config fields.
```

Bad: a 60-line body on a one-file fix. A body that explains how the author debugged it. A body that lists every linter rule that passed.

## Changelog entries

Product-visible changes ship with a changelog entry in the same PR (or immediately after). Entries are plain MDX files in `changelog-entries/` directories, one file per release.

- **Atoms**: `fern/products/atoms/pages/intro/reference/changelog-entries/`
- **Waves v4**: `fern/products/waves/pages/v4.0.0/changelog-entries/`

### File naming

`YYYY-MM-DD-short-slug.mdx`

Example: `2026-04-20-agent-versioning.mdx`.

### Frontmatter

```mdx
---
title: Short descriptive headline
---

Two to four lines of body. What shipped. Link to the full docs
page for anyone who wants the detail.

→ [Full guide](/atoms/atoms-platform/features/versioning)
```

### When to add a changelog entry

- New customer-visible feature (new endpoint, new event, new SDK, new model).
- Breaking API change or deprecation.
- Significant customer-impact bug fix.

### When not to

- Doc-only PRs (restructures, link fixes, typo cleanups).
- Internal refactors, CI changes, nav reorganization.
- Migration guides and how-to content (already ship through the normal docs tree).

## Before you push

1. Run `python3 scripts/check_nav.py` (catches orphan pages and dangling nav entries).
2. Run `python3 scripts/check_links.py path/to/changed.mdx` (HEAD-verifies every internal link against docs.smallest.ai).
3. Re-read the commit subject. If over 72 characters, trim.

## When in doubt

Existing MDX in the same product tab is the best style reference. Match its register and depth. When the primary product brand naming differs from internal engineering names, use the customer-facing term (for example, "TTS Lightning v3.1", not the internal "Waves" label in prose).
