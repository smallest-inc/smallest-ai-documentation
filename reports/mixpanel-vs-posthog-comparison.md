# Mixpanel vs PostHog — Comparison Report for Smallest AI

**Date:** 2026-04-14 
**Prepared by:** Velocity Sentinel (Sauron Bot) 
**Method:** Codebase analysis across 6+ repos in `smallest-inc` GitHub org

---

## Table of Contents

1. [Current State at Smallest AI](#1-current-state-at-smallest-ai)
2. [Feature Comparison](#2-feature-comparison)
3. [What's Best for Smallest AI](#3-whats-best-for-smallest-ai)
4. [TL;DR Scorecard](#4-tldr-scorecard)

---

## 1. Current State at Smallest AI

Mixpanel is **deeply embedded** across **6 repos and 7 surfaces**:

| Repo | Surface | SDK Used |
|------|---------|----------|
| `atoms-platform` | Atoms frontend | `mixpanel-browser` |
| `atoms-platform` | `main-backend` | `mixpanel` (Node SDK) |
| `atoms-platform` | `console-backend` | `mixpanel` (Node SDK) |
| `smallest-console` | Unified console frontend | `mixpanel-browser` |
| `waves-platform` | TTS dashboard frontend | `mixpanel-browser` |
| `smallest-platform` | Marketing/landing page | `mixpanel-browser` |
| `smallest-ai-documentation` | Docs site | `mixpanel-browser` + **PostHog** (dual-send) |
| `miniflow-desktop` | macOS Swift app | Mixpanel Swift SDK |
| `devrel-reports-bot` | Slack bot (automated reports) | Mixpanel Export API |

### Events Tracked (60+ distinct events)

| Category | Key Events |
|----------|------------|
| **Auth** | Login Page Viewed, OTP Send, Google Login, Invitation Accept |
| **Onboarding** | Onboarding Started, Step Completed, Onboarding Completed |
| **Agent CRUD** | Agent Created, Configured, Deleted, Field Updated, Name Updated |
| **Agent Testing** | Test Call Initiated, Web Call Connected/Ended, Chat Connected/Ended |
| **Voice Cloning** | Voice Clone Created, Audio Uploaded, Pro Voice Clone Submission |
| **TTS** | Audio Generated (with model, voice, language, speed metadata) |
| **Campaigns** | Campaign Created, Started, Paused, Deleted, Logs Exported |
| **Audience** | CSV Parsed, Form Submitted, Template Downloaded |
| **Payments** | Payment Successful, Upgrade Modal Click |
| **Navigation** | Sidebar clicks, Platform Switched, Org Switched |
| **Docs** | Page Viewed, Code Copied, Search, Scroll Depth, CTA Clicks, SDK Install Copied |

### Features Actively Used

- **Session replay** at 100% recording rate (`atoms-platform/providers.tsx`)
- **UTM tracking & attribution** (captured and stored in sessionStorage)
- **User identification** by email (via `mixpanel.identify`)
- **Cross-domain cookie persistence** on `.smallest.ai` domain
- **Conversion funnels** (Onboarding → API Key → Audio Generation)
- **Geographic breakdown** (country tracking via `mp_country_code`)
- **Mixpanel Export API** used by `devrel-reports-bot` for automated weekly Slack reports

### PostHog Usage Today

PostHog is **only** on `docs.smallest.ai` via Fern's native integration — **not in any product surface**. The docs analytics script (`analytics.js`) dual-sends to both Mixpanel and PostHog.

---

## 2. Feature Comparison

### Core Analytics

| Capability | Mixpanel | PostHog |
|------------|----------|---------|
| Event tracking | Best-in-class, purpose-built | Good, on par |
| Funnels | Excellent — flexible, real-time | Good — slightly less polished UI |
| Retention analysis | Excellent | Good |
| User cohorts | Excellent | Good |
| Group analytics (org-level) | Yes (paid) | Yes (paid) |
| SQL access to raw data | No (export API only) | Yes — built-in SQL (HogQL) |
| Real-time dashboards | Near real-time | Real-time |

### Session Replay

| Capability | Mixpanel | PostHog |
|------------|----------|---------|
| Session replay | Added recently (100% in your config) | Mature, core feature |
| Network tab recording | Limited | Full request/response inspection |
| Console log capture | No | Yes |
| Replay linked to events | Basic | Deep — click on event → see exact session |
| Mobile session replay | No | iOS/Android support |

### Feature Flags & Experiments

| Capability | Mixpanel | PostHog |
|------------|----------|---------|
| Feature flags | ❌ No | ✅ Yes — first-party, built-in |
| A/B testing | Experiments add-on | Built-in, tight analytics integration |
| Server-side flags | ❌ No | ✅ Yes (multi-language SDKs) |
| Targeting by property | N/A | ✅ Yes — user/group properties |

### Data & Privacy

| Capability | Mixpanel | PostHog |
|------------|----------|---------|
| Self-hosting option | ❌ No — SaaS only | ✅ Yes — full self-host on your infra |
| EU data residency | Yes | Yes (Cloud EU or self-host) |
| Data warehouse export | BigQuery/S3 (paid) | Built-in data warehouse, plus S3/BigQuery |
| Raw data access | Export API (limited) | Full SQL access (HogQL), direct ClickHouse |
| GDPR compliance tools | Good | Excellent — self-host = full control |

### Developer Experience

| Capability | Mixpanel | PostHog |
|------------|----------|---------|
| SDKs | JS, Node, Python, Swift, etc. | JS, Node, Python, Go, Ruby, Swift, etc. |
| Autocapture | ❌ No — manual instrumentation only | ✅ Yes — auto-tracks clicks, pageviews, inputs |
| API quality | Good but older | Modern REST + HogQL |
| Docs quality | Excellent | Excellent |
| Open source | ❌ No | ✅ Yes — MIT licensed |

### Pricing (as of 2026)

| Tier | Mixpanel | PostHog |
|------|----------|---------|
| Free tier | 20M events/mo | 1M events/mo + 5K sessions/mo |
| Paid | ~$0.00028/event at scale | ~$0.00031/event + replays, flags priced separately |
| Session replay | Included in Growth plan | $0.005/session after 5K free |
| Feature flags | Not available | 1M requests free, then $0.0001/request |
| Self-host | Not possible | Free (MIT) — you pay infra only |

### Integrations

| Tool | Mixpanel | PostHog |
|------|----------|---------|
| Slack | Yes | Yes |
| Webhook alerts | Limited | Yes — actions framework |
| Data warehouse | BigQuery, Snowflake export | Built-in warehouse + external sync |
| CRM (HubSpot, etc.) | Via CDP | Direct integration |
| Reverse ETL | Needs Segment/Census | Built-in (batch exports, webhooks) |

---

## 3. What's Best for Smallest AI

### Recommendation: Stay with Mixpanel for now. Evaluate PostHog migration in 6-12 months.

### Why Mixpanel Wins TODAY

1. **Migration cost is too high right now.** 60+ events across 6 repos, 3 backends (`atoms`, `console-backend`, `main-backend`), a Swift macOS app, and an automated reporting bot (`devrel-reports-bot`) all depend on Mixpanel. This is a multi-sprint effort to migrate.

2. **Session replay at 100%** is already configured and working in `atoms-platform/providers.tsx`. Moving to PostHog replay means re-instrumenting and losing historical replay data.

3. **Mixpanel's funnel and retention analysis is best-in-class.** For a B2B SaaS tracking `Onboarding → API Key → Audio Generation` conversion, Mixpanel's funnel builder is superior.

4. **`devrel-reports-bot`** uses Mixpanel's Export API (`data.mixpanel.com/api/2.0/export`) to auto-generate weekly Slack reports with signup metrics, conversion funnels, top countries, and top pages. This pipeline would need to be rebuilt.

5. **Cross-domain cookie tracking** (`.smallest.ai` domain) is working — atoms, console, waves, and docs all share identity. Re-doing this with PostHog is doable but not free effort.

### When PostHog Becomes the Better Choice

1. **When you need feature flags** — currently Smallest has no feature flag system. PostHog's flags are tightly integrated with analytics (e.g., "show experiment variant A to 50%, then measure conversion"). This is the single strongest reason to eventually migrate.

2. **When self-hosting matters** — if data residency requirements from enterprise clients require on-prem analytics, PostHog self-host is the only viable option.

3. **When you outgrow Mixpanel's free tier (20M events/mo)** — PostHog's self-host option means you can scale to billions of events at infra cost only.

4. **When you want raw SQL on your analytics data** — PostHog's HogQL lets engineers query raw event data with SQL. Currently you're using ClickHouse for backend events but Mixpanel for product events — PostHog could unify these since it runs on ClickHouse under the hood.

5. **When autocapture becomes valuable** — PostHog auto-tracks clicks, pageviews, and inputs without manual instrumentation. Useful as your product surface grows faster than your analytics instrumentation.

### Recommended Hybrid Approach (Low Effort, High Value)

```
Phase 1 (Now):     Keep Mixpanel as primary product analytics
Phase 2 (Now):     Expand PostHog on docs (already there via Fern)
Phase 3 (1-2 mo):  Add PostHog feature flags as standalone tool
                   (doesn't require migrating analytics)
Phase 4 (6-12 mo): Full migration — use PostHog's Mixpanel import tool
                   to bring historical data, swap SDKs repo by repo
```

**Key risk with PostHog:** The free tier is only 1M events/mo vs Mixpanel's 20M. At your current scale (~2K+ calls/day with 60+ event types per session), you'd likely hit PostHog's paid tier quickly on Cloud. Self-hosting avoids this but adds ops burden.

---

## 4. TL;DR Scorecard

| Dimension | Winner for Smallest AI | Why |
|-----------|----------------------|-----|
| Event analytics & funnels | **Mixpanel** | Already deeply integrated, best-in-class UX |
| Session replay | **Tie** | Both capable, Mixpanel already at 100% |
| Feature flags | **PostHog** | Mixpanel doesn't have this — clear gap |
| A/B testing | **PostHog** | Integrated with analytics, no add-on needed |
| Self-host / data control | **PostHog** | Only option for self-hosting |
| Cost at scale | **PostHog** (self-host) | Zero marginal cost on own infra |
| Migration effort | **Mixpanel** (stay) | 60+ events, 6 repos, 3 backends to migrate |
| Raw data SQL | **PostHog** | HogQL + native ClickHouse (matches your stack) |
| Automated reporting | **Mixpanel** | devrel-reports-bot already built on Export API |

---

**Bottom line:** Mixpanel is the right tool today. PostHog is the right tool for tomorrow. Add PostHog feature flags now as a standalone, and plan a full migration when feature flags + self-hosting become critical business needs.
