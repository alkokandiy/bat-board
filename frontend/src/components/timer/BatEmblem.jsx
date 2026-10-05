import React, { useId } from 'react';

// The classic Batman oval emblem, redrawn by eye from the owner's reference:
// a black bat inside a yellow ring, with the yellow showing through the rounded
// gaps above the wings (either side of the ears) and the scalloped gaps below.
//
// Layers: black border, yellow ring, black field, then the yellow lobes and the
// ear notch on top. The yellow parts are drawn twice — dim brass, and bright
// gold clipped to `progress` from the bottom up — so the signal "lights up"
// as time passes while the bat itself stays black. viewBox is 500 × 285.
export const EMBLEM_W = 500;
export const EMBLEM_H = 285;

const CX = 250;
const CY = 142.5;
const BLACK = '#04060a';

// Top-left lobe, bottom-left lobe (mirrored for the right side) and the notch
// between the ears. Lobes extend into the ring so they merge with it.
const TOP_LOBE =
  'M 150,28 C 143,40 139,52 141,66 C 143,82 152,95 168,102 C 183,108 198,108 207,101 C 214,94 217,78 219,58 C 220,46 221,36 223,27 L 223,20 Z';
const BOTTOM_LOBE =
  'M 118,245 L 116,236 C 110,230 103,220 101,211 C 99,202 105,189 120,184 C 135,180 148,185 158,193 C 164,198 168,203 171,207 C 175,200 185,189 198,187 C 210,186 220,195 230,209 C 238,220 245,232 250,243 L 250,262 Z';
const EAR_NOTCH = 'M 223,20 L 223,27 Q 228,45 237,51 L 263,51 Q 272,45 277,27 L 277,20 Z';
const MIRROR = `translate(${EMBLEM_W},0) scale(-1,1)`;

// The yellow parts of the emblem in one colour.
function Yellow({ id, fill }) {
  return (
    <>
      <ellipse cx={CX} cy={CY} rx="238" ry="130.5" fill={fill} />
      <ellipse cx={CX} cy={CY} rx="222" ry="115" fill={BLACK} />
      {/* A hairline stroke in the same colour hides the seam where the two bottom lobes meet. */}
      <g fill={fill} stroke={typeof fill === 'string' ? fill : undefined} strokeWidth="0.8">
        <use href={`#${id}-top`} />
        <use href={`#${id}-top`} transform={MIRROR} />
        <use href={`#${id}-bottom`} />
        <use href={`#${id}-bottom`} transform={MIRROR} />
        <use href={`#${id}-notch`} />
      </g>
    </>
  );
}

// `progress` is 0–100.
export default function BatEmblem({ progress = 0, className = '' }) {
  const id = useId().replace(/:/g, '');
  const p = Math.max(0, Math.min(100, progress));
  // At 100% the clip opens fully so the glow isn't cut off at the edges.
  const fillTop = p >= 100 ? -60 : EMBLEM_H - (p / 100) * EMBLEM_H;

  return (
    <svg
      data-testid="bat-emblem"
      viewBox={`0 0 ${EMBLEM_W} ${EMBLEM_H}`}
      className={`overflow-visible ${className}`}
      role="img"
      aria-label={`Bat-Signal, ${Math.round(p)}% elapsed`}
    >
      <defs>
        <path id={`${id}-top`} d={TOP_LOBE} />
        <path id={`${id}-bottom`} d={BOTTOM_LOBE} />
        <path id={`${id}-notch`} d={EAR_NOTCH} />

        {/* Lit gold: brightest in the middle, deeper at the rim. Shared by all shapes. */}
        <radialGradient id={`${id}-lit`} gradientUnits="userSpaceOnUse" cx={CX} cy={CY} r="250">
          <stop offset="0%" stopColor="#FFE680" />
          <stop offset="55%" stopColor="#FFC800" />
          <stop offset="100%" stopColor="#E6A200" />
        </radialGradient>

        <filter id={`${id}-glow`} x="-10%" y="-15%" width="120%" height="130%" colorInterpolationFilters="sRGB">
          <feGaussianBlur stdDeviation="9" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>

        <clipPath id={`${id}-reveal`}>
          <rect x="-60" y={fillTop} width={EMBLEM_W + 120} height={EMBLEM_H + 200} />
        </clipPath>
      </defs>

      {/* Black border (and a faint rim so it reads on a dark panel) */}
      <ellipse cx={CX} cy={CY} rx="249" ry="142" fill={BLACK} stroke="#2a3248" strokeWidth="1.5" />

      {/* Unlit: dim brass */}
      <Yellow id={id} fill="#3b3420" />

      {/* Lit from the bottom as time passes */}
      <g clipPath={`url(#${id}-reveal)`}>
        <g filter={`url(#${id}-glow)`}>
          <Yellow id={id} fill={`url(#${id}-lit)`} />
        </g>
      </g>
    </svg>
  );
}
