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

→ [Full guide](/voice-agents/platform/features/versioning)
```

### When to add a changelog entry

- New customer-visible feature (new endpoint, new event, new SDK, new model).
- Breaking API change or deprecation.
- Significant customer-impact bug fix.

### When not to

- Doc-only PRs (restructures, link fixes, typo cleanups).
- Internal refactors, CI changes, nav reorganization.
- Migration guides and how-to content (already ship through the normal docs tree).

### CI enforcement

Any PR that modifies a file under `fern/apis/**/*.yaml` (OpenAPI or AsyncAPI spec) must add a file under a `changelog-entries/` directory. The "Changelog entry for spec change" GitHub Action blocks the PR otherwise.

If the spec change is not customer-visible (description-only edit, internal refactor, comment fix), add the `skip-changelog` label to the PR and re-run the check.

## Spec layers (Waves TTS + STT)

Every TTS/STT endpoint in the Waves product is described across **three** YAML files. Editing only one is the most common cause of "I changed the spec but the docs still show the old text." Know which layer feeds which surface before you start.

### The three layers (top → bottom of precedence)

```
┌───────────────────────────────────────────────────────────┐
│  Layer 1: BASE SPEC                                       │
│  fern/apis/waves/openapi/<endpoint>.yaml                  │
│  fern/apis/waves/asyncapi/<endpoint>-ws.yaml              │
│  → Feeds: SDK code-gen (Python, TypeScript, Go)           │
│  → Owns: schema shape (paths, params, types, enums)       │
└───────────────────────────────────────────────────────────┘
         ▲ decorated by ▼
┌───────────────────────────────────────────────────────────┐
│  Layer 2: SDK SIBLING OVERRIDE                            │
│  fern/apis/waves/openapi/<endpoint>-overrides.yaml        │
│  fern/apis/waves/asyncapi/<endpoint>-ws-overrides.yml     │
│  → Feeds: SDK code-gen on top of base                     │
│  → Adds: operationId, x-fern-sdk-method-name              │
└───────────────────────────────────────────────────────────┘
         ▲ decorated by ▼
