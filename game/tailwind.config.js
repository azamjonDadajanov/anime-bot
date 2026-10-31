/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        game: {
          dark: '#0f172a',
          card: '#1e293b',
          accent: '#f59e0b',
          gold: '#fbbf24',
          anime: '#ec4899',
        }
      }
    },
  },
  plugins: [],
}
