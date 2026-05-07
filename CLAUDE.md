# Repo rules — smallest-ai-documentation

This file is loaded automatically at the start of every Claude Code session. The rules below are the **product of past mistakes** in this repo. Treat them as load-bearing.

---

## How to think about this codebase

There are TWO products documented here, and each has multiple **spec layers** plus **hand-written guides**. A change to a single param can require edits in 5–7 different files across spec, SDK overrides, docs render overrides, MDX guides, version mirrors, and a changelog entry. Missing any one of them ships a broken doc or a broken SDK.

Before touching any spec or guide, identify:

1. **Which product** — atoms or waves
2. **Which transport** — REST (openapi) or WS (asyncapi)
3. **What kind of change** — new endpoint, new param, param description tweak, enum change, error response change, removal, deprecation
4. **What's in scope per product** — see the per-product checklists below

---

## Spec layer map (the trap that's burnt us before)

```
                            ┌────────────────────────────┐
                            │  Hand-written MDX guides   │
                            │  fern/products/{atoms,waves}│
                            │  + version mirrors         │
                            └────────────┬───────────────┘
                                         │ describes
                          ┌──────────────┴──────────────┐
                          ▼                              ▼
                ┌──────────────────┐          ┌──────────────────┐
                │  ATOMS spec      │          │  WAVES spec      │
                └────────┬─────────┘          └────────┬─────────┘
                         │                             │
        ┌────────────────┴───────┐         ┌──────────┴────────────────────┐
        │                        │         │                               │
        ▼                        ▼         ▼                               ▼
   openapi/openapi.yaml   asyncapi/      openapi/<endpoint>.yaml    asyncapi/<endpoint>-ws.yaml
        +                  agent-ws.yaml         +                              +
   openapi-overrides.yaml      +              <endpoint>-overrides.yaml    <endpoint>-ws-overrides.yml
        +                  agent-ws-           (SDK gen)                  (SDK gen)
   ai_examples_override.yml  overrides.yaml         +                              +
                                            waves-v4/overrides/             waves-v4/overrides/
                                            <endpoint>-overrides.yaml      <endpoint>-ws-overrides.yml
                                            (v4 docs render)               (v4 docs render)
```

Atoms has 5 spec files. Waves has up to 6 per endpoint (base + SDK override + v4 docs override × REST/WS). **No product is "exempt"** — earlier versions of this file said atoms was exempt. That was wrong.

---

## Per-change checklist

Pick the section that matches your change. Run the steps in order. Skipping a step is what causes regressions.

### 🟢 Atoms — REST endpoint or param change

**Spec:**
- [ ] `fern/apis/atoms/openapi/openapi.yaml` — base spec (structure, types, descriptions)
- [ ] `fern/apis/atoms/openapi/openapi-overrides.yaml` — SDK + docs decoration (if change touches a field this file overrides)
- [ ] `fern/apis/atoms/openapi/ai_examples_override.yml` — AI-search examples (if adding/changing example values)

**Guides:**
- [ ] `fern/products/atoms/pages/dev/build/**` — feature guides referencing the param
- [ ] `fern/products/atoms/pages/dev/migrate/**` — comparison tables (e.g. ElevenLabs migration)
- [ ] `fern/products/atoms/pages/intro/reference/changelog-entries/{YYYY-MM-DD}-{slug}.mdx` — required for any spec-touching change

