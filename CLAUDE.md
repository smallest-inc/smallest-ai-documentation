# Repo rules — smallest-ai-documentation

## Spec edits — base vs override layers (HARD RULE)

The waves API has **three spec layers**, not one. Editing the base spec alone will not always show up on docs. Always check which layer drives the surface you intend to change.

| Layer | Path | Drives |
|---|---|---|
| Base spec | `fern/apis/waves/{openapi,asyncapi}/*.yaml` | Source of truth for structure |
| SDK gen overrides | `fern/apis/waves/{openapi,asyncapi}/*-overrides.yaml` (siblings) | SDK method names, examples, deprecations for generated clients via `fern/apis/unified/generators.yml` |
| v4 docs render overrides | `fern/apis/waves-v4/overrides/*.yaml` (separate dir) | What renders on `docs.smallest.ai/waves/*` API reference pages via `fern/apis/waves-v4/generators.yml` |

**The trap:** a `description`, `default`, `enum`, or `example` set in `waves-v4/overrides/*` **wins** on the docs render. Editing the same field in the base spec is invisible until the override is also updated. Same in the other direction for SDK consumers (waves-overrides wins).

**The rule for any spec-touching PR:**
1. Identify which layer governs the surface you want to change (docs page / SDK / both).
2. Run `python3 scripts/spec-live-tests/spec_drift_check.py` locally before pushing.
3. Update both base and override in lockstep when a tracked content field exists in both.
4. CI will block the PR if the drift check fails.

**Atoms also has its own base + override pairs** (corrected from an earlier note in this file). The atoms layout is:
- REST: `fern/apis/atoms/openapi/openapi.yaml` + sibling `openapi-overrides.yaml` + `ai_examples_override.yml`
- WS:   `fern/apis/atoms/asyncapi/agent-ws.yaml` + sibling `agent-ws-overrides.yaml` (the realtime agent endpoint at `WSS /atoms/v1/agent/connect`)

The drift CI auto-discovers all of these — atoms and waves both. The atoms WS endpoint renders at `/atoms/api-reference/api-reference/realtime-agent/realtime-agent` and is the primary surface for the WebSocket SDK + mobile widget integration guides.

## Auditing API surface — count BOTH OpenAPI paths AND AsyncAPI channels

When verifying that the docs render every documented endpoint, walk *both*:
- Every `paths.<path>.<method>` in any `openapi*.yaml` under `fern/apis/`
- Every `channels.<chan>` in any `asyncapi*.yaml` under `fern/apis/`

The atoms realtime agent endpoint lives in `fern/apis/atoms/asyncapi/agent-ws.yaml` and is easy to miss if you only look at `openapi/`. Same for the four waves WS specs (`pulse-stt-ws`, `lightning-v3.1-ws`, `lightning-v2-ws`, `stream-tts-ws`). A spec audit that only counts REST operations under-reports.

## Pulse STT WS exception — cross-structural-path drift

The v4 docs override for `pulse-stt-ws` puts param descriptions under `channels.pulseStream.parameters.<name>`. The base spec has them buried under `channels.pulseStream.messages.<msg>.payload.properties.<name>`. Fern's docs render reads from the override's `parameters` block. The drift check covers this cross-path comparison automatically — don't chase it manually.

## Always test API calls before documenting them

Live-verify every flag, param, response shape claim before merging. The PR template + the `api-spec-live-test` workflow exist because we have shipped wrong docs in the past. Don't trust `fern check` alone — it validates structure, not behavior.

## Project conventions

- **Versions are frozen:** never touch `fern/products/waves/versions/v2.2.0` or `v3.0.1`. v4.0.0 only.
- **Both `pages/` and `versions/` mirrors must change together** when editing v4 content under `fern/products/waves/`. Catch with link/nav check.
- **Commits:** never add `Co-Authored-By: Claude` or "Generated with Claude Code". Use git config user.name + user.email.
- **PR titles + bodies:** terse, customer-safe, no AI persona, no rabbit-hole detail. Conventional Commits format.
- **Don't push to remote unless explicitly asked.** Commit locally, let user review.
