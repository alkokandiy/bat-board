/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        'matte-obsidian': '#1a1a1a',
        'electric-bat-yellow': '#FFD700',
        'dark-slate': '#2c2c2c',
        'bat-surface': '#08080f',
        'bat-card': '#0d0d18',
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