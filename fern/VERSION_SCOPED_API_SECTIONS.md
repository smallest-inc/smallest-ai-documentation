# Version-scoped API sections

This document explains how to show or hide auto-generated API reference sections (like Pronunciation Dictionaries) on a per-version basis, even though all versions share the same underlying API specs.

## The mechanism: `x-fern-audiences` + `audiences` filter

All versions reference the same `waves` API definition via `api-name: waves` in their version config files. To control which endpoints appear per-version, we use Fern's **audiences** feature (Pro/Enterprise).

### How it works

1. **Tag version-specific endpoints** with `x-fern-audiences` in the OpenAPI/AsyncAPI override files:

```yaml
# In waves-api-overrides.yaml
paths:
  /api/v1/pronunciation-dicts:
    get:
      x-fern-audiences:
        - v4
      tags:
        - Pronunciation Dictionaries
```

2. **Set the `audiences` filter** on each version's `api:` section to its version identifier:

```yaml
# v4.0.0.yml
- api: API Reference
  api-name: waves
  audiences:
    - v4

# v3.0.1.yml
- api: API Reference
  api-name: waves
  audiences:
    - v3

# v2.2.0.yml
- api: API Reference
  api-name: waves
  audiences:
    - v2
```

### Filtering behavior

- Endpoints are **explicitly tagged** with the version audiences they belong to (e.g. `[v2, v3, v4]` for common endpoints, `[v4]` for v4-only).
- Each version config sets `audiences` to its own version identifier: v2.2.0 uses `[v2]`, v3.0.1 uses `[v3]`, v4.0.0 uses `[v4]`.
- An endpoint only appears in a version if the version's audience is listed in the endpoint's `x-fern-audiences`.
- If **no** `audiences` filter is set on the API section, nothing is filtered and all endpoints appear.

## What's currently tagged

### Common endpoints — `x-fern-audiences: [v2, v3, v4]`

**REST (OpenAPI overrides):**
- Lightning TTS (POST `/api/v1/lightning/get_speech`) - `waves-api-overrides.yaml`
- Lightning Large TTS (POST `/api/v1/lightning-large/get_speech`, POST `/api/v1/lightning-large/stream`) - `waves-api-overrides.yaml`
- Lightning v2 TTS (POST `/api/v1/lightning-v2/get_speech`, POST `/api/v1/lightning-v2/stream`) - `waves-api-overrides.yaml`
- Get Voices (GET `/api/v1/{model}/get_voices`) - `get-voices-openapi-overrides.yaml`
- Add Voice (POST `/api/v1/lightning-large/add_voice`) - `add-voice-openapi-overrides.yaml`
- Get Cloned Voices (GET `/api/v1/lightning-large/get_cloned_voices`) - `get-cloned-voices-openapi-overrides.yaml`
- Delete Voice Clone (DELETE `/api/v1/lightning-large`) - `delete-cloned-voice-openapi-overrides.yaml`

**WebSocket (AsyncAPI overrides):**
- Streaming TTS WebSocket (`/api/v1/streaming-tts/stream`) - `stream-tts-ws-overrides.yml`
- Lightning v2 WebSocket (`/api/v1/lightning-v2/get_speech/stream`) - `lightning-v2-ws-overrides.yml`

### v4-only endpoints — `x-fern-audiences: [v4]`

**REST (OpenAPI overrides):**
- Pronunciation Dictionaries (GET, POST, PUT, DELETE `/api/v1/pronunciation-dicts`) - `waves-api-overrides.yaml`
- Lightning v3.1 TTS (POST `/api/v1/lightning-v3.1/get_speech`, POST `/api/v1/lightning-v3.1/stream`) - `lightning-v3.1-openapi-overrides.yaml`
- ASR Speech-to-Text (POST `/api/v1/lightning/get_text`) - `asr-openapi-overrides.yaml`
- Pulse STT (POST `/api/v1/pulse/get_text`) - `pulse-stt-openapi-overrides.yaml`

**WebSocket (AsyncAPI overrides):**
- ASR WebSocket (`/api/v1/asr`) - `asr-ws-overrides.yml`
- Lightning ASR WebSocket (`/api/v1/lightning/get_text`) - `lightning-asr-ws-overrides.yml`
- Lightning v3.1 WebSocket (`/api/v1/lightning-v3.1/get_speech/stream`) - `lightning-v3.1-ws-overrides.yml`
- Pulse STT WebSocket (`/api/v1/pulse/get_text`) - `pulse-stt-ws-overrides.yml`

## General pattern for adding version-scoped sections

To add a new endpoint to specific versions:

1. Add `x-fern-audiences` with the list of version tags (e.g. `[v4]` or `[v2, v3, v4]`) in the override file
2. The endpoint will only appear in versions whose `audiences` config includes a matching tag

## Important: `layout` does NOT filter

The `layout` property under the `api:` block controls **ordering**, not visibility. Any subpackages not listed in the layout are appended at the end. To actually hide endpoints, you must use `x-fern-audiences` + `audiences`.

## Reference

- [Fern audiences docs](https://buildwithfern.com/learn/api-definitions/openapi/extensions/audiences)
- [Fern x-fern-ignore docs](https://buildwithfern.com/learn/api-definitions/openapi/extensions/ignoring-elements) (alternative: permanently hide endpoints from all versions)
