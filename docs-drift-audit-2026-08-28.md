# API Drift Audit — 2026-08-28

Comparison of `waves-platform` + `atoms-platform` backend routes against Fern-published spec.

## Compact summary

| Product | Backend endpoints | Documented | Delta | Highest-impact fix |
|---|---|---|---|---|
| **Waves** | ~95 | ~20 | **~75 undocumented** | Lightning-v3.2 model family (new prosody controls); 4 orphan specs |
| **Atoms** | ~240 | ~134 | ~106 delta (many intentionally internal) | Agent Optimization, widget entry points, WhatsApp/Roger integrations |

Real customer-visible drift on Atoms is likely 30-50 endpoints once admin/cron/webhook are excluded.

---

## Waves — quick wins (`fern/apis/waves/generators.yml`)

**4 spec files exist on disk but are not registered in `generators.yml`.** Adding them exposes ~15 endpoints with no schema work needed.

- [ ] Register `openapi/stt-openapi.yaml` (unified STT)
- [ ] Register `openapi/pca-openapi.yaml` (post-call analysis: `POST /pca/`, `POST /pca/generate`)
- [ ] Register `openapi/electron-openapi.yaml` (LLM `POST /chat/completions` — currently only mentioned in prose)
- [ ] Register `openapi/voice-catalog-openapi.yaml` (`GET /voice/get-all-models`)

## Waves — new endpoints requiring OpenAPI schema

### Lightning-v3.2 (entire model family missing)
- [ ] `POST /waves/v1/lightning-v3.2/get_speech` — sync TTS with `emotion`, `pitch`, `volume`, `prosody`, `accent`, free-form `instruction`
- [ ] `WSS /waves/v1/lightning-v3.2/stream` — streaming variant
- [ ] `GET /waves/v1/lightning-v3.2/get_voices` — voice list

Backend refs: `waves-platform/apps/main-backend/src/routes/speech/tts/lightning-v3/speech/lightning-v3.2.routes.ts:11-29`

New OpenAPI file: `openapi/lightning-v3.2-openapi.yaml` (this PR includes the fragment)

### Voice cloning — browser flow + preprocessing flags
- [ ] `POST /waves/v1/voice-cloning/upload-audio` (jwt, multipart, ≤5 MB)
- [ ] `POST /waves/v1/voice-cloning/create` (jwt)
- [ ] `GET /waves/v1/voice-cloning/:id` (jwt, clone status polling)
- [ ] `GET /waves/v1/voice-cloning/models` (jwt)
- [ ] `POST /waves/v1/voice-cloning/delete` (jwt)
- [ ] Extend existing `POST /waves/v1/voice-cloning` schema with preprocessing flags `skip_superresolution`, `skip_denoise`, `skip_normalize`, `skip_vad`

Backend refs: `waves-platform/apps/main-backend/src/routes/speech/tts/voice-clone/voice-clone.route.ts:17-26`

### Projects — entire resource undocumented
- [ ] 13 endpoints under `/waves/v1/projects/*`: CRUD, chapters, blocks, voice-settings, exports, downloads, PATCH, cancel, `text_to_speech/:id`

Backend refs: `waves-platform/apps/main-backend/src/routes/projects/projects.route.ts:28-57`

New OpenAPI file: `openapi/projects-openapi.yaml` (this PR includes the fragment)

### Voice library actions
- [ ] `POST /waves/v1/voice/:voiceId/save` + `DELETE`
- [ ] `POST /waves/v1/voice/:voiceId/upvote` + `DELETE`

Backend refs: `waves-platform/apps/main-backend/src/routes/voice/voice.route.ts:18-22`

### S2S Analytics
- [ ] `GET /waves/v1/analytics/s2s/usage/timeseries`
- [ ] `GET /waves/v1/analytics/s2s/logs`

Backend refs: `waves-platform/apps/main-backend/src/routes/analytics/s2s/s2s.analytics.route.ts:8-9`

### Small deltas on already-documented resources
- [ ] `DELETE /waves/v1/pronunciation-dicts/` — missing from spec (spec has GET/POST/PUT only)
- [ ] `DELETE /waves/v1/analytics/asr/history` — bulk-delete variant missing (single-record variant IS documented)
- [ ] `POST /waves/v1/tts/live` — control frames missing from AsyncAPI (`flush`, `continue`, `cancel_request`)
- [ ] `GET /waves/v1/chat/health` — LLM health check missing

### Path prefix drift — needs product decision
Docs use `/waves/v1/*`; backend mounts at `/api/v1/*`. If the public gateway rewrites the prefix, everything is fine. **Please confirm** — if it doesn't rewrite, every `waves/v1/*` documented path is wrong. (Owner: gateway / platform team.)

---

## Atoms — categorical drift (needs per-endpoint pass to finalize)

A second Explore agent is currently generating the per-endpoint list. Categories where drift is confirmed:

- [ ] **Agent Optimization** — AI chat-based tuning with accepted/discarded changes (`apps/main-backend/src/routes/agent-optimization/*`); no doc coverage
- [ ] **Widget entry points** — public chat + web-call, distinct from `/conversation/webcall`; not documented
- [ ] **Roger integration** — MS Teams/Zoom deployment; not documented (confirm whether customer-facing)
- [ ] **WhatsApp dispatch** — main-backend has message/call dispatch + SIP trunk registration; docs cover WhatsApp only via console-backend
- [ ] **Console-backend public** — likely 15-25 customer-visible endpoints undocumented (API keys, invitations, coupons, subscription details)
- [ ] **payment-service** — undocumented: payment methods list/add/delete, auto-reload, billing alerts, entitlements, preferences

### Confirmed excluded from doc scope (leave undocumented)
- All health probes (`/health*`)
- Provider webhooks (`/conversation/inbound*`, `/whatsapp/webhook`, `/payment/v1/webhooks`)
- Cron endpoints (`/campaign/cron`, `/phone-billing/*`, `/admin/kb-storage-billing/*`)
- Internal service-to-service (`/api/v1/internal/*`, admin routes with `X-Admin-API-Key`)

---

## Long-term fix — spec in code
See companion PR on backend repos: `chore/openapi-in-code-scaffold-2026-08-28`. Once backend routes emit OpenAPI from their Zod schemas + a CI bot opens PRs into this repo, this drift will be a nightly diff instead of a quarterly audit.
