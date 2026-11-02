/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // --- original palette, kept so nothing breaks mid-migration -------
        'matte-obsidian': '#1a1a1a',
        'electric-bat-yellow': '#FFD700',
        'dark-slate': '#2c2c2c',
        'bat-surface': '#08080f',
        'bat-card': '#0d0d18',

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
      fontFamily: {
        sans: ['Inter', 'sans-serif'],
        display: ['Bebas Neue', 'sans-serif'],
        body: ['Rajdhani', 'sans-serif'],
      },
    },
  },
  plugins: [],
}