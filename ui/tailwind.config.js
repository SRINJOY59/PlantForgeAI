/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        steel: {
          50: "#f2f6fa", 100: "#e2ebf3", 200: "#c5d7e6", 300: "#9bb8d1",
          400: "#6a92b6", 500: "#47739c", 600: "#375c82", 700: "#2e4b6a",
          800: "#294059", 900: "#26374b", 950: "#182433",
        },
      },
      fontFamily: {
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
    },
  },
  plugins: [],
};
