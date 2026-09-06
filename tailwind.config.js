/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ["class", '[data-theme="dark"]'],
  theme: {
    extend: {
      colors: {
        background: "var(--bg)",
        foreground: "var(--text)",
        card: "var(--surface)",
        muted: "var(--muted)",
        border: "var(--border)",
        primary: "var(--primary)",
        secondary: "var(--secondary)",
        destructive: "var(--danger)",
        warning: "var(--warning)",
      },
      fontFamily: {
        sans: ["Inter", "Segoe UI", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "Cascadia Mono", "Consolas", "monospace"],
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
    },
  },
  plugins: [],
};
