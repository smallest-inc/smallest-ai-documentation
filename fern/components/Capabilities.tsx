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

// Icon set — inline SVGs, 24x24 viewBox, FILLED (Heroicons-solid / FA-solid style)
// to match the existing sidebar icon look (`microphone`, `sparkles`, etc.).
// All paths use `fill="currentColor"`; no stroke.
const ICONS: Record<string, React.ReactNode> = {
  bolt: (
    <path d="M14.615 1.595a.75.75 0 01.359.852L12.982 9.75h7.268a.75.75 0 01.548 1.262l-10.5 11.25a.75.75 0 01-1.272-.71l1.992-7.302H3.75a.75.75 0 01-.548-1.262l10.5-11.25a.75.75 0 01.913-.143z" />
  ),
  globe: (
    <path d="M21.721 12.752a9.711 9.711 0 00-.945-5.003 12.754 12.754 0 01-4.339 2.708 18.991 18.991 0 01-.214 4.772 17.165 17.165 0 005.498-2.477zM14.634 15.55a17.324 17.324 0 00.332-4.647c-.952.227-1.945.347-2.966.347-1.021 0-2.014-.12-2.966-.347a17.515 17.515 0 00.332 4.647 17.385 17.385 0 005.268 0zM9.772 17.119a18.963 18.963 0 004.456 0A17.182 17.182 0 0112 21.724a17.18 17.18 0 01-2.228-4.605zM7.777 15.23a18.87 18.87 0 01-.214-4.774 12.753 12.753 0 01-4.34-2.708 9.711 9.711 0 00-.944 5.004 17.165 17.165 0 005.498 2.477zM21.356 14.752a9.765 9.765 0 01-7.478 6.817 18.64 18.64 0 001.988-4.718 18.627 18.627 0 005.49-2.098zM2.644 14.752c1.682.971 3.53 1.688 5.49 2.099a18.64 18.64 0 001.988 4.718 9.765 9.765 0 01-7.478-6.816zM13.878 2.43a9.755 9.755 0 016.116 3.986 11.267 11.267 0 01-3.746 2.504 18.63 18.63 0 00-2.37-6.49zM12 2.276a17.152 17.152 0 012.805 7.121c-.897.23-1.837.353-2.805.353-.968 0-1.908-.122-2.805-.353A17.151 17.151 0 0112 2.276zM10.122 2.43a18.629 18.629 0 00-2.37 6.49 11.266 11.266 0 01-3.746-2.504 9.754 9.754 0 016.116-3.985z" />
  ),
  "shield-halved": (
    <path fillRule="evenodd" d="M12.516 2.17a.75.75 0 00-1.032 0 11.209 11.209 0 01-7.877 3.08.75.75 0 00-.722.515A12.74 12.74 0 002.25 9.75c0 5.942 4.064 10.933 9.563 12.348a.749.749 0 00.374 0c5.499-1.415 9.563-6.406 9.563-12.348 0-1.39-.223-2.73-.635-3.985a.75.75 0 00-.722-.516l-.143.001c-2.996 0-5.717-1.17-7.734-3.08zM12 7.5a.75.75 0 01.75.75v3.75a.75.75 0 01-1.5 0V8.25A.75.75 0 0112 7.5zm0 8.25a.75.75 0 100 1.5.75.75 0 000-1.5z" clipRule="evenodd" />
  ),
  users: (
    <>
      <path d="M4.5 6.375a4.125 4.125 0 118.25 0 4.125 4.125 0 01-8.25 0zM14.25 8.625a3.375 3.375 0 116.75 0 3.375 3.375 0 01-6.75 0zM1.5 19.125a7.125 7.125 0 0114.25 0v.003l-.001.119a.75.75 0 01-.363.63 13.067 13.067 0 01-6.761 1.873c-2.472 0-4.786-.684-6.76-1.873a.75.75 0 01-.364-.63l-.001-.122zM17.25 19.128l-.001.144a2.25 2.25 0 01-.233.96 10.088 10.088 0 005.06-1.01.75.75 0 00.42-.643 4.875 4.875 0 00-6.957-4.611 8.586 8.586 0 011.71 5.157v.003z" />
    </>
  ),
  "volume-low": (
    <path fillRule="evenodd" d="M13.5 4.06c0-1.336-1.616-2.005-2.56-1.06l-4.5 4.5H4.508c-1.141 0-2.318.664-2.66 1.905A9.76 9.76 0 001.5 12c0 .898.121 1.768.35 2.595.341 1.24 1.518 1.905 2.659 1.905h1.93l4.5 4.5c.945.945 2.561.276 2.561-1.06V4.06zM15.932 7.757a.75.75 0 011.061 0 6 6 0 010 8.486.75.75 0 01-1.06-1.061 4.5 4.5 0 000-6.364.75.75 0 010-1.06z" clipRule="evenodd" />
  ),
  language: (
    <path fillRule="evenodd" d="M9 2.25a.75.75 0 01.75.75v1.506a49.38 49.38 0 015.343.371.75.75 0 11-.186 1.489c-.66-.083-1.323-.151-1.99-.206a18.67 18.67 0 01-2.97 6.323c.318.384.65.753.998 1.107a.75.75 0 11-1.07 1.052A18.902 18.902 0 019 13.687a18.823 18.823 0 01-5.656 4.482.75.75 0 11-.688-1.333 17.323 17.323 0 005.396-4.353A18.72 18.72 0 015.89 8.598a.75.75 0 011.388-.568A17.21 17.21 0 009 11.224a17.17 17.17 0 002.391-5.165 48.038 48.038 0 00-8.298.307.75.75 0 01-.186-1.489 49.159 49.159 0 015.343-.371V3A.75.75 0 019 2.25zM15.75 9a.75.75 0 01.68.433l5.25 11.25a.75.75 0 01-1.36.634l-1.198-2.567h-6.744l-1.198 2.567a.75.75 0 01-1.36-.634l5.25-11.25A.75.75 0 0115.75 9zm-2.672 8.25h5.344l-2.672-5.726-2.672 5.726z" clipRule="evenodd" />
  ),
  microphone: (
    <>
      <path d="M8.25 4.5a3.75 3.75 0 117.5 0v8.25a3.75 3.75 0 11-7.5 0V4.5z" />
      <path d="M6 10.5a.75.75 0 01.75.75v1.5a5.25 5.25 0 1010.5 0v-1.5a.75.75 0 011.5 0v1.5a6.751 6.751 0 01-6 6.709v2.041h3a.75.75 0 010 1.5h-7.5a.75.75 0 010-1.5h3v-2.041a6.751 6.751 0 01-6-6.709v-1.5A.75.75 0 016 10.5z" />
    </>
  ),
  waveform: (
    <>
      <path d="M3.75 12a.75.75 0 01.75-.75h.75a.75.75 0 010 1.5H4.5a.75.75 0 01-.75-.75zM7.5 8.25a.75.75 0 01.75.75v6a.75.75 0 01-1.5 0V9a.75.75 0 01.75-.75zM10.5 4.5a.75.75 0 01.75.75v13.5a.75.75 0 01-1.5 0V5.25a.75.75 0 01.75-.75zM13.5 8.25a.75.75 0 01.75.75v6a.75.75 0 01-1.5 0V9a.75.75 0 01.75-.75zM16.5 6a.75.75 0 01.75.75v10.5a.75.75 0 01-1.5 0V6.75A.75.75 0 0116.5 6zM19.5 11.25a.75.75 0 01.75.75.75.75 0 01-.75.75h-.75a.75.75 0 010-1.5h.75z" />
    </>
  ),
  gauge: (
    <path fillRule="evenodd" d="M12 2.25c-5.385 0-9.75 4.365-9.75 9.75 0 2.32.81 4.45 2.16 6.124.31.385.83.554 1.293.43A33.7 33.7 0 0112 18c2.213 0 4.36.214 6.297.578.464.124.984-.045 1.293-.43A9.715 9.715 0 0021.75 12c0-5.385-4.365-9.75-9.75-9.75zm4.28 7.78a.75.75 0 00-1.06-1.06l-3.22 3.22a1.5 1.5 0 101.06 1.06l3.22-3.22z" clipRule="evenodd" />
  ),
  clock: (
    <path fillRule="evenodd" d="M12 2.25c-5.385 0-9.75 4.365-9.75 9.75s4.365 9.75 9.75 9.75 9.75-4.365 9.75-9.75S17.385 2.25 12 2.25zM12.75 6a.75.75 0 00-1.5 0v6c0 .414.336.75.75.75h4.5a.75.75 0 000-1.5h-3.75V6z" clipRule="evenodd" />
  ),
  sparkles: (
    <path fillRule="evenodd" d="M9 4.5a.75.75 0 01.721.544l.813 2.846a3.75 3.75 0 002.576 2.576l2.846.813a.75.75 0 010 1.442l-2.846.813a3.75 3.75 0 00-2.576 2.576l-.813 2.846a.75.75 0 01-1.442 0l-.813-2.846a3.75 3.75 0 00-2.576-2.576l-2.846-.813a.75.75 0 010-1.442l2.846-.813A3.75 3.75 0 007.466 7.89l.813-2.846A.75.75 0 019 4.5zM18 1.5a.75.75 0 01.728.568l.258 1.036c.236.94.97 1.674 1.91 1.91l1.036.258a.75.75 0 010 1.456l-1.036.258c-.94.236-1.674.97-1.91 1.91l-.258 1.036a.75.75 0 01-1.456 0l-.258-1.036a2.625 2.625 0 00-1.91-1.91l-1.036-.258a.75.75 0 010-1.456l1.036-.258a2.625 2.625 0 001.91-1.91l.258-1.036A.75.75 0 0118 1.5zM16.5 15a.75.75 0 01.712.513l.394 1.183c.15.447.5.799.948.948l1.183.395a.75.75 0 010 1.422l-1.183.395c-.447.15-.799.5-.948.948l-.395 1.183a.75.75 0 01-1.422 0l-.395-1.183a1.5 1.5 0 00-.948-.948l-1.183-.395a.75.75 0 010-1.422l1.183-.395c.447-.15.799-.5.948-.948l.395-1.183A.75.75 0 0116.5 15z" clipRule="evenodd" />
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
      fill="currentColor"
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
  /**
   * If true, wraps the entire grid in a subtle outer container with a
   * 1px border + rounded corners + interior padding. Per-row dividers
   * stay. Use this when the section needs more visual definition next
   * to surrounding tables / heavy prose. Default is borderless.
   */
  bordered?: boolean;
  children?: React.ReactNode;
};

export const Capabilities: React.FC<CapabilitiesProps> = ({ bordered = false, children }) => {
  const gridStyle: React.CSSProperties = {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 280px), 1fr))",
    columnGap: "32px",
    rowGap: 0,
  };

  if (bordered) {
    return (
      <div
        className="capabilities-container--bordered"
        style={{
          border: "1px solid rgba(127, 127, 127, 0.18)",
          borderRadius: 10,
          padding: "4px 20px",
          margin: "16px 0 8px",
        }}
      >
        <div className="capabilities-grid" style={gridStyle}>
          {children}
        </div>
      </div>
    );
  }

  return (
    <div
      className="capabilities-grid"
      style={{ ...gridStyle, margin: "16px 0 8px" }}
    >
      {children}
    </div>
  );
};
