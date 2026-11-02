import React from 'react';

/**
 * Nothing here yet — said so it reads as room, not as a failure to load.
 *
 * Flat grey italics ("Nothing here") looked like something had broken. A
 * dashed well reads as a space waiting to be filled, which is what it is.
 */
export default function EmptyState({ children, action = null, compact = false }) {
  return (
    <div className={`rounded-lg border border-dashed border-bat-line text-center ${compact ? 'py-5 px-3' : 'py-10 px-4'}`}>
      <p className="text-[11px] font-mono uppercase tracking-wider text-ink-faint">{children}</p>
      {action && <div className="mt-3">{action}</div>}
    </div>
  );
}
