import React from "react";

/**
 * <Capabilities> — clean feature-list container for model cards.
 *
 * Usage in MDX:
 *
 *   <Capabilities>
 *     <Capability icon="zap" name="Real-Time Optimized">
 *       Sub-100 ms TTFT at 1 concurrency, ~300 ms at 100.
 *     </Capability>
 *     <Capability icon="globe" name="Multi-Language" href="#supported-languages">
 *       17 streaming + 26 pre-recorded languages.
 *     </Capability>
 *   </Capabilities>
 *
 * Renders as a 2-col responsive grid (1-col on mobile). Each item is icon + bold
 * name + description prose. Optional `href` makes the row a link with a subtle
 * affordance — items without `href` render as static prose (no fake-clickability).
 *
 * Styling rationale:
 * - Inline styles + CSS variables for portability across Fern themes (dark/light)
 *   without depending on Tailwind being globally available in the components dir.
 * - No card chrome / no shadow / no border on individual items — just a subtle
 *   row divider. Generous vertical rhythm so the list scans top-to-bottom.
 * - Icon is a 28px square with the accent color background at low alpha — gives
 *   visual hierarchy without competing with the body text.
 */

type CapabilityProps = {
  icon?: string;
  name: string;
  href?: string;
  children?: React.ReactNode;
};

export const Capability: React.FC<CapabilityProps> = ({ icon, name, href, children }) => {
  const content = (
    <>
      {icon && (
        <span
          aria-hidden="true"
          style={{
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            width: 32,
            height: 32,
            borderRadius: 8,
            background: "color-mix(in srgb, var(--accent, #6366f1) 12%, transparent)",
            color: "var(--accent, #6366f1)",
            flexShrink: 0,
            fontSize: 16,
            lineHeight: 1,
          }}
        >
          <i className={`fa-solid fa-${icon}`} />
        </span>
      )}
      <div style={{ display: "flex", flexDirection: "column", gap: 4, minWidth: 0 }}>
        <span
          style={{
            fontWeight: 600,
            fontSize: "0.95rem",
            color: "var(--text-default, inherit)",
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
                opacity: 0.5,
                transition: "opacity 150ms ease, transform 150ms ease",
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
            lineHeight: 1.5,
            color: "color-mix(in srgb, var(--text-default, currentColor) 75%, transparent)",
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
    borderBottom: "1px solid color-mix(in srgb, var(--text-default, currentColor) 8%, transparent)",
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
          const arrow = e.currentTarget.querySelector(".capability-arrow") as HTMLElement | null;
          if (arrow) {
            arrow.style.opacity = "1";
            arrow.style.transform = "translateX(2px)";
          }
        }}
        onMouseLeave={(e) => {
          const arrow = e.currentTarget.querySelector(".capability-arrow") as HTMLElement | null;
          if (arrow) {
            arrow.style.opacity = "0.5";
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
        gap: "0 32px",
        margin: "16px 0 8px",
      }}
    >
      {children}
    </div>
  );
};