**Verify:**
- [ ] `fern check` — 0 errors
- [ ] `python3 scripts/spec-live-tests/spec_drift_check.py` — 0 drift
- [ ] **Live-test against `api.smallest.ai/atoms/v1`** — never document anything you haven't seen the platform actually accept
- [ ] Inspect the Fern preview URL for the affected endpoint page (don't trust spec validation alone)

### 🟢 Atoms — WebSocket endpoint or param change

**Spec:**
- [ ] `fern/apis/atoms/asyncapi/agent-ws.yaml` — base WS spec (the realtime agent endpoint at `WSS /atoms/v1/agent/connect`)
- [ ] `fern/apis/atoms/asyncapi/agent-ws-overrides.yaml` — decoration

**Guides — ALL FOUR mobile guides + the SDK doc consume this endpoint:**
- [ ] `fern/products/atoms/pages/dev/integrate/websocket-sdk.mdx`
- [ ] `fern/products/atoms/pages/dev/integrate/mobile/react-native.mdx`
- [ ] `fern/products/atoms/pages/dev/integrate/mobile/ios-swift.mdx`
- [ ] `fern/products/atoms/pages/dev/integrate/mobile/android-kotlin.mdx`
- [ ] `fern/products/atoms/pages/dev/integrate/mobile/flutter.mdx`
- [ ] `fern/products/atoms/pages/dev/migrate/from-elevenlabs.mdx` — comparison table cites the WS URL + message types
- [ ] `fern/products/atoms/pages/dev/cookbooks/examples.mdx` — Hearthside cookbook entry references the WS endpoint
- [ ] Changelog entry at `fern/products/atoms/pages/intro/reference/changelog-entries/{YYYY-MM-DD}-{slug}.mdx`

**Verify:**
- [ ] `fern check` — 0 errors
- [ ] `python3 scripts/spec-live-tests/spec_drift_check.py` — 0 drift
- [ ] Live-test the WS connection with each documented message type (`input_audio_buffer.append`, `output_audio.delta`, `agent_start_talking`, `agent_stop_talking`, `interruption`)
- [ ] Preview-check `/atoms/api-reference/api-reference/realtime-agent/realtime-agent` — confirm message types render

### 🟢 Waves — TTS (Lightning v3.1, v2) endpoint or param change

**Spec — REST (sync + SSE stream) — THREE layers:**
- [ ] `fern/apis/waves/openapi/lightning-v3.1-openapi.yaml` (or `waves-api.yaml` for v2) — base structure
- [ ] `fern/apis/waves/openapi/lightning-v3.1-openapi-overrides.yaml` — SDK gen (Python/JS/TS/Go) reads this
- [ ] `fern/apis/waves-v4/overrides/lightning-v3.1-openapi-overrides.yaml` — what renders on `docs.smallest.ai/waves` API ref

**Spec — WebSocket (streaming) — THREE layers:**
- [ ] `fern/apis/waves/asyncapi/lightning-v3.1-ws.yaml` — base WS structure
- [ ] `fern/apis/waves/asyncapi/lightning-v3.1-ws-overrides.yml` — SDK gen
- [ ] `fern/apis/waves-v4/overrides/lightning-v3.1-ws-overrides.yml` — v4 docs render

**Guides + version mirror:**
- [ ] `fern/products/waves/pages/v4.0.0/text-to-speech/{quickstart,how-to-tts,stream-tts,model-cards/lightning-v3-1}.mdx` — narrative + code samples
- [ ] `fern/products/waves/versions/v4.0.0/text-to-speech/...` — **version mirror must also be updated**
- [ ] `fern/products/waves/pages/v4.0.0/changelog-entries/{YYYY-MM-DD}-{slug}.mdx`

**Verify:**
- [ ] `fern check` — 0 errors
- [ ] `python3 scripts/spec-live-tests/spec_drift_check.py` — 0 drift across all 3 layers
- [ ] **Live-test each enum value** against `api.smallest.ai/waves/v1/lightning-v3.1/get_speech` — the platform's error message gives the canonical enum (`{"received": "X", "code": "invalid_enum_value", "options": [...]}`)
- [ ] Live-test the WS endpoint at `wss://api.smallest.ai/waves/v1/lightning-v3.1/get_speech/stream`
- [ ] Preview-check the Lightning v3.1 endpoint pages for visible param descriptions and enum lists

### 🟢 Waves — STT (Pulse) endpoint or param change

**Spec — REST (pre-recorded) — THREE layers:**
- [ ] `fern/apis/waves/openapi/pulse-stt-openapi.yaml`
- [ ] `fern/apis/waves/openapi/pulse-stt-openapi-overrides.yaml`
- [ ] `fern/apis/waves-v4/overrides/pulse-stt-openapi-overrides.yaml`

**Spec — WebSocket (realtime) — THREE layers:**
- [ ] `fern/apis/waves/asyncapi/pulse-stt-ws.yaml`
- [ ] `fern/apis/waves/asyncapi/pulse-stt-ws-overrides.yml`
- [ ] `fern/apis/waves-v4/overrides/pulse-stt-ws-overrides.yml` ← **Fern reads request param descriptions from `channels.pulseStream.parameters.*` IN THIS FILE, not from base**

**Guides + version mirror:**
- [ ] `fern/products/waves/pages/v4.0.0/speech-to-text/**` — overview, features, pre-recorded, realtime, model card, benchmarks
- [ ] `fern/products/waves/versions/v4.0.0/speech-to-text/**` — version mirror
- [ ] `fern/products/waves/pages/v4.0.0/changelog-entries/{YYYY-MM-DD}-{slug}.mdx`

**Verify:**
- [ ] `fern check` — 0 errors
- [ ] `python3 scripts/spec-live-tests/spec_drift_check.py` — 0 drift
- [ ] Live-test the Pulse REST endpoint with the demo WAV
- [ ] Live-test the Pulse WS endpoint at `wss://api.smallest.ai/waves/v1/pulse/get_text` with each documented param
- [ ] Preview-check the Pulse STT endpoint page

### 🟢 Cross-cutting changes (any product)

If your change touches any tab/section nav, frontmatter, links, redirects:
- [ ] `fern/products/{atoms,waves}.yml` — nav definitions
- [ ] `fern/docs.yml` — global config
- [ ] Frontmatter `description:` on every new/edited MDX (used in search)
- [ ] HEAD-verify every new internal link before commit (Fern slug rules: camelCase splits on case boundaries)

---

## CI surface

These run on every PR that touches `fern/apis/**` or related folders. Failures must be fixed, never bypassed:

| Check | What it does |
|---|---|
| `fern-check` | YAML structure validation |
| `Test Quickstart Code Samples` | runs every code sample in MDX against the live API |
| `Nav & Link Check` | broken internal links, orphan pages |
| `Changelog required for spec changes` | requires a changelog entry for any `fern/apis/**` PR |
| `API Spec Live Test / Atoms` | creates a real agent on the test tenant, PATCHes every documented `CreateAgentRequest` field, asserts diff endpoint reports it, archives. Also exercises `deleteAgent`. |
| `API Spec Live Test / Atoms WS` | opens `WSS /atoms/v1/agent/connect`, asserts `session.created` arrives + at least one of the documented server-pushed events (`agent_start_talking`, `output_audio.delta`, etc.) — flags any undocumented type. |
| `API Spec Live Test / Waves TTS` | Lightning v3.1 REST + WS smoke test |
| `API Spec Live Test / Waves STT` | Pulse WS streams the demo WAV, asserts non-empty transcript |
| `Waves spec drift` | base vs override drift across **all three** waves layers + atoms layers (auto-discovered) |
| `v4 docs mirror` | pages/v4.0.0 ↔ versions/v4.0.0 drift on PR-changed files |
| `preview-docs` | Fern preview build |

Run these locally before push:

```bash
fern check
python3 scripts/spec-live-tests/spec_drift_check.py
python3 scripts/spec-live-tests/v4_mirror_check.py        # PR-scoped vs origin/main
```

When changing a spec, also run the relevant live test (needs `SMALLEST_API_KEY` against the test tenant):

```bash
SMALLEST_API_KEY=... python3 scripts/spec-live-tests/atoms_live_test.py        # Atoms REST
SMALLEST_API_KEY=... python3 scripts/spec-live-tests/atoms_ws_live_test.py     # Atoms WS
SMALLEST_API_KEY=... python3 scripts/spec-live-tests/waves_tts_live_test.py    # Lightning v3.1 TTS
SMALLEST_API_KEY=... python3 scripts/spec-live-tests/waves_stt_live_test.py    # Pulse STT
```

---

## Ironclad rules (no exceptions)

1. **Always live-test API behavior** before documenting anything. `fern check` only validates YAML, not behavior. Past incidents: `numerals` flag was documented but Fern read it from a different layer and the change didn't render; `mulaw` was documented as a Lightning output_format but the API rejects it; `firstMessage` was assumed to round-trip but only verified after a live test caught it.
2. **Count BOTH `paths.*.<method>` AND `channels.*`** when auditing endpoint coverage. Atoms has 67 REST + 1 WS. Waves has 18 REST + 4 WS. Auditing only `openapi/` under-reports.
3. **No "soft-delete" or platform-internal vocabulary in customer-facing text.** When in doubt, ask. The deleteAgent endpoint description was reverted twice over this rule.
4. **Versions are frozen.** Never touch `fern/products/waves/versions/v2.2.0` or `v3.0.1`. v4.0.0 only.
5. **Both `pages/` and `versions/` mirrors must change together** when editing v4 content under `fern/products/waves/`. Mirror check fails the PR otherwise.
6. **Commits:** Conventional Commits format. Subject under 72 chars. No `Co-Authored-By: Claude`. No "Generated with Claude Code". No persona, no AI exposition, no rabbit-hole detail.
7. **Don't push to remote unless explicitly asked.** Commit locally, let user review.
8. **PR descriptions stay terse.** Customer-safe wording only — no source comparisons, no flagging/review asks, no "previously fabricated" framing.

---

## When something looks off, DO NOT GUESS — verify

- Spec layer mismatch → run `python3 scripts/spec-live-tests/spec_drift_check.py`
- Behavior question → call the live API
- Endpoint missing on docs → grep the sitemap, check `paths` AND `channels`
- Mirror question → `diff -rq fern/products/waves/pages/v4.0.0/ fern/products/waves/versions/v4.0.0/`
- Asyncapi WS spec is paired with channel parameters that override doesn't replicate to base → see "Pulse STT WS exception" note below

## Pulse STT WS exception — cross-structural-path drift

The v4 docs override for `pulse-stt-ws` puts param descriptions under `channels.pulseStream.parameters.<name>`. The base spec has them buried under `channels.pulseStream.messages.<msg>.payload.properties.<name>`. Fern's docs render reads from the override's `parameters` block. The drift check covers same-path drift; cross-structural-path drift is documented here as a known sharp edge — when adding/changing a Pulse STT WS param, **the override `parameters` block is the customer-visible source of truth**.
