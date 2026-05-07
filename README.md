<br/>
<div align="center">

  <a href="https://smallest.ai">
    <img src="fern/docs/assets/logo_dark.png" alt="Smallest AI" height="50">
  </a>

  <h1>Smallest AI Documentation</h1>

  <p>Source for <a href="https://docs.smallest.ai"><strong>docs.smallest.ai</strong></a> — the unified documentation site for Smallest AI's Voice Agents (Atoms) and Models (Waves) products.</p>

  <a href="https://docs.smallest.ai">
    <img src="https://img.shields.io/badge/Docs-docs.smallest.ai-2A9D8F?style=for-the-badge&logo=readthedocs&logoColor=white" alt="Documentation">
  </a>
  <a href="https://github.com/smallest-inc/smallest-python">
    <img src="https://img.shields.io/badge/Python%20SDK-smallest--python-blue?style=for-the-badge&logo=python&logoColor=white" alt="Python SDK">
  </a>
  <a href="https://github.com/smallest-inc/smallest-js">
    <img src="https://img.shields.io/badge/JS%20SDK-smallest--js-yellow?style=for-the-badge&logo=javascript&logoColor=white" alt="JavaScript SDK">
  </a>
  <a href="https://discord.gg/ywShEyXHBW">
    <img src="https://img.shields.io/badge/Discord-Join%20Community-5865F2?style=for-the-badge&logo=discord&logoColor=white" alt="Discord">
  </a>
  <a href="https://twitter.com/smallest_AI">
    <img src="https://img.shields.io/twitter/url/https/twitter.com/smallest_AI.svg?style=social&label=Follow%20smallest_AI" alt="Twitter">
  </a>
  <a href="https://www.linkedin.com/company/smallest">
    <img src="https://img.shields.io/badge/LinkedIn-Connect-blue" alt="LinkedIn">
  </a>
  <a href="https://www.youtube.com/@smallest_ai">
    <img src="https://img.shields.io/static/v1?message=smallest_ai&logo=youtube&label=&color=FF0000&logoColor=white&labelColor=&style=for-the-badge" height=20 alt="YouTube">
  </a>

</div>

---

## About

