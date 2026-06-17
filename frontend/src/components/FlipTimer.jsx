import React, { useState, useEffect, useRef } from 'react';

function FlipDigit({ digit, delay }) {
  const [flipping, setFlipping] = useState(false);
  const [displayed, setDisplayed] = useState(digit);
  const prevRef = useRef(digit);

  useEffect(() => {
    if (digit !== prevRef.current) {
      setFlipping(true);
      const t1 = setTimeout(() => {
        setDisplayed(digit);
        prevRef.current = digit;
      }, 150);
      const t2 = setTimeout(() => setFlipping(false), 300);
      return () => { clearTimeout(t1); clearTimeout(t2); };
    }
  }, [digit]);

  return (
    <div className="relative" style={{ width: '0.6em', height: '0.85em', perspective: '600px' }}>
      <div
        className={`absolute inset-0 flex items-center justify-center rounded-md border select-none transition-transform duration-[400ms] ease-in-out ${
          flipping
            ? 'border-electric-bat-yellow/60 bg-dark-slate text-electric-bat-yellow'
            : 'border-slate-700 bg-matte-obsidian text-slate-100'
        } ${flipping ? 'animate-flip-card' : ''}`}
        style={{ backfaceVisibility: 'hidden', transformStyle: 'preserve-3d' }}
      >
        <span className="font-mono font-bold leading-none">{displayed}</span>
        {/* reflection line */}
        <div className="absolute top-1/2 left-0 right-0 h-[1px] bg-slate-800/50" />
      </div>
      {flipping && (
        <div
          className="absolute inset-0 flex items-center justify-center rounded-md border border-electric-bat-yellow/60 bg-dark-slate text-electric-bat-yellow animate-flip-card-reverse select-none"
          style={{ backfaceVisibility: 'hidden', transformStyle: 'preserve-3d' }}
        >
          <span className="font-mono font-bold leading-none">{digit}</span>
          <div className="absolute top-1/2 left-0 right-0 h-[1px] bg-slate-800/50" />
        </div>
      )}
    </div>
  );
}

export default function FlipTimer({ seconds, className = '' }) {
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  const timeStr = `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;

  return (
    <div className={`flex items-center justify-center gap-1 ${className}`}>
      {timeStr.split('').map((char, i) =>
        char === ':' ? (
          <span key={i} className="text-4xl font-mono font-bold text-electric-bat-yellow mx-0.5 select-none" style={{ textShadow: '0 0 12px rgba(245,200,66,0.4)' }}>:</span>
        ) : (
          <FlipDigit key={i} digit={char} delay={i * 50} />
        )
      )}
      <style>{`
        @keyframes flip-card {
          0% { transform: rotateY(0deg); }
          50% { transform: rotateY(90deg); }
          51% { opacity: 0; }
          100% { opacity: 0; transform: rotateY(90deg); }
        }
        @keyframes flip-card-reverse {
          0% { opacity: 0; transform: rotateY(-90deg); }
          49% { opacity: 0; transform: rotateY(-90deg); }
          50% { opacity: 1; transform: rotateY(-90deg); }
          100% { transform: rotateY(0deg); }
        }
        .animate-flip-card {
          animation: flip-card 400ms ease-in-out forwards;
        }
        .animate-flip-card-reverse {
          animation: flip-card-reverse 400ms ease-in-out forwards;
        }
      `}</style>
    </div>
  );
}
