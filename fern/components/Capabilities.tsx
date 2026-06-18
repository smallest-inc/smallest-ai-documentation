import React from "react";

/**
 * <Capabilities> — clean feature-list container for model cards.
 *
 * Usage in MDX:
 *
 *   import { Capabilities, Capability } from "@/components/Capabilities";
 *
 *   <Capabilities>
 *     <Capability icon="bolt" name="Real-Time Optimized">
 *       Sub-100 ms TTFT at 1 concurrency, ~300 ms at 100.
 *     </Capability>
 *     <Capability icon="globe" name="Multi-Language" href="#supported-languages">
 *       17 streaming + 26 pre-recorded languages.
 *     </Capability>
 *   </Capabilities>
 *
 * Renders as a 2-col responsive grid (1-col on mobile). Each item is icon +
 * bold name + description prose. Optional `href` makes the row a link with a
 * subtle right-arrow affordance — items without `href` render as static prose
 * (no fake-clickability).
 *
 * Icons are inline SVGs (Lucide-style, 18px, currentColor-stroked) so they
 * work without depending on Font Awesome being available in the custom-
 * component context. Add new icons to ICONS below if you need more.
 */

// Icon set — inline SVGs, 24x24 viewBox, stroke-based for theme parity.
const ICONS: Record<string, React.ReactNode> = {
  bolt: (
    <path d="M13 2L3 14h7l-1 8 10-12h-7l1-8z" strokeLinecap="round" strokeLinejoin="round" />
  ),
  globe: (
    <>
      <circle cx="12" cy="12" r="10" />
      <path d="M2 12h20M12 2a15.3 15.3 0 010 20M12 2a15.3 15.3 0 000 20" />
    </>
  ),
  "shield-halved": (
    <>
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M12 2v20" strokeLinecap="round" />
    </>
  ),
  users: (
    <>
      <path d="M16 21v-2a4 4 0 00-4-4H6a4 4 0 00-4 4v2" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="9" cy="7" r="4" />
      <path d="M22 21v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75" strokeLinecap="round" strokeLinejoin="round" />
    </>
  ),
  "volume-low": (
    <>
      <path d="M11 5L6 9H2v6h4l5 4V5z" strokeLinejoin="round" />
      <path d="M15.54 8.46a5 5 0 010 7.07" strokeLinecap="round" />
    </>
  ),
  language: (
    <>
      <path d="M5 8l6 6M4 14l6-6 2-3M2 5h12M7 2h1M22 22l-5-10-5 10M14 18h6" strokeLinecap="round" strokeLinejoin="round" />
    </>
  ),
  // STT/TTS specific extras — add as you need them
  microphone: (
    <>
      <rect x="9" y="2" width="6" height="12" rx="3" />
      <path d="M19 10a7 7 0 01-14 0M12 19v3M8 22h8" strokeLinecap="round" />
    </>
  ),
  waveform: (
    <>
      <path d="M2 12h2M6 8v8M10 4v16M14 8v8M18 6v12M22 12h2" strokeLinecap="round" />
    </>
  ),
  gauge: (
    <>
      <path d="M3 12a9 9 0 0118 0" />
      <path d="M12 12l4-4" strokeLinecap="round" />
      <circle cx="12" cy="12" r="1" fill="currentColor" stroke="none" />
    </>
  ),
  clock: (
    <>
      <circle cx="12" cy="12" r="10" />
      <path d="M12 6v6l4 2" strokeLinecap="round" />
    </>
  ),
  sparkles: (
    <>
      <path d="M12 3l1.5 4.5L18 9l-4.5 1.5L12 15l-1.5-4.5L6 9l4.5-1.5L12 3z" strokeLinejoin="round" />
      <path d="M19 14l.75 2.25L22 17l-2.25.75L19 20l-.75-2.25L16 17l2.25-.75L19 14z" strokeLinejoin="round" />
    </>
  ),
};

const Icon: React.FC<{ name: string }> = ({ name }) => {
  const path = ICONS[name];
  if (!path) return null;
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      aria-hidden="true"
    >
      {path}
    </svg>
  );
};

type CapabilityProps = {
  icon?: string;
  name: string;
  href?: string;
  children?: React.ReactNode;
};

// Brand accent — matches `colors.accentPrimary` in docs.yml.
// Dark theme: #2A9D8F (teal). Light theme: #083b4d (dark navy).
// We default icons to a muted neutral; the accent color only kicks in on
// hover for linked rows (mirrors the sidebar's selected-vs-unselected pattern).
const MUTED_ICON = "rgba(127, 127, 127, 0.72)";   // works on both themes
const ACCENT = "#2A9D8F";                            // brand teal

export const Capability: React.FC<CapabilityProps> = ({ icon, name, href, children }) => {
  const content = (
    <>
      {icon && (
        <span
          aria-hidden="true"
          className="capability-icon"
          style={{
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            width: 20,
            height: 20,
            flexShrink: 0,
            marginTop: 2,
            color: MUTED_ICON,
            transition: "color 150ms ease",
          }}
        >
          <Icon name={icon} />
        </span>
      )}
      <div style={{ display: "flex", flexDirection: "column", gap: 4, minWidth: 0 }}>
        <span
          style={{
            fontWeight: 600,
            fontSize: "0.95rem",
            display: "inline-flex",
            alignItems: "center",
            gap: 6,
          }}
        >
          {name}
          {href && (
            <span
              aria-hidden="true"
              style={{
                fontSize: "0.75rem",
                opacity: 0.45,
                transition: "opacity 150ms ease, transform 150ms ease, color 150ms ease",
              }}
              className="capability-arrow"
            >
              →
            </span>
          )}
        </span>
        <span
          style={{
            fontSize: "0.875rem",
            lineHeight: 1.55,
            opacity: 0.78,
          }}
        >
          {children}
        </span>
      </div>
    </>
  );

  const itemStyle: React.CSSProperties = {
    display: "flex",
    gap: 14,
    alignItems: "flex-start",
    padding: "16px 4px",
    borderBottom: "1px solid rgba(127, 127, 127, 0.15)",
    textDecoration: "none",
    color: "inherit",
  };

  if (href) {
    return (
      <a
        href={href}
        style={itemStyle}
        className="capability-row capability-row--linked"
        onMouseEnter={(e) => {
          const icon = e.currentTarget.querySelector(".capability-icon") as HTMLElement | null;
          const arrow = e.currentTarget.querySelector(".capability-arrow") as HTMLElement | null;
          if (icon) icon.style.color = ACCENT;
          if (arrow) {
            arrow.style.opacity = "1";
            arrow.style.color = ACCENT;
            arrow.style.transform = "translateX(2px)";
          }
        }}
        onMouseLeave={(e) => {
          const icon = e.currentTarget.querySelector(".capability-icon") as HTMLElement | null;
          const arrow = e.currentTarget.querySelector(".capability-arrow") as HTMLElement | null;
          if (icon) icon.style.color = MUTED_ICON;
          if (arrow) {
            arrow.style.opacity = "0.45";
            arrow.style.color = "";
            arrow.style.transform = "translateX(0)";
          }
        }}
      >
        {content}
      </a>
    );
  }

  return (
    <div style={itemStyle} className="capability-row">
      {content}
    </div>
  );
};

type CapabilitiesProps = {
  children?: React.ReactNode;
};

export const Capabilities: React.FC<CapabilitiesProps> = ({ children }) => {
  return (
    <div
      className="capabilities-grid"
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 280px), 1fr))",
        columnGap: "32px",
        rowGap: 0,
        margin: "16px 0 8px",
      }}
    >
      {children}
    </div>
  );
};
