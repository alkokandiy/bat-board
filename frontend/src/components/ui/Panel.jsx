import React from 'react';

/**
 * A titled block inside a screen. One shape for all of them, so the eye stops
 * re-learning the layout on every tab.
 *
 * The header rule is a hairline rather than a full border: the panel is held
 * together by its surface and shadow, not by being drawn around.
 */
export default function Panel({ title, meta = null, action = null, children, className = '', bodyClassName = 'p-4' }) {
  return (
    <section
      className={`rounded-card bg-gradient-to-b from-bat-surface to-bat-bg
        ring-1 ring-bat-line shadow-tile overflow-hidden ${className}`}
    >
      {(title || action) && (
        <div className="flex items-center justify-between gap-3 px-4 py-3 border-b border-white/[0.04]">
          <div className="flex items-baseline gap-2 min-w-0">
            <h2 className="text-[11px] font-mono uppercase tracking-[0.14em] text-ink-muted truncate">{title}</h2>
            {meta && <span className="text-[10px] font-mono text-ink-faint tabular-nums shrink-0">{meta}</span>}
          </div>
          {action}
        </div>
      )}
      <div className={bodyClassName}>{children}</div>
    </section>
  );
}
