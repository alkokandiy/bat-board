/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // The original palette is GONE. It was five names kept "so nothing
        // breaks mid-migration", and the migration is finished: nothing in
        // src/ or index.html refers to matte-obsidian, dark-slate,
        // electric-bat-yellow, bat-card or the shadowed bat-surface any
        // more. Two of them were already dead weight — bat-card was used by
        // nobody, and 'bat-surface' declared the same class name as
        // bat.surface below and silently lost to it, so anyone reading it
        // believed panels were #08080f when the CSS said #121218.
        //
        // Keeping a parallel vocabulary alive invites a colour to be chosen
        // for how it looks instead of what it means, which is the whole
        // thing the tokens below exist to stop.

        // --- semantic roles ----------------------------------------------
        // Colour had no meaning here: yellow sat on every border, heading and
        // number, so it signalled nothing. These say what a colour MEANS, and
        // the rule is that yellow is spent sparingly — on the person's own
        // standing and on the one action a screen wants.
        bat: {
          bg: '#0b0b0f',        // the page beneath everything
          surface: '#121218',   // panels
          raised: '#1a1a22',    // cards sitting on panels
          line: '#26262f',      // ordinary borders
          'line-strong': '#3a3a46',
        },
        ink: {
          DEFAULT: '#e8e8ee',   // primary text
          muted: '#9a9aa8',     // labels, captions
          faint: '#60606e',     // de-emphasised, timestamps
        },
        signal: {
          self: '#FFD700',      // the person: points, level, primary action
          work: '#38bdf8',      // the corporate track — never yellow
          late: '#f87171',      // overdue, broken
          warn: '#fbbf24',      // at risk
          good: '#4ade80',      // done, kept
        },
      },
      // A rhythm, so panels stop being spaced by whatever felt right.
      spacing: {
        gutter: '1.5rem',
        section: '2rem',
      },
      // Softer corners. 4px reads as a web form; these read as hardware.
      borderRadius: {
        card: '14px',
        tile: '12px',
        chip: '8px',
      },
      // Depth instead of a 1px grey line round everything. The glow variants
      // are for the one element that is genuinely active.
      boxShadow: {
        tile: '0 1px 0 0 rgba(255,255,255,0.03) inset, 0 2px 8px -2px rgba(0,0,0,0.6)',
        lift: '0 1px 0 0 rgba(255,255,255,0.05) inset, 0 8px 24px -6px rgba(0,0,0,0.7)',
        'glow-self': '0 0 0 1px rgba(255,215,0,0.25), 0 6px 20px -6px rgba(255,215,0,0.25)',
        'glow-work': '0 0 0 1px rgba(56,189,248,0.25), 0 6px 20px -6px rgba(56,189,248,0.25)',
      },
      transitionTimingFunction: {
        // iOS-ish: quick to start, settles rather than stops.
        soft: 'cubic-bezier(0.32, 0.72, 0, 1)',
      },
      keyframes: {
        'rise-in': {
          '0%': { opacity: '0', transform: 'translateY(6px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      },
      animation: {
        'rise-in': 'rise-in 260ms cubic-bezier(0.32, 0.72, 0, 1) both',
      },
      fontFamily: {
        sans: ['Inter', 'sans-serif'],
        display: ['Bebas Neue', 'sans-serif'],
        body: ['Rajdhani', 'sans-serif'],
      },
    },
  },
  plugins: [],
}