┌───────────────────────────────────────────────────────────┐
│  Layer 3: V4 DOCS OVERRIDE                                │
│  fern/apis/waves-v4/overrides/<endpoint>-overrides.yaml   │
│  fern/apis/waves-v4/overrides/<endpoint>-ws-overrides.yml │
│  → Feeds: the API reference pages on docs.smallest.ai     │
│  → Adds: rich Markdown description, code examples,        │
│          deprecation warnings, x-fern-audiences           │
└───────────────────────────────────────────────────────────┘
```

### Which layer to edit for which intent

| You want to… | Edit |
|---|---|
| Add or change a request/response field shape | Layer 1 (base) — schema is the source of truth |
| Add a code example, change the public docs description | Layer 3 (v4 docs override) — that's what the docs site renders |
| Rename the SDK method | Layer 2 (sibling override) — set `x-fern-sdk-method-name` |
| Mark an endpoint deprecated with strikethrough + IDE warning | Add `deprecated: true` to **both** Layer 2 AND Layer 3 — Layer 2 fires SDK `@deprecated`, Layer 3 fires nav strikethrough |
| Change which docs audiences see this endpoint | Layer 3 — set `x-fern-audiences: [v4docs]` (missing this means the endpoint vanishes from the docs build entirely) |

### Spec drift check

Layer 1 and Layer 3 both have a `description:` field. If they differ, `scripts/spec-live-tests/spec_drift_check.py` fails. The convention is:

- **Layer 3 is the rich, authoritative version** — full Markdown, multiple code examples, common gotchas.
- **Layer 1 mirrors Layer 3** verbatim. This keeps the SDK docstrings as informative as the public docs.
- When in doubt, copy Layer 3 → Layer 1, not the other way around. Going the other direction strips the rich content from the docs site.

The other tracked fields the drift check enforces equality on: `default`, `example`, `examples`, `enum`. Layer 1's structure (paths, parameter names, types) does NOT have to match Layer 3 — Layer 3 can omit fields it doesn't need to override.

### TTS unified surface (post v3.1 Pro launch, 2026-05-15)

The canonical TTS routes are now:

- `POST /waves/v1/tts` — sync REST
- `POST /waves/v1/tts/live` — Server-Sent Events streaming
- `WSS /waves/v1/tts/live` — WebSocket streaming

The model is selected via the `model` body field (`lightning_v3.1` default, or `lightning_v3.1_pro`). The legacy model-named routes (`/waves/v1/lightning-v3.1/get_speech`, `/stream`, `/get_speech/stream`) are marked `deprecated: true` and scheduled for retirement on **2026-07-14**. Don't add new params to the legacy specs — add them to the unified specs (`tts-openapi.yaml`, `tts-ws.yaml`) instead.

### Deprecation pattern

| Endpoint state | Title suffix | `deprecated: true` | Visible effect |
|---|---|---|---|
| Current model, route superseded (Lightning v3.1) | `(Endpoint Deprecated)` | **Yes** — on both Layer 2 and Layer 3 | Strikethrough in nav + SDK `@deprecated` + `<Warning>` block on the endpoint page with the retirement date |
| Model + route both retired (Lightning v2) | `(Deprecated)` | No (legacy convention) | Label only, no strikethrough |
| AsyncAPI WebSocket | label in `title:` field of the channel override | n/a — Fern doesn't honor `deprecated:` on AsyncAPI | No strikethrough mechanism; the label and Layer 3 Warning block carry the message |

### Common gotchas

- **Missing `x-fern-audiences`** on a Layer 3 channel override → Fern omits the endpoint from the docs sidebar entirely. Every AsyncAPI channel override must declare its audience.
- **Forgetting the version mirror.** Every file under `fern/products/waves/pages/v4.0.0/...mdx` has a parallel copy under `fern/products/waves/versions/v4.0.0/...mdx`. The `v4 docs mirror` CI check fails if you touch one without the other. After editing in `pages/`, run `cp` to the matching path under `versions/`.
- **`# ci:skip` for snippets that need extra deps** like `sounddevice` / `numpy` for audio playback — they're not installed in CI. Without the directive, `scripts/run_doc_python_snippets.py` runs the block and fails on the missing import.
- **AsyncAPI override-key parity (HARD RULE).** Every `channels.<chan>.messages.<KEY>` and `operations.<KEY>` in a Layer 2 or Layer 3 override must use the **exact same key** as Layer 1 (base). Orphan keys cause Fern's merger to silently drop sibling operations from the rendered docs — that's how `sendFinalize` was missing from the Pulse STT API ref for 5+ weeks (PR #189). `spec_drift_check.py` enforces this; the `KEY_PARITY_ALLOWLIST` is reserved for retiring specs only, never active surfaces.
- **Quote any YAML scalar whose value contains a colon (HARD RULE).** Both spec YAMLs (`fern/apis/...`) and MDX frontmatter blocks use real YAML parsers. Any unquoted scalar with `: ` (colon-space) anywhere in the value is a syntax bomb — the parser thinks it's a nested mapping and the entire build fails. Examples that have bitten us three times: `description: Send {"type": "finalize"} …`, `description: Set is_final: true on the response`, `description: Opt in with \`word_timestamps: true\` …`. Wrap the whole value in single quotes (`description: 'Set is_final: true on the response.'`) or split into a block scalar with `description: |` + indented body. Run `python -c "import yaml,re; yaml.safe_load(re.match(r'---\\n(.*?)\\n---', open(F).read(), re.S).group(1))"` on the file before commit if you've put any inline code in frontmatter.

## Pre-flight checklist before you push

The bugs we've shipped tend to share a pattern: the spec is on disk, `fern check` passes, but the rendered docs lose content during merge — or the prose drifts away from the section's promise. Before declaring a docs edit done:

1. **Run all three gates.** They each catch a different class of bug:
   ```bash
   fern check                                                    # YAML structural validity
   python3 scripts/spec-live-tests/spec_drift_check.py            # description + key-parity drift
   python3 scripts/check_nav.py                                   # orphan pages + dangling links
   ```
2. **Verify behavior against source of truth.** For wire claims, the platform repos (`waves-platform`, `atoms-platform`) win over docs. For schema, Layer 1 (base spec) wins over override. Never document behavior you haven't either read in the source or live-tested.
3. **Re-read every modified section against its heading.** If the heading is "Recommended Setup for Agentic Use Cases", does the body and code example actually deliver an agentic setup? Single-sentence correctness is not enough — section coherence matters more (PR #189 fixed a section whose heading promised an agentic setup but whose body recommended the single-shot pattern).
4. **Live-test where possible.** `SMALLEST_API_KEY=… python3 scripts/spec-live-tests/<service>_live_test.py`.
5. **Mirror parity.** `diff -rq fern/products/waves/pages/v4.0.0/ fern/products/waves/versions/v4.0.0/` should produce zero diff on any path you touched.
6. **Trust the post-deploy smoke check.** `scripts/spec-live-tests/docs_render_smoke.py` runs after every push to `main` (see `.github/workflows/publish-docs.yml`) and fetches the rendered docs, asserting every expected operation / signal / section appears. If it fails on your change, the spec is correct on disk but Fern dropped something — investigate the override layering, don't just retry.

## Before you push

1. Run `python3 scripts/check_nav.py` (catches orphan pages and dangling nav entries).
2. Run `python3 scripts/check_links.py path/to/changed.mdx` (HEAD-verifies every internal link against docs.smallest.ai).
3. Re-read the commit subject. If over 72 characters, trim.

## Keeping the cookbook in sync

The `smallest-inc/cookbook` repo holds the runnable end-to-end samples
that this docs repo links to and embeds via URL (audio fixtures, full
SDK demos, integration recipes). If a docs change affects API surface
that the cookbook also demonstrates, both repos must move together —
otherwise readers hit a broken cookbook script the moment they follow
a "Full runnable source files:" link from a quickstart.

**When to update the cookbook alongside a docs PR:**

- Adding, removing, or renaming a parameter on a Pulse STT / Lightning TTS endpoint.
- Changing default behavior (e.g., `language` default, `format=false` cascade).
- Changing protocol shape (e.g., `finalize` vs `close_stream` for end-of-stream).
- Renaming or moving an audio fixture under `speech-to-text/getting-started/samples/`.

**Process:**

1. Open the docs PR.
2. In the same hour, open the cookbook PR — same commit subject prefix (`fix(stt):`, `feat(tts):`, etc.) so the pair is searchable.
3. Cross-link both PRs in their bodies (`Companion: smallest-inc/cookbook#NN` / `Companion: smallest-inc/smallest-ai-documentation#NN`).
4. Merge cookbook first. Cookbook's `test-docs-snippets.yml` runs the samples against the live API on every PR; if it can't pass, the docs PR is misaligned with reality and shouldn't merge either.

**Fail-safes if the pair drifts anyway:**

- The docs repo's `test-quickstarts.yml` runs `scripts/run_doc_python_snippets.py` against the live API on every PR that touches v4 STT MDX. Stale embedded snippets fail the build.
- The cookbook's `test-docs-snippets.yml` exercises `transcribe-python.py` and `websocket-python.py` end-to-end on every PR + a weekly Monday cron. The Slack webhook in that workflow fires on failure.
- Both safety nets can catch one-side drift, but the *paired-PR* convention above is what keeps the time-to-detection close to zero.

## When in doubt

Existing MDX in the same product tab is the best style reference. Match its register and depth. When the primary product brand naming differs from internal engineering names, use the customer-facing term (for example, "TTS Lightning v3.1", not the internal "Waves" label in prose).
