import React from 'react';

/**
 * One number worth looking at.
 *
 * Every tile used to look identical — same card, same border, whether it held
 * "42 missions" or a level name — so nothing drew the eye to what mattered.
 * `tone` carries the meaning, and `attention` marks the one that needs a
 * decision: it gets the coloured rail and a brighter number, and nothing else
 * does. If everything is emphasised, nothing is.
 */
const TONES = {
  self: { text: 'text-signal-self', rail: 'bg-signal-self' },
  work: { text: 'text-signal-work', rail: 'bg-signal-work' },
  late: { text: 'text-signal-late', rail: 'bg-signal-late' },
  warn: { text: 'text-signal-warn', rail: 'bg-signal-warn' },
  good: { text: 'text-signal-good', rail: 'bg-signal-good' },
  plain: { text: 'text-ink', rail: 'bg-bat-line-strong' },
};

export default function StatTile({ label, value, hint, tone = 'plain', attention = false, onClick }) {
  const t = TONES[tone] || TONES.plain;
  const Tag = onClick ? 'button' : 'div';
  return (
    <Tag
      onClick={onClick}
      className={`relative overflow-hidden rounded-lg border bg-bat-surface p-4 text-left w-full
        ${attention ? 'border-bat-line-strong' : 'border-bat-line'}
        ${onClick ? 'transition-colors duration-150 hover:border-bat-line-strong focus:outline-none focus-visible:ring-1 focus-visible:ring-signal-self/50' : ''}`}
    >
      {attention && (
        <span className={`absolute left-0 top-0 bottom-0 w-[2px] ${t.rail}`} aria-hidden="true" />
      )}
      <div className="text-[10px] font-mono uppercase tracking-widest text-ink-muted">{label}</div>
      <div className={`mt-1.5 font-mono font-bold tabular-nums leading-none text-2xl ${attention ? t.text : 'text-ink'}`}>
        {value}
      </div>
      {hint && <div className="mt-1.5 text-[11px] text-ink-faint">{hint}</div>}
    </Tag>
  );
}
