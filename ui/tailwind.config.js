/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        // PlantForge.ai brand violet, built around the mark's sampled #78549C.
        // brand-600 is the core; the ramp stays muted rather than vivid so it
        // matches the line-art logo instead of shouting over it.
        brand: {
          50: "#f7f3fb", 100: "#f0e8f7", 200: "#ddcbeb", 300: "#c3a9dc",
          400: "#a37fc4", 500: "#8b62b0", 600: "#7a54a0", 700: "#61407f",
          800: "#4d3364", 900: "#3d284f", 950: "#271833",
        },
        steel: {
          50: "#f0f4f8", 100: "#dbeafe", 200: "#bfdbfe", 300: "#93c5fd",
          400: "#60a5fa", 500: "#3b82f6", 600: "#2563eb", 700: "#1d4ed8",
          800: "#1e40af", 900: "#1e3a8a", 950: "#172554",
        },
      },
      fontFamily: {
        sans:    ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        display: ["Plus Jakarta Sans", "Inter", "ui-sans-serif", "sans-serif"],
        mono:    ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      boxShadow: {
        "card":    "0 1px 3px rgba(0,0,0,0.05), 0 1px 2px rgba(0,0,0,0.06)",
        "card-md": "0 4px 12px rgba(0,0,0,0.06), 0 2px 4px rgba(0,0,0,0.04)",
        "card-lg": "0 8px 24px rgba(0,0,0,0.08), 0 4px 8px rgba(0,0,0,0.04)",
        "brand":    "0 4px 14px rgba(122,84,160,0.18)",
        "brand-sm": "0 1px 4px rgba(122,84,160,0.2)",
      },
      animation: {
        "slide-up":  "slideUp 0.3s ease-out",
        "fade-in":   "fadeIn 0.2s ease-out",
        "pulse-slow":"pulse 3s ease-in-out infinite",
      },
      keyframes: {
        slideUp: {
          "0%":   { opacity: 0, transform: "translateY(6px)" },
          "100%": { opacity: 1, transform: "translateY(0)" },
        },
        fadeIn: {
          "0%":   { opacity: 0 },
          "100%": { opacity: 1 },
        },
      },
    },
  },
  plugins: [
    require("@tailwindcss/typography")
  ],
};
