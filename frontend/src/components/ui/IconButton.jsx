import React from 'react';

/**
 * A glyph that is still a button.
 *
 * The row controls across this app were bare glyphs with a `title` and no
 * accessible name: a screen reader announced "button, button, button", and
 * nothing could tell them apart. `label` is mandatory here so that cannot
 * happen again — it names the action AND the thing it acts on.
 */
const TONES = {
  plain: 'hover:text-ink hover:ring-bat-line-strong',
  danger: 'hover:text-signal-late hover:ring-signal-late/40',
  warn: 'hover:text-signal-warn hover:ring-signal-warn/40',
};

export default function IconButton({ label, icon: Icon, tone = 'plain', size = 13, className = '', ...rest }) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      className={`w-7 h-7 inline-flex items-center justify-center rounded-chip
        text-ink-faint ring-1 ring-transparent bg-transparent
        transition-all duration-200 ease-soft active:scale-[0.94]
        focus:outline-none focus-visible:ring-2 focus-visible:ring-signal-self/60
        ${TONES[tone] || TONES.plain} ${className}`}
      {...rest}
    >
      <Icon size={size} />
    </button>
  );
}
