import React from "react";

// Fixtures are committed as TS modules (not JSON) because Fern's MDX
// bundler does not resolve relative JSON imports. Each fixture exports a
// typed `Fixture` object captured live from the production Pulse STT
// WebSocket with vad_events=true.
import { fixture as cleanFixture } from "./fixtures/clean";
import { fixture as multiFixture } from "./fixtures/multi-turn";
import { fixture as noTailFixture } from "./fixtures/no-tail";
import type { AnyEvent, Fixture, SpeechEvent } from "./types";

// Audio files live under fern/docs/assets/vad-events/ (Fern static asset
// root). They are served at /assets/vad-events/<name>.mp3 on the rendered
// site. Each fixture's `audio` field carries the URL.

const FIXTURES: Record<string, Fixture> = {
  clean: cleanFixture,
  "multi-turn": multiFixture,
  "no-tail": noTailFixture,
};

const FIXTURE_LABELS: Record<string, { title: string; subtitle: string }> = {
  clean: {
    title: "Clean utterance",
    subtitle: "One speech_started, one speech_ended.",
  },
  "multi-turn": {
    title: "Multiple turns",
    subtitle: "Two voiced regions, two pairs of events.",
  },
  "no-tail": {
    title: "No trailing silence",
    subtitle: "speech_started fires; speech_ended does not.",
  },
};

// Each fixture's `audio` field already points at the served URL
// (/assets/vad-events/<name>.mp3) — no separate mapping needed.

function eventTimestamp(e: AnyEvent): number {
  return e.type === "transcription" ? e.timestamp_est : e.timestamp;
}

function formatTime(s: number): string {
  return `${s.toFixed(2)}s`;
}

function formatPayload(e: AnyEvent): string {
  if (e.type === "transcription") {
    const tag = e.is_final ? "is_final:true" : "is_final:false";
    const short = e.transcript.length > 60 ? `${e.transcript.slice(0, 57)}...` : e.transcript;
    return `{ ${tag}, transcript: "${short}" }`;
  }
  return `{ type: "${e.type}", session_id: "${(e.session_id || "").slice(0, 8)}", timestamp: ${e.timestamp.toFixed(3)} }`;
}

function eventColor(e: AnyEvent): string {
  if (e.type === "speech_started") return "var(--accent, #2dd4bf)";
  if (e.type === "speech_ended") return "var(--accent-secondary, #a78bfa)";
  return "var(--text-muted, #71717a)";
}

function eventGlyph(e: AnyEvent): string {
  if (e.type === "speech_started") return "▶";
  if (e.type === "speech_ended") return "■";
  return "·";
}

