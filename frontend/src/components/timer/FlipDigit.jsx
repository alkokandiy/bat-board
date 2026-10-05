import React, { useEffect, useRef, useState } from 'react';

// A split-flap digit in real CSS 3D.
//
// Anatomy (as in a mechanical flip clock): two static half-cards, and one
// two-faced flap hinged on the centre seam. The flap's front face carries the
// old digit's top half; as it rotates down 180° its back face carries the new
// digit's bottom half. Lighting is faked by darkening faces as they turn away
// from the light and by shadows cast on the cards beneath.

export const FLIP_MS = 560;
const W = 84;
const H = 116;
const HALF = H / 2;

const digitStyle = {
  position: 'absolute',
  left: 0,
  width: W,
  height: H,
  lineHeight: `${H}px`,
  textAlign: 'center',
  fontFamily: "'Share Tech Mono', monospace",
  fontSize: 92,
  color: 'var(--yellow-core)',
  textShadow: '0 0 18px rgba(255,215,0,0.18), 0 2px 0 rgba(0,0,0,0.5)',
  userSelect: 'none',
};

// One half of a card: `top` shows the upper half of the digit, else the lower.
function Half({ digit, top, style, children }) {
  return (
    <div
      style={{
        position: 'absolute',
        left: 0,
        width: W,
        height: HALF,
        top: top ? 0 : HALF,
        overflow: 'hidden',
        borderRadius: top ? '9px 9px 0 0' : '0 0 9px 9px',
        background: top
          ? 'linear-gradient(180deg, #1b2540 0%, #121a2e 100%)'
          : 'linear-gradient(180deg, #0c1220 0%, #141c31 100%)',
        ...style,
      }}
    >
      <div style={{ ...digitStyle, top: top ? 0 : -HALF }}>{digit}</div>
      {children}
    </div>
  );
}

const shade = (animation) => ({
  position: 'absolute',
  inset: 0,
  background: '#000',
  opacity: 0,
  pointerEvents: 'none',
  animation,
});

function prefersReducedMotion() {
  try {
    return window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false;
  } catch {
    return false;
  }
}

export default function FlipDigit({ digit }) {
  const [shown, setShown] = useState(digit); // the digit the card has settled on
  const [flip, setFlip] = useState(null); // { from, to } while a flap is in the air
  const timer = useRef(null);

  // Start the next flip once the card is idle. If the value changed again
  // mid-flip, the card finishes the current flap and then flips to the latest
  // value, so it always settles on the final digit.
  useEffect(() => {
    if (flip || digit === shown) return;
    if (prefersReducedMotion()) {
      setShown(digit);
      return;
    }
    setFlip({ from: shown, to: digit });
    timer.current = setTimeout(() => {
      setShown(digit);
      setFlip(null);
    }, FLIP_MS + 20);
  }, [digit, shown, flip]);

  useEffect(() => () => clearTimeout(timer.current), []);

  const top = flip ? flip.to : shown;
  const bottom = flip ? flip.from : shown;
  const ms = `${FLIP_MS}ms`;

  return (
    <div
      data-testid="flip-digit"
      data-digit={shown}
      className="relative select-none"
      style={{
        width: W,
        height: H,
        borderRadius: 11,
        perspective: 560,
        background: '#05080f',
        padding: 0,
        boxShadow: [
          '0 0 0 1px rgba(255,215,0,0.10)',
          '0 2px 0 rgba(255,255,255,0.05) inset',
          '0 26px 38px -12px rgba(0,0,0,0.85)',
          '0 6px 10px rgba(0,0,0,0.55)',
        ].join(', '),
      }}
    >
      {/* Static cards: the new digit on top, the old one underneath until the flap lands */}
      <Half digit={top} top>
        {flip && <div style={shade(`flipShadeTop ${ms} ease-in-out forwards`)} />}
      </Half>
      <Half digit={bottom}>
        {flip && <div style={shade(`flipShadeBottom ${ms} ease-in-out forwards`)} />}
      </Half>

      {/* The flap */}
      {flip && (
        <div
          style={{
            position: 'absolute',
            top: 0,
            left: 0,
            width: W,
            height: HALF,
            transformOrigin: '50% 100%',
            transformStyle: 'preserve-3d',
            animation: `flipFlap ${ms} cubic-bezier(0.45, 0, 0.7, 1) forwards`,
            zIndex: 5,
          }}
        >
          {/* Front: old digit, top half */}
          <Half digit={flip.from} top style={{ backfaceVisibility: 'hidden' }}>
            <div style={shade(`flipShadeFront ${ms} ease-in forwards`)} />
          </Half>
          {/* Back: new digit, bottom half, pre-rotated so it reads right-way-up when landed */}
          <div
            style={{
              position: 'absolute',
              inset: 0,
              transform: 'rotateX(180deg)',
              backfaceVisibility: 'hidden',
            }}
          >
            <Half digit={flip.to} style={{ top: 0 }}>
              <div style={shade(`flipShadeBack ${ms} ease-out forwards`)} />
            </Half>
          </div>
        </div>
      )}

      {/* Centre seam + hinge pins */}
      <div
        aria-hidden
        style={{
          position: 'absolute',
          top: HALF - 1,
          left: 0,
          right: 0,
          height: 2,
          background: '#03050a',
          boxShadow: '0 1px 0 rgba(255,255,255,0.06)',
          zIndex: 8,
          pointerEvents: 'none',
        }}
      />
      {[-4, W - 4].map((x) => (
        <div
          key={x}
          aria-hidden
          style={{
            position: 'absolute',
            top: HALF - 4,
            left: x,
            width: 8,
            height: 8,
            borderRadius: '50%',
            background: 'radial-gradient(circle at 35% 30%, #5b6785 0%, #232b42 55%, #0a0e18 100%)',
            boxShadow: '0 1px 2px rgba(0,0,0,0.7)',
            zIndex: 9,
            pointerEvents: 'none',
          }}
        />
      ))}

      {/* Glass gloss */}
      <div
        aria-hidden
        style={{
          position: 'absolute',
          inset: 0,
          borderRadius: 11,
          background:
            'linear-gradient(160deg, rgba(255,255,255,0.07) 0%, rgba(255,255,255,0) 38%, rgba(255,255,255,0) 100%)',
          zIndex: 10,
          pointerEvents: 'none',
        }}
      />
    </div>
  );
}
