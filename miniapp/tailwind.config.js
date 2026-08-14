/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      // index.css maps Telegram's theme params onto these variables. Wiring
      // them into the palette is what makes them usable: previously the body
      // took Telegram's text colour while every card was hardcoded bg-white,
      // so in dark mode student names and typed text were white on white.
      colors: {
        tg: {
          bg: "var(--tg-bg)",
          text: "var(--tg-text)",
          hint: "var(--tg-hint)",
          link: "var(--tg-link)",
          button: "var(--tg-button)",
          buttonText: "var(--tg-button-text)",
          secondaryBg: "var(--tg-secondary-bg)",
        },
      },
      minHeight: { 11: "2.75rem" },
      minWidth: { 11: "2.75rem" },
    },
  },
  plugins: [],
};