export const VadEventsDemo: React.FC = () => {
  const [activeFixture, setActiveFixture] = React.useState<string>("clean");
  const [playheadS, setPlayheadS] = React.useState<number>(0);
  const [isPlaying, setIsPlaying] = React.useState<boolean>(false);
  const audioRef = React.useRef<HTMLAudioElement | null>(null);
  const rafRef = React.useRef<number | null>(null);
  const logRefs = React.useRef<Record<number, HTMLDivElement | null>>({});

  const fixture = FIXTURES[activeFixture];

  // Reset on fixture change
  React.useEffect(() => {
    setPlayheadS(0);
    setIsPlaying(false);
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.currentTime = 0;
    }
  }, [activeFixture]);

  // Drive the playhead while playing
  React.useEffect(() => {
    function tick() {
      if (audioRef.current) setPlayheadS(audioRef.current.currentTime);
      rafRef.current = requestAnimationFrame(tick);
    }
    if (isPlaying) {
      rafRef.current = requestAnimationFrame(tick);
      return () => {
        if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
      };
    }
    return undefined;
  }, [isPlaying]);

  // Determine "current" event index based on playhead.
  // Scans the whole array (rather than stopping at the first out-of-order
  // timestamp) so non-monotonic sequences still highlight correctly.
  // Picks the latest event by timestamp that the playhead has crossed.
  const currentEventIdx = React.useMemo(() => {
    let idx = -1;
    let bestTs = -Infinity;
    for (let i = 0; i < fixture.events.length; i++) {
      const ts = eventTimestamp(fixture.events[i]);
      if (ts <= playheadS && ts > bestTs) {
        idx = i;
        bestTs = ts;
      }
    }
    return idx;
  }, [playheadS, fixture]);

  // Auto-scroll the log so the current event stays visible
  React.useEffect(() => {
    const el = logRefs.current[currentEventIdx];
    if (el && typeof el.scrollIntoView === "function") {
      el.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }, [currentEventIdx]);

  function togglePlay() {
    if (!audioRef.current) return;
    if (audioRef.current.paused) {
      audioRef.current.play();
      setIsPlaying(true);
    } else {
      audioRef.current.pause();
      setIsPlaying(false);
    }
  }

  function onTimeUpdate(e: React.SyntheticEvent<HTMLAudioElement>) {
    setPlayheadS((e.target as HTMLAudioElement).currentTime);
  }

  function onEnded() {
    setIsPlaying(false);
  }

  // Layout constants
  const waveWidth = 720;
  const waveHeight = 96;
  const barCount = fixture.waveform.length;
  const barWidth = waveWidth / barCount;
  const playheadX = (playheadS / fixture.duration_s) * waveWidth;

  return (
    <div
      style={{
        border: "1px solid var(--border, #3f3f46)",
        borderRadius: 10,
        padding: 16,
        marginBottom: 24,
        background: "var(--background-secondary, transparent)",
      }}
    >
      {/* Fixture picker */}
      <div style={{ display: "flex", gap: 8, marginBottom: 12, flexWrap: "wrap" }}>
        {Object.keys(FIXTURES).map((k) => {
          const active = activeFixture === k;
          return (
            <button
              key={k}
              type="button"
              onClick={() => setActiveFixture(k)}
              style={{
                padding: "8px 12px",
                borderRadius: 6,
                border: active
                  ? "1px solid var(--accent, #2dd4bf)"
                  : "1px solid var(--border, #3f3f46)",
                background: active ? "var(--accent-faded, rgba(45,212,191,0.1))" : "transparent",
                color: "var(--text-default, inherit)",
                cursor: "pointer",
                textAlign: "left",
                minWidth: 180,
              }}
            >
              <div style={{ fontWeight: 600, fontSize: 13 }}>{FIXTURE_LABELS[k].title}</div>
              <div style={{ fontSize: 11, color: "var(--text-muted, #71717a)", marginTop: 2 }}>
                {FIXTURE_LABELS[k].subtitle}
              </div>
            </button>
          );
        })}
      </div>

      {/* Audio + transport */}
      <audio
        ref={audioRef}
        src={fixture.audio}
        preload="metadata"
        onTimeUpdate={onTimeUpdate}
        onEnded={onEnded}
        onPlay={() => setIsPlaying(true)}
        onPause={() => setIsPlaying(false)}
      />

      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 8 }}>
        <button
          type="button"
          onClick={togglePlay}
          style={{
            padding: "6px 14px",
            borderRadius: 6,
            border: "1px solid var(--accent, #2dd4bf)",
            background: "var(--accent, #2dd4bf)",
            color: "var(--background, #000)",
            cursor: "pointer",
            fontWeight: 600,
            fontSize: 13,
            minWidth: 80,
          }}
        >
          {isPlaying ? "Pause" : "Play"}
        </button>
        <span style={{ fontFamily: "monospace", fontSize: 12, color: "var(--text-muted, #71717a)" }}>
          {formatTime(playheadS)} / {formatTime(fixture.duration_s)}
        </span>
        <span
          style={{
            fontFamily: "monospace",
            fontSize: 11,
            color: "var(--text-muted, #71717a)",
            marginLeft: "auto",
          }}
        >
          {fixture.sample_rate} Hz · mono PCM
        </span>
      </div>

      {/* Waveform + markers */}
      <div style={{ position: "relative", width: "100%", overflow: "hidden" }}>
        <svg
          viewBox={`0 0 ${waveWidth} ${waveHeight + 28}`}
          preserveAspectRatio="none"
          style={{
            width: "100%",
            height: waveHeight + 28,
            background: "var(--background-tertiary, rgba(255,255,255,0.02))",
            borderRadius: 6,
          }}
        >
          {/* Waveform bars */}
          {fixture.waveform.map((amp, i) => {
            const h = Math.max(1, amp * waveHeight);
            const x = i * barWidth;
            const y = (waveHeight - h) / 2;
            return (
              <rect
                key={i}
                x={x}
                y={y}
                width={Math.max(1, barWidth - 0.5)}
                height={h}
                fill="var(--text-muted, #71717a)"
                opacity={0.45}
              />
            );
          })}

          {/* Event markers */}
          {fixture.events
            .filter((e) => e.type === "speech_started" || e.type === "speech_ended")
            .map((e, i) => {
              const x = (eventTimestamp(e) / fixture.duration_s) * waveWidth;
              const color = eventColor(e);
              const label = e.type;
              const aboveBar = e.type === "speech_started";
              return (
                <g key={`m-${i}`}>
                  <line
                    x1={x}
                    x2={x}
                    y1={0}
                    y2={waveHeight}
                    stroke={color}
                    strokeWidth={2}
                    strokeDasharray="4 3"
                  />
                  <circle cx={x} cy={aboveBar ? 6 : waveHeight - 6} r={5} fill={color} />
                  <text
                    x={x + 8}
                    y={waveHeight + 18}
                    fontSize={11}
                    fontFamily="ui-monospace, monospace"
                    fill={color}
                  >
                    {label} @ {(e as SpeechEvent).timestamp.toFixed(2)}s
                  </text>
                </g>
              );
            })}

          {/* Playhead */}
          {playheadS > 0 && playheadS <= fixture.duration_s && (
            <line
              x1={playheadX}
              x2={playheadX}
              y1={0}
              y2={waveHeight}
              stroke="var(--accent, #2dd4bf)"
              strokeWidth={1.5}
              opacity={0.9}
            />
          )}
        </svg>
      </div>

      {/* Event log */}
      <div style={{ marginTop: 12 }}>
        <div
          style={{
            fontSize: 11,
            fontFamily: "ui-monospace, monospace",
            color: "var(--text-muted, #71717a)",
            marginBottom: 4,
            textTransform: "uppercase",
            letterSpacing: 0.5,
          }}
        >
          Server messages — captured from a live run
        </div>
        <div
          style={{
            maxHeight: 220,
            overflowY: "auto",
            border: "1px solid var(--border, #3f3f46)",
            borderRadius: 6,
            background: "var(--background-tertiary, rgba(0,0,0,0.2))",
            fontFamily: "ui-monospace, monospace",
            fontSize: 12,
          }}
        >
          {fixture.events.map((e, i) => {
            const isCurrent = i === currentEventIdx;
            const reached = i <= currentEventIdx;
            return (
              <div
                key={i}
                ref={(el) => {
                  logRefs.current[i] = el;
                }}
                style={{
                  padding: "6px 10px",
                  borderLeft: `3px solid ${isCurrent ? eventColor(e) : "transparent"}`,
                  background: isCurrent ? "var(--accent-faded, rgba(45,212,191,0.08))" : "transparent",
                  opacity: reached ? 1 : 0.45,
                  color: "var(--text-default, inherit)",
                  display: "flex",
                  gap: 10,
                  alignItems: "baseline",
                }}
              >
                <span
                  style={{
                    width: 56,
                    color: "var(--text-muted, #71717a)",
                    fontSize: 11,
                  }}
                >
                  {formatTime(eventTimestamp(e))}
                </span>
                <span style={{ color: eventColor(e), width: 16, textAlign: "center" }}>
                  {eventGlyph(e)}
                </span>
                <span style={{ flex: 1, wordBreak: "break-word" }}>{formatPayload(e)}</span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};
