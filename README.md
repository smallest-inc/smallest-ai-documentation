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
    <img src="https://dcbadge.vercel.app/api/server/ywShEyXHBW?style=flat" alt="Discord">
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

### Voice Agents (Atoms) Content

| What to change | Where |
|---|---|
| Platform docs (UI guides, agent config, testing) | `fern/products/atoms/pages/platform/` |
| Developer guide (API usage, building agents, SDK) | `fern/products/atoms/pages/dev/` |
| Product overview (intro, capabilities, telephony) | `fern/products/atoms/pages/intro/` |
| Deep-dive reference (voice config, LLM, webhooks) | `fern/products/atoms/pages/deep-dive/` |
| API reference spec | `fern/apis/atoms/openapi/openapi.yaml` |
| Navigation & tabs | `fern/products/atoms.yml` |
| Images | `fern/products/atoms/pages/images/` |

### Models (Waves) Content

| What to change | Where |
|---|---|
| Text-to-Speech (Lightning) docs | `fern/products/waves/pages/v4.0.0/text-to-speech/` |
| Speech-to-Text (Pulse) docs | `fern/products/waves/pages/v4.0.0/speech-to-text/` |
| Getting started, auth, quickstart | `fern/products/waves/pages/v4.0.0/getting-started/` |
| Voice cloning | `fern/products/waves/pages/v4.0.0/voice-cloning/` |
| Integrations (Vercel AI SDK, etc.) | `fern/products/waves/pages/v4.0.0/integrations/` |
| Best practices | `fern/products/waves/pages/v4.0.0/best-practices/` |
| Model cards (TTS / STT) | `fern/products/waves/pages/v4.0.0/text-to-speech/model-cards/` and `speech-to-text/model-cards/` |
| On-prem deployment | `fern/products/waves/pages/v4.0.0/on-prem/` |
| API reference overrides (docs display) | `fern/apis/waves-v4/overrides/` |
| OpenAPI / AsyncAPI specs (SDK generation) | `fern/apis/waves/openapi/` and `fern/apis/waves/asyncapi/` |
| Navigation & versions | `fern/products/waves/versions/v4.0.0.yml` |
| Images | `fern/products/waves/pages/v4.0.0/images/` |

### Global / Shared

| What to change | Where |
|---|---|
| Site theme, colors, logo, layout | `fern/docs.yml` |
| Custom CSS | `fern/docs/assets/styles/global-styling.css` |
| Favicon, logos | `fern/docs/assets/` |
| Shared MDX snippets | `fern/snippets/` |

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
| [podcast-generator](https://github.com/smallest-inc/podcast-generator) | AI Podcast Generator (Smallest Cast) |

## Support

- **Documentation**: [docs.smallest.ai](https://docs.smallest.ai)
- **Discord**: [Join our community](https://discord.gg/ywShEyXHBW)
- **Email**: [support@smallest.ai](mailto:support@smallest.ai)
- **Issues**: [Open an issue](https://github.com/smallest-inc/smallest-ai-documentation/issues)
