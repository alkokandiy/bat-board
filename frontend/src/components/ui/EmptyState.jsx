import React from 'react';

/**
 * Nothing here yet — said so it reads as room, not as a failure to load.
 */
export default function EmptyState({ children, action = null, compact = false }) {
  return (
    <div className={`rounded-tile border border-dashed border-bat-line text-center ${compact ? 'py-6 px-3' : 'py-12 px-4'}`}>
      <p className="text-[11px] font-mono uppercase tracking-[0.14em] text-ink-faint">{children}</p>
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
