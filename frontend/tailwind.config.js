/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        // Updated to match refined elevation hierarchy in :root (index.css).
        base: "#0A0E18",
        navy: "#0A0E18",
        surface: "#0F1318",
        card: "#141A23",
        cardhover: "#1C2536",
        raised: "#1C2536",
        input: "#141A23",
        accent: "#6366F1",   // indigo
        indigo: "#6366F1",
        hot: "#F59E0B",      // amber — signals only
        signal: "#F59E0B",
        success: "#10B981",  // emerald
        danger: "#EF4444",
        purple: "#8B5CF6",
        ink: "#E8EDF4",
        muted: "#7A8699",
        faint: "#4A5568",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        serif: ["Fraunces", "Georgia", "serif"],
        mono: ["'JetBrains Mono'", "monospace"],
      },
    },
  },
  plugins: [],
};
