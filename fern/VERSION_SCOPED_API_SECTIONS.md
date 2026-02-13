# Version-scoped API sections

This document explains how to show or hide auto-generated API reference sections (like Pronunciation Dictionaries) on a per-version basis, even though all versions share the same underlying API specs.

## The mechanism: `layout` as a strict filter

All versions reference the same `waves` API definition via `api-name: waves` in their version config files. However, each version config has its own `layout` property under the `api:` block. When `flattened: true` is set, this layout acts as a **strict filter**: only the subpackages explicitly listed in the layout will appear in the sidebar. Any subpackages that exist in the API spec but are omitted from the layout are hidden for that version.

## How it works for Pronunciation Dictionaries

The Pronunciation Dictionaries endpoints exist in the shared API spec (`waves-api.yaml` + overrides) and are tagged with the "Pronunciation Dictionaries" tag. This tag creates a subpackage in the auto-generated API reference.

**v4.0.0** includes it in its layout:

```yaml
# fern/products/waves/versions/v4.0.0.yml
- api: API Reference
  api-name: waves
  flattened: true
  layout:
    - Text to Speech:
        title: Text to Speech
    - Speech to Text:
        title: Speech to Text
    - Voices:
        title: Voices
    - Voice Cloning:
        title: Voice Cloning
    - Pronunciation Dictionaries:
        title: Pronunciation Dictionaries
```

**v2.2.0** and **v3.0.1** omit it from their layouts:

```yaml
# fern/products/waves/versions/v2.2.0.yml
- api: API Reference
  api-name: waves
  flattened: true
  layout:
    - Lightning v2:
        title: Lightning v2
    - Lightning Large:
        title: Lightning Large
    - Lightning:
        title: Lightning
    - Voices:
        title: Voices
    - Voice Cloning:
        title: Voice Cloning
```

Because the layout is a strict filter, Pronunciation Dictionaries endpoints are hidden in v2.2.0 and v3.0.1 even though the endpoints exist in the shared API spec.

## General pattern for version-scoping

To show a section in one version but not another:

1. Ensure the endpoints are tagged with a distinct tag in the OpenAPI spec/overrides
2. Add that tag to the `layout` list in the version configs where it should appear
3. Omit it from the `layout` list in version configs where it should be hidden

No changes to the API spec, audiences, or separate API definitions are needed. The version-specific `layout` property is the sole control.

## Key constraint

All versions share the same API spec files in `fern/apis/waves/`. You cannot add or remove endpoints per-version at the spec level. The `layout` in each version config is the only per-version control over which auto-generated sections appear.
