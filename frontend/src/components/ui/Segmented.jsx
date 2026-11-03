import React from 'react';

/**
 * One control, four choices, no four separate bordered boxes.
 *
 * The filters were eight hand-rolled buttons on two rows, each drawing its own
 * border — so the screen opened with more chrome than content. A segmented
 * track reads as a single thing you are moving a selection along.
 */
export default function Segmented({ label, options, value, onChange }) {
  return (
    <div role="group" aria-label={label} className="inline-flex rounded-chip bg-bat-surface ring-1 ring-bat-line p-0.5">
      {options.map((opt) => {
        const on = opt.value === value;
        return (
          <button
            key={opt.value}
            type="button"
            onClick={() => onChange(opt.value)}
            aria-pressed={on}
            className={`px-3 py-1 rounded-[6px] text-[10px] font-mono uppercase tracking-widest
              transition-all duration-200 ease-soft
              focus:outline-none focus-visible:ring-2 focus-visible:ring-signal-self/60
              ${on ? 'bg-bat-raised text-ink shadow-tile' : 'text-ink-faint hover:text-ink-muted'}`}
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}

