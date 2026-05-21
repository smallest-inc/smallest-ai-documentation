# Electron Docs Drop — Reference for DevRel

This directory contains a complete reference draft of the Electron (LLM) documentation, ready for DevRel review, edit, and publish.

## What's here

### New pages (Tab: Documentation → "LLM (Electron)" section)
1. `quickstart.mdx` — OpenAI SDK in 5 lines + base URL swap
2. `overview.mdx` — what Electron is, key features, pricing, plan limits, use cases
3. `chat-completions.mdx` — core API reference (request/response shape, all parameters, error codes)
4. `streaming.mdx` — SSE format, consuming the stream, final usage chunk, disconnect behavior
5. `tool-calling.mdx` — standard OpenAI tools + the voice-agent filler-phrase pattern
6. `prefix-caching.mdx` — how caching works, how to structure prompts, cost math
7. `supported-parameters.mdx` — passthrough table, rejected parameters, schema limits
8. `migrate-from-openai.mdx` — side-by-side diff, common migration questions
9. `best-practices.mdx` — opinionated guide: caching, streaming, tool calls, error handling, cost control

### New model card (Tab: Model Cards → "LLM" section)
- `model-cards/electron.mdx`

### New cookbook (Tab: Documentation → existing "Cookbooks" section)
- `../cookbooks/voice-agent-electron-pulse-lightning.mdx` — wires Pulse + Electron + Lightning

### Updated files (already edited)
- `../getting-started/models.mdx` — added Electron card + LLM model overview table
- `../../versions/v4.0.0.yml` — added nav entries to all three tabs (Documentation, API Reference, Model Cards) + cookbook
- `../../../docs.yml` — added Electron to AI-search system prompt + synonym map

### Reference snippet (not auto-loaded by Fern)
- `_openapi-snippet.yaml` — drop into the live OpenAPI spec under `fern/apis/waves-v4/openapi/<spec-file>`. Once merged, the API Reference page renders automatically (nav entry already added).

## How to use this drop

Read each MDX and:
- Adjust tone / examples to your house style
- Replace anything wrong with the actual product behavior
- Drop any sections you don't want
- Add screenshots / videos where helpful

All copy is meant as a starting point — treat it as a first draft.

## Verified facts at time of writing

(Captured during Electron's first prod launch to anchor the docs to current product behavior. DevRel should re-verify before publishing.)

- Endpoint: `POST https://api.smallest.ai/waves/v1/chat/completions`
- Model ID in body: `"electron"`
- Context window: 32,768 tokens combined input + output
- TTFT: < 300 ms warm
- Pricing: $0.40/M input, $0.10/M cached input, $1.60/M output
- Plan limits: Standard 10 RPM / 3 concurrent; Enterprise 200 RPM / 20 concurrent
- 70 languages (full list in `model-cards/electron.mdx#supported-languages`)
- Tool calling: standard OpenAI shape, with voice-agent filler in `content` alongside `tool_calls`
- Prefix caching: automatic, reported as `usage.prompt_tokens_details.cached_tokens`
- Rejected params: `n > 1`, `prompt_logprobs`

## Out of scope (not in this drop)

- PCA (Post-Call Analytics) docs — separate product, separate pass
- On-prem / self-hosting for Electron — roadmap, not GA
- Multi-region info — roadmap, not GA
- Public benchmark scores — research team to publish separately
- Versioning info (Electron v2 etc.) — none yet