This repository contains the source files for the Smallest AI documentation site at [docs.smallest.ai](https://docs.smallest.ai). The docs are built with [Fern](https://buildwithfern.com) and cover two products:

| Product | Display Name | Description | Docs URL |
|---|---|---|---|
| **Atoms** | Voice Agents | End-to-end voice AI agents for telephony, web, and mobile | [docs.smallest.ai/atoms](https://docs.smallest.ai/atoms) |
| **Waves** | Models | Text-to-Speech (Lightning) and Speech-to-Text (Pulse) APIs | [docs.smallest.ai/waves](https://docs.smallest.ai/waves) |

## Repository Structure

```
.
├── fern/
│   ├── docs.yml                          # Main docs config (products, theme, layout)
│   ├── fern.config.json                  # Fern org + version
│   ├── docs/
│   │   ├── assets/                       # Logos, favicon, CSS, images, videos
│   │   └── changelog/                    # Changelog entries
│   ├── apis/
│   │   ├── atoms/openapi/                # Atoms (Voice Agents) OpenAPI spec
│   │   ├── waves/                        # Waves OpenAPI + AsyncAPI specs (SDK generation)
│   │   ├── waves-v4/overrides/           # Waves v4 API reference overrides (docs rendering)
│   │   └── unified/                      # Unified SDK generator config
│   ├── products/
│   │   ├── atoms.yml                     # Voice Agents navigation config
│   │   ├── atoms/pages/                  # Voice Agents documentation pages (MDX)
│   │   ├── waves/versions/               # Models version configs (v4.0.0, v3.0.1, v2.2.0)
│   │   └── waves/pages/                  # Models documentation pages (MDX)
│   └── snippets/                         # Shared MDX snippets
├── .github/workflows/
│   ├── publish-docs.yml                  # Auto-publish on push to main
│   ├── preview-docs.yml                  # PR preview URLs
│   ├── python-sdk.yml                    # Python SDK generation
│   ├── ts-sdk.yml                        # TypeScript SDK generation
│   ├── go-sdk.yml                        # Go SDK generation
│   └── test-quickstarts.yml              # Quickstart code sample tests
└── README.md
```

## Which Files to Edit

### Models (Waves)

| What you're changing | Where to edit |
|---|---|
| Waves docs content (pages, guides) | `fern/products/waves/pages/v4.0.0/*.mdx` |
| Waves sidebar navigation | `fern/products/waves/versions/v4.0.0.yml` |
| Waves API spec (REST/HTTP endpoints) | `fern/apis/waves/openapi/*.yaml` |
| Waves API spec (WebSocket endpoints) | `fern/apis/waves/asyncapi/*.yaml` |
| Waves API ref page rendering (what shows on docs site) | `fern/apis/waves-v4/overrides/*.yml` |
| Waves images | `fern/products/waves/pages/v4.0.0/images/` |

### Voice Agents (Atoms)

| What you're changing | Where to edit |
|---|---|
| Atoms docs content | `fern/products/atoms/pages/**/*.mdx` |
| Atoms sidebar navigation | `fern/products/atoms.yml` |
| Atoms API spec | `fern/apis/atoms/openapi/openapi.yaml` |
| Atoms images | `fern/products/atoms/pages/images/` |

### Global

| What you're changing | Where to edit |
|---|---|
| Product toggle, global config | `fern/docs.yml` |
| CSS / styling | `fern/docs/assets/styles/global-styling.css` |
| Logos, favicon | `fern/docs/assets/` |
| Shared MDX snippets | `fern/snippets/` |

> **Important — three spec layers for waves**:
> 1. **Base spec** at `fern/apis/waves/{openapi,asyncapi}/*.yaml` — source of truth for structure.
> 2. **SDK overrides** at `fern/apis/waves/{openapi,asyncapi}/*-overrides.yaml` (siblings of base) — drive SDK method names, examples, and deprecations via `fern/apis/unified/generators.yml`.
> 3. **v4 docs overrides** at `fern/apis/waves-v4/overrides/*.yaml` — drive what renders on the `docs.smallest.ai/waves` API reference pages via `fern/apis/waves-v4/generators.yml`.
>
> A `description`, `default`, `enum`, or `example` set in the v4 docs override **wins** on docs render. Editing the same field in the base spec alone is invisible. Always update both layers in lockstep, and run `python3 scripts/spec-live-tests/spec_drift_check.py` before pushing — CI runs it on every PR that touches `fern/apis/waves/**` or `fern/apis/waves-v4/overrides/**`.
>
> **Atoms has its own base + override pairs** (REST under `fern/apis/atoms/openapi/` and WS under `fern/apis/atoms/asyncapi/`). The atoms WebSocket endpoint at `WSS /atoms/v1/agent/connect` lives in `agent-ws.yaml` and renders at `/atoms/api-reference/api-reference/realtime-agent/realtime-agent` — easy to miss if you only audit `openapi/`. The drift check script auto-discovers all atoms and waves layers.

## Setup

### Prerequisites

- **Node.js** 18+
- **npm** or **yarn**
- A Fern account and `FERN_TOKEN` (for publishing)

### Install Fern CLI

```bash
npm install -g fern-api
```

### Local Development

Preview the docs locally with hot-reload:

```bash
fern docs dev
```

This starts a local server at `http://localhost:3000` with live reloading as you edit MDX and config files.

### Preview a Build

Generate a preview URL (useful for PR reviews):

```bash
fern generate --docs --preview
```

### Publish to Production

Publishing happens automatically when changes are merged to `main` via the `publish-docs.yml` GitHub Action. To publish manually:

```bash
FERN_TOKEN=<your-token> fern generate --docs
```

### Upgrade Fern Version

```bash
fern upgrade
```

Then update the version in `fern/fern.config.json` if needed.

## Contributing

We welcome contributions from the community! Here's how to get started:

### 1. Fork & Clone

```bash
git clone https://github.com/smallest-inc/smallest-ai-documentation.git
cd smallest-ai-documentation
npm install -g fern-api
```

### 2. Create a Branch

```bash
git checkout -b docs/your-change-description
```

### 3. Make Your Changes

- **Content changes**: Edit MDX files in the relevant `pages/` directory (see [Which Files to Edit](#which-files-to-edit))
- **Navigation changes**: Edit the YAML config (`atoms.yml` or `waves/versions/v4.0.0.yml`)
- **API spec changes**: Edit OpenAPI/AsyncAPI files in `fern/apis/`
- **Style changes**: Edit `fern/docs.yml` or `fern/docs/assets/styles/global-styling.css`

### 4. Preview Locally

```bash
fern docs dev
```

Verify your changes look correct at `http://localhost:3000`.

### 5. Submit a Pull Request

Push your branch and open a PR against `main`. A preview URL will be automatically generated and posted as a PR comment.

### Guidelines

- All content pages use **MDX** format (Markdown + JSX components)
- Follow existing naming conventions for file and folder names
- Keep images in the `images/` directory next to the pages that use them
- Use [Fern's component library](https://buildwithfern.com/learn/docs/content/components/overview) for callouts, cards, tabs, etc.
- Test that internal links work by previewing locally before submitting

## Related Repositories

| Repository | Description |
|---|---|
| [smallest-python](https://github.com/smallest-inc/smallest-python) | Official Python SDK |
| [smallest-js](https://github.com/smallest-inc/smallest-js) | Official JavaScript/TypeScript SDK |
| [cookbook](https://github.com/smallest-inc/cookbook) | Examples and guides for using Smallest AI |

## Support

- **Documentation**: [docs.smallest.ai](https://docs.smallest.ai)
- **Discord**: [Join our community](https://discord.gg/ywShEyXHBW)
- **Email**: [support@smallest.ai](mailto:support@smallest.ai)
- **Issues**: [Open an issue](https://github.com/smallest-inc/smallest-ai-documentation/issues)
