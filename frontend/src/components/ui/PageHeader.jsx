import React from 'react';

/**
 * The top of every screen.
 *
 * The old headers spent their most valuable line on prose that said nothing —
 * "Tactical overview of ongoing Gotham defense protocols" told you neither
 * what was on the board nor what to do. The voice stays; the line now carries
 * facts. `stats` is a list of {label, value, tone} rendered as a single
 * readable strip: "42 open · 6 overdue · 3 due today".
 */
// Tailwind scans source for whole class names, so `bg-${accent}` would be
// purged from the stylesheet and silently render colourless. Every variant
// has to appear literally somewhere it can see.
const ACCENTS = {
  self: 'bg-signal-self',
  work: 'bg-signal-work',
  late: 'bg-signal-late',
  plain: 'bg-bat-line-strong',
};

const STAT_TONES = {
  self: 'text-signal-self',
  work: 'text-signal-work',
  late: 'text-signal-late',
  warn: 'text-signal-warn',
  good: 'text-signal-good',
};

export default function PageHeader({ title, accent = 'self', stats = [], action = null, children }) {
  return (
    <header className="flex items-start justify-between gap-4 mb-section">
      <div className="min-w-0">
        <div className="flex items-baseline gap-3">
          <span className={`w-1 h-6 rounded-sm shrink-0 ${ACCENTS[accent] || ACCENTS.self}`} aria-hidden="true" />
          <h1 className="font-display text-3xl tracking-wide text-ink leading-none">{title}</h1>
        </div>
        {stats.length > 0 && (
          <p className="mt-2 ml-4 text-xs font-mono text-ink-muted flex flex-wrap items-center gap-x-2 gap-y-1">
            {stats.map((s, i) => (
              <React.Fragment key={s.label}>
                {i > 0 && <span className="text-ink-faint" aria-hidden="true">·</span>}
                <span className={STAT_TONES[s.tone] || 'text-ink-muted'}>
                  <span className="tabular-nums">{s.value}</span> {s.label}
                </span>
              </React.Fragment>
            ))}
          </p>
        )}
        {children && <div className="mt-2 ml-4 text-xs text-ink-faint">{children}</div>}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </header>
  );
}
