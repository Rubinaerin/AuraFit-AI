/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./src/**/*.{js,jsx,ts,tsx}", "./public/index.html"],
  theme: {
    extend: {
      colors: {
        base:    "#0A0A0F",
        surface: "#12121A",
        card:    "#1E1E2E",
        "card-hover": "#252538",
        border:  "#2A2A3E",
        primary: {
          DEFAULT: "#6C63FF",
          dim:     "#6C63FF22",
          hover:   "#7C74FF",
        },
        accent: {
          DEFAULT: "#00D4AA",
          dim:     "#00D4AA18",
        },
        danger: {
          DEFAULT: "#FF4757",
          dim:     "#FF475718",
        },
        warning: {
          DEFAULT: "#FFB347",
          dim:     "#FFB34718",
        },
        "warning-dim": "#FFB34714",
        text: {
          primary:   "#F5F5F5",
          secondary: "#9999BB",
          muted:     "#55556A",
        },
      },
      fontFamily: {
        display: ["'Space Grotesk'", "sans-serif"],
        body:    ["'Inter'", "sans-serif"],
      },
      backgroundImage: {
        "glow-primary": "radial-gradient(ellipse at center, #6C63FF22 0%, transparent 70%)",
        "glow-accent":  "radial-gradient(ellipse at center, #00D4AA18 0%, transparent 70%)",
        "card-gradient": "linear-gradient(135deg, #1E1E2E 0%, #1A1A28 100%)",
      },
      boxShadow: {
        "glow-primary": "0 0 20px #6C63FF33",
        "glow-accent":  "0 0 20px #00D4AA22",
        "card":         "0 4px 24px rgba(0,0,0,0.4)",
        "card-hover":   "0 8px 32px rgba(0,0,0,0.6)",
      },
      animation: {
        "pulse-slow":   "pulse 3s cubic-bezier(0.4,0,0.6,1) infinite",
        "fade-in":      "fadeIn 0.3s ease-out",
        "slide-up":     "slideUp 0.4s ease-out",
        "spin-slow":    "spin 8s linear infinite",
      },
      keyframes: {
        fadeIn:  { "0%": { opacity: 0 }, "100%": { opacity: 1 } },
        slideUp: { "0%": { opacity: 0, transform: "translateY(12px)" }, "100%": { opacity: 1, transform: "translateY(0)" } },
      },
    },
  },
  plugins: [],
};
