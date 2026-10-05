import React, { useId } from 'react';

// Bat emblem redrawn by eye from the owner's reference: wide sweeping wings
// with crescent horns curling over a deep scoop, short ears, and a pointed
// tail between rounded wing points. One continuous, perfectly symmetric
// outline (the right half was drawn and mirrored; no seam). viewBox 600 × 330.
export const EMBLEM_W = 600;
export const EMBLEM_H = 330;

const BAT_PATH =
  'M 300,104 L 322,72 L 332,126 C 392,129 445,116 448,80 Q 447,60 431,41 C 498,52 562,110 580,181 C 538,189 482,191 457,199 Q 449,208 447,226 Q 378,214 300,287 Q 222,214 153,226 Q 151,208 143,199 C 118,191 62,189 20,181 C 38,110 102,52 169,41 Q 153,60 152,80 C 155,116 208,129 268,126 L 278,72 L 300,104 Z';

// `progress` is 0–100: the emblem fills with light from the bottom up.
export default function BatEmblem({ progress = 0, className = '' }) {
  const id = useId().replace(/:/g, '');
  const p = Math.max(0, Math.min(100, progress));
  // At 100% the clip opens fully so the glow isn't cut off at the ears.
  const fillTop = p >= 100 ? -60 : EMBLEM_H - (p / 100) * EMBLEM_H;

  return (
    <svg
      data-testid="bat-emblem"
      viewBox={`0 0 ${EMBLEM_W} ${EMBLEM_H}`}
      className={`overflow-visible ${className}`}
      role="img"
      aria-label={`Bat emblem, ${Math.round(p)}% elapsed`}
    >
      <defs>
        <path id={`${id}-bat`} d={BAT_PATH} />

        {/* Soft bloom for the lit part */}
        <filter id={`${id}-glow`} x="-15%" y="-20%" width="130%" height="140%">
          <feGaussianBlur stdDeviation="9" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>

        {/* Metallic body: brighter along the wing crest, deeper toward the tail */}
        <linearGradient id={`${id}-lit`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#FFF1A8" />
          <stop offset="35%" stopColor="#FFD700" />
          <stop offset="100%" stopColor="#E0A800" />
        </linearGradient>

        {/* Unlit body: dark steel with a faint top-light */}
        <linearGradient id={`${id}-dark`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#27324a" />
          <stop offset="100%" stopColor="#0f1627" />
        </linearGradient>

        <clipPath id={`${id}-reveal`}>
          <rect x="-40" y={fillTop} width={EMBLEM_W + 80} height={EMBLEM_H + 160} />
        </clipPath>
      </defs>

      {/* Unlit emblem: always visible */}
      <use href={`#${id}-bat`} fill={`url(#${id}-dark)`} stroke="#3a4766" strokeWidth="1.5" strokeLinejoin="round" />

      {/* Lit part, revealed from the bottom as time passes */}
      <g clipPath={`url(#${id}-reveal)`}>
        <use href={`#${id}-bat`} fill={`url(#${id}-lit)`} stroke="#FFE680" strokeWidth="0.8" strokeLinejoin="round" filter={`url(#${id}-glow)`} />
      </g>
    </svg>
  );
}
