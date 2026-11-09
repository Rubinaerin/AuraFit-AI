/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./src/**/*.{js,jsx,ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        base: '#0B0F17', // veya projenizdeki arka plan rengi
        surface: '#151C28',
        card: {
          DEFAULT: '#1E293B',
          hover: '#334155',
        },
        border: '#334155',
        primary: {
          DEFAULT: '#6C63FF',
          hover: '#5B54E0',
        },
        accent: '#00D4AA',
        danger: '#FF5252',
        warning: '#FFB020',
        text: {
          primary: '#F8FAFC',
          secondary: '#94A3B8',
          muted: '#64748B',
        },
      },
      boxShadow: {
        card: '0 4px 20px rgba(0, 0, 0, 0.25)',
        'card-hover': '0 8px 30px rgba(0, 0, 0, 0.35)',
        'glow-primary': '0 0 20px rgba(108, 99, 255, 0.4)',
      },
      fontFamily: {
        display: ['Space Grotesk', 'sans-serif'],
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
      },
    },
  },
  plugins: [],
}