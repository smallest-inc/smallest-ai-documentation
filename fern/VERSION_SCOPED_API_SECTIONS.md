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

2. **Set the `audiences` filter** on each version's `api:` section to control which tagged endpoints appear:

```yaml
# v4.0.0.yml - includes v4-tagged endpoints
- api: API Reference
  api-name: waves
  audiences:
    - base
    - v4

# v2.2.0.yml - excludes v4-tagged endpoints
- api: API Reference
  api-name: waves
  audiences:
    - base
```

### Filtering behavior

- Endpoints **without** `x-fern-audiences` are always included regardless of the `audiences` filter (they are audience-agnostic).
- Endpoints **with** `x-fern-audiences: [v4]` only appear when the version config's `audiences` list includes `v4`.
- If **no** `audiences` filter is set on the API section, nothing is filtered and all endpoints appear.

The `base` audience is a placeholder that activates filtering. Since no endpoints are tagged `base`, its only purpose is to ensure the filter is active so that v4-tagged endpoints are excluded.

## What's currently tagged

The following endpoints are tagged `x-fern-audiences: [v4]` (v4-only):

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

To hide a new API section from older versions:

1. Add `x-fern-audiences: [v4]` to the endpoint(s) in their override file
2. Ensure the version configs that should show it include `v4` in their `audiences` list
3. Ensure the version configs that should hide it do NOT include `v4` in their `audiences` list

## Important: `layout` does NOT filter

The `layout` property under the `api:` block controls **ordering**, not visibility. Any subpackages not listed in the layout are appended at the end. To actually hide endpoints, you must use `x-fern-audiences` + `audiences`.

## Reference

- [Fern audiences docs](https://buildwithfern.com/learn/api-definitions/openapi/extensions/audiences)
- [Fern x-fern-ignore docs](https://buildwithfern.com/learn/api-definitions/openapi/extensions/ignoring-elements) (alternative: permanently hide endpoints from all versions)
