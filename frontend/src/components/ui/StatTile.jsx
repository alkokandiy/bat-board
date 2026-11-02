import React from 'react';

/**
 * One number worth looking at.
 *
 * Every tile used to look identical — same card, same 1px border, whether it
 * held "42 missions" or a level name — so nothing drew the eye. `tone` gives
 * the number meaning and `attention` marks the ONE that needs a decision: it
 * gets the rail, the colour and a faint glow, and nothing else does. If
 * everything is emphasised, nothing is.
 *
 * The press behaviour is deliberate. A tile that moves a little under the
 * finger feels like a control; one that only changes border colour feels like
 * a div that happens to be clickable.
 */
const TONES = {
  self: { text: 'text-signal-self', rail: 'bg-signal-self', glow: 'shadow-glow-self' },
  work: { text: 'text-signal-work', rail: 'bg-signal-work', glow: 'shadow-glow-work' },
  late: { text: 'text-signal-late', rail: 'bg-signal-late', glow: '' },
  warn: { text: 'text-signal-warn', rail: 'bg-signal-warn', glow: '' },
  good: { text: 'text-signal-good', rail: 'bg-signal-good', glow: '' },
  plain: { text: 'text-ink', rail: 'bg-bat-line-strong', glow: '' },
};

export default function StatTile({ label, value, hint, tone = 'plain', attention = false, onClick }) {
  const t = TONES[tone] || TONES.plain;
  const Tag = onClick ? 'button' : 'div';
  return (
    <Tag
      onClick={onClick}
      className={`group relative isolate w-full overflow-hidden rounded-tile p-4 text-left
        bg-gradient-to-b from-bat-surface to-bat-bg
        ring-1 ${attention ? 'ring-bat-line-strong' : 'ring-bat-line'}
        shadow-tile transition-all duration-200 ease-soft
        ${onClick ? 'hover:shadow-lift hover:ring-bat-line-strong active:scale-[0.985] cursor-pointer' : ''}
        focus:outline-none focus-visible:ring-2 focus-visible:ring-signal-self/60`}
    >
      {attention && (
        <span className={`absolute left-0 top-0 bottom-0 w-[2px] ${t.rail}`} aria-hidden="true" />
      )}
      <div className="text-[10px] font-mono uppercase tracking-[0.14em] text-ink-muted">{label}</div>
      <div className={`mt-2 font-mono font-bold tabular-nums leading-none text-[26px] ${attention ? t.text : 'text-ink'}`}>
        {value}
      </div>
      {hint && <div className="mt-2 text-[11px] leading-snug text-ink-faint">{hint}</div>}
    </Tag>
  );
}
