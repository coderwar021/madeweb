/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Noto Sans SC", "Noto Sans JP", "ui-sans-serif", "sans-serif"],
        serif: ["Fraunces", "Songti SC", "serif"],
      },
      colors: {
        ink: "#12110f",
        paper: "#f3efe6",
        ember: "#ff4d2e",
      },
    },
  },
  plugins: [],
};
