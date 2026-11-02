import React from 'react';

/**
 * One input surface. Inputs were previously declared inline on every screen,
 * each with its own background, border and focus colour; a form built from
 * four different greys never looks finished however good the type is.
 */
export const fieldClass =
  `w-full rounded-chip bg-bat-raised px-3 py-2 text-ink placeholder-ink-faint
   ring-1 ring-bat-line transition-all duration-200 ease-soft
   focus:outline-none focus:ring-2 focus:ring-signal-self/50
   disabled:opacity-50`;

export default function Field({ label, hint, children, className = '' }) {
  return (
    <label className={`block ${className}`}>
      {label && (
        <span className="mb-1.5 block text-[10px] font-mono uppercase tracking-[0.14em] text-ink-muted">
          {label}
        </span>
      )}
      {children}
      {hint && <span className="mt-1.5 block text-[10px] leading-snug text-ink-faint">{hint}</span>}
    </label>
  );
}
