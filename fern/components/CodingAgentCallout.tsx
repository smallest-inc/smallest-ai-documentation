import React from "react";

/**
 * <CodingAgentCallout /> = persistent per-page hint for developers building
 * with an AI coding agent. Appended to every page-MDX via
 * `scripts/inject_agent_callout.py` and enforced by a CI check.
 *
 * The three links are also PostHog-instrumented via `data-callout-link` so we
 * can measure discovery. Handler is in
 * `fern/docs/assets/scripts/analytics.js` (see setupCodingAgentCalloutTracking).
 *
 * Reads as: article body → this callout → Fern default footer (Was this page
 * helpful? / prev-next / Fern branding). Meant to feel like a calm closing
 * pointer, not an ad.
 */

const ACCENT = "#2A9D8F"; // brand teal, matches colors.accentPrimary.dark
const MUTED_ICON = "rgba(127, 127, 127, 0.72)";

const SparklesIcon = () => (
  <svg
    width="18"
    height="18"
    viewBox="0 0 24 24"
    fill="currentColor"
    aria-hidden="true"
    style={{ flexShrink: 0 }}
  >
    <path
      fillRule="evenodd"
      d="M9 4.5a.75.75 0 01.721.544l.813 2.846a3.75 3.75 0 002.576 2.576l2.846.813a.75.75 0 010 1.442l-2.846.813a3.75 3.75 0 00-2.576 2.576l-.813 2.846a.75.75 0 01-1.442 0l-.813-2.846a3.75 3.75 0 00-2.576-2.576l-2.846-.813a.75.75 0 010-1.442l2.846-.813A3.75 3.75 0 007.466 7.89l.813-2.846A.75.75 0 019 4.5zM18 1.5a.75.75 0 01.728.568l.258 1.036c.236.94.97 1.674 1.91 1.91l1.036.258a.75.75 0 010 1.456l-1.036.258c-.94.236-1.674.97-1.91 1.91l-.258 1.036a.75.75 0 01-1.456 0l-.258-1.036a2.625 2.625 0 00-1.91-1.91l-1.036-.258a.75.75 0 010-1.456l1.036-.258a2.625 2.625 0 001.91-1.91l.258-1.036A.75.75 0 0118 1.5zM16.5 15a.75.75 0 01.712.513l.394 1.183c.15.447.5.799.948.948l1.183.395a.75.75 0 010 1.422l-1.183.395c-.447.15-.799.5-.948.948l-.395 1.183a.75.75 0 01-1.422 0l-.395-1.183a1.5 1.5 0 00-.948-.948l-1.183-.395a.75.75 0 010-1.422l1.183-.395c.447-.15.799-.5.948-.948l.395-1.183A.75.75 0 0116.5 15z"
      clipRule="evenodd"
    />
  </svg>
);

type LinkProps = { href: string; kind: "llms-txt" | "mcp" | "build-page"; children: React.ReactNode };
const CalloutLink: React.FC<LinkProps> = ({ href, kind, children }) => (
  <a
    href={href}
    data-callout-link={kind}
    style={{ color: ACCENT, textDecoration: "none", fontWeight: 500 }}
    onMouseEnter={(e) => (e.currentTarget.style.textDecoration = "underline")}
    onMouseLeave={(e) => (e.currentTarget.style.textDecoration = "none")}
  >
    {children}
  </a>
);

export const CodingAgentCallout: React.FC = () => (
  <aside
    className="coding-agent-callout"
    aria-label="Guidance for AI coding agents"
    style={{
      display: "flex",
      alignItems: "flex-start",
      gap: 12,
      marginTop: 32,
      marginBottom: 8,
      padding: "14px 16px",
      border: "1px solid rgba(127, 127, 127, 0.18)",
      borderRadius: 8,
      background: "rgba(127, 127, 127, 0.04)",
    }}
  >
    <span
      aria-hidden="true"
      style={{
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        width: 20,
        height: 20,
        marginTop: 2,
        color: MUTED_ICON,
      }}
    >
      <SparklesIcon />
    </span>
    <div style={{ fontSize: "0.9rem", lineHeight: 1.55, opacity: 0.9 }}>
      <strong>Building with an AI coding agent?</strong>{" "}
      Start at{" "}
      <CalloutLink href="https://docs.smallest.ai/llms.txt" kind="llms-txt">
        <code>/llms.txt</code>
      </CalloutLink>
      , install the{" "}
      <CalloutLink href="/voice-agents/mcp/getting-started/quick-start" kind="mcp">
        MCP server
      </CalloutLink>
      , or paste a prompt from{" "}
      <CalloutLink
        href="/overview/developer-tools/build-with-a-coding-agent"
        kind="build-page"
      >
        Build with a coding agent
      </CalloutLink>
      .
    </div>
  </aside>
);
