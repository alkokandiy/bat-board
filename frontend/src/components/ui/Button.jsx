import React from 'react';

/**
 * Every button in this app was hand-rolled Tailwind, so no two agreed on
 * height, radius, press behaviour or disabled state — which is most of why
 * the screens read as assembled rather than designed.
 *
 * `tone` follows the same colour roles as everything else: self for the one
 * action a screen wants, work for the corporate track, ghost for everything
 * secondary, danger for destruction.
 */
const TONES = {
  self: 'bg-signal-self text-bat-bg hover:brightness-110 shadow-tile',
  work: 'bg-signal-work text-bat-bg hover:brightness-110 shadow-tile',
  ghost: 'bg-bat-raised text-ink-muted ring-1 ring-bat-line hover:text-ink hover:ring-bat-line-strong',
  danger: 'bg-transparent text-signal-late ring-1 ring-signal-late/40 hover:bg-signal-late/10 hover:ring-signal-late/70',
};

const SIZES = {
  sm: 'px-2.5 py-1 text-[10px]',
  md: 'px-4 py-2 text-[11px]',
};

export default function Button({
  tone = 'ghost', size = 'md', type = 'button', className = '', children, ...rest
}) {
  return (
    <button
      type={type}
      className={`inline-flex items-center justify-center gap-1.5 rounded-chip font-mono font-bold
        uppercase tracking-widest transition-all duration-200 ease-soft
        active:scale-[0.97] disabled:opacity-40 disabled:pointer-events-none
        focus:outline-none focus-visible:ring-2 focus-visible:ring-signal-self/60
        ${TONES[tone] || TONES.ghost} ${SIZES[size] || SIZES.md} ${className}`}
      {...rest}
    >
      {children}
    </button>
  );
}
