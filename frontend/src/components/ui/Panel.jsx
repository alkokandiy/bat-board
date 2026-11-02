import React from 'react';

/**
 * A titled block inside a screen. One shape for all of them, so the eye stops
 * re-learning the layout on every tab.
 */
export default function Panel({ title, meta = null, action = null, children, className = '' }) {
  return (
    <section className={`rounded-lg border border-bat-line bg-bat-surface ${className}`}>
      {(title || action) && (
        <div className="flex items-center justify-between gap-3 border-b border-bat-line px-4 py-2.5">
          <div className="flex items-baseline gap-2 min-w-0">
            <h2 className="text-[11px] font-mono uppercase tracking-widest text-ink-muted truncate">{title}</h2>
            {meta && <span className="text-[10px] font-mono text-ink-faint tabular-nums shrink-0">{meta}</span>}
          </div>
          {action}
        </div>
      )}
      <div className="p-4">{children}</div>
    </section>
  );
}
