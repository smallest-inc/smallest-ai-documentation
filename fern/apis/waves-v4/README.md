# `waves-v4` — docs-only API definition

This folder holds the **docs-render overrides** for the waves API surface. It is **not** a SDK generation target — SDK generation for waves runs out of [`fern/apis/unified/generators.yml`](../unified/generators.yml).

## What goes here

- `generators.yml` — registers every waves base spec from `fern/apis/waves/` and pairs it with a v4 docs-render override under `overrides/`.
- `overrides/*.yaml` — per-spec docs decoration (titles, audience filters, hand-written examples, deprecation flags, etc.) that ships only to v4 docs.

## ⚠ Server URL gotcha — read before adding a new model/endpoint

**Do not add an `environments:` / `default-environment:` / `default-url:` block to `generators.yml` here.** The waves SDK env config already lives in `fern/apis/unified/generators.yml` — duplicating it in this file forces Fern's docs renderer onto a named-environment code path that fails to resolve and falls back to a synthetic `https://host.com` placeholder on every waves API reference page.

The symptom is subtle: every auto-generated code snippet (cURL, Swift, Java, …) on every waves endpoint page advertises `https://host.com/waves/v1/...` to customers. Hand-written examples in each spec's `description:` field disguise the bug visually, but the bug is still there — and a new endpoint without hand-written examples (e.g. when you first add it) shows the bug nakedly.

### Required base-spec shape

Every waves OpenAPI base spec under `fern/apis/waves/openapi/` must have:

```yaml
servers:
- url: https://api.smallest.ai
  description: Waves API server
  x-fern-server-name: waves          # ← REQUIRED, do not omit
```

Every waves AsyncAPI base spec under `fern/apis/waves/asyncapi/` must have:

```yaml
servers:
  production:
    host: api.smallest.ai
    pathname: /waves/v1/...
    protocol: wss
    x-fern-server-name: waves-ws     # ← REQUIRED (or `waves` for REST-over-WS)
```

### Verification before merging a new spec

1. Run `fern docs dev` locally (or open the PR's Fern preview URL).
2. Open the new endpoint's API reference page in a browser.
3. View source / inspect — grep for `host.com`. It must be **0 hits**.
4. Confirm the rendered `environments` JSON shows `{"id":"waves","baseUrl":"https://api.smallest.ai"}`, not `{"id":"Default","baseUrl":"https://host.com"}`.

If you find `host.com` in the rendered HTML, the most likely cause is one of:
- You added the new spec to `generators.yml` but forgot `x-fern-server-name: waves` in the base spec's `servers:` block.
- Someone re-introduced an `environments:` block to `generators.yml` in this folder.

### History

- PR #175 — root-cause fix (commit `e7cf412`): dropped the duplicate `environments:` block + added `x-fern-server-name: waves` to every waves base spec.
- The duplicate block was introduced before this folder existed as a docs-only target; once SDK gen moved to `fern/apis/unified/generators.yml`, the duplicate became actively harmful.
