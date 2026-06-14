/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#070b07",
        panel: "#0c110c",
        panel2: "#10160f",
        panel3: "#141b12",
        line: "#1c2a1b",
        line2: "#27361f",
        dim: "#5d6f55",
        fog: "#9fb295",
        lit: "#d6e8c8",
        acid: "#c8f53b",
        neon: "#5df06a",
        amber: "#f5c542",
        danger: "#ff5d5d",
      },
      fontFamily: {
        mono: [
          '"JetBrains Mono"',
          '"Cascadia Code"',
          '"Cascadia Mono"',
          "Consolas",
          '"Courier New"',
          "monospace",
        ],
      },
      fontSize: {
        nano: ["9px", "12px"],
        micro: ["10px", "14px"],
        tiny: ["11px", "15px"],
      },
      boxShadow: {
        glow: "0 0 12px rgba(200,245,59,0.25)",
        glowGreen: "0 0 12px rgba(93,240,106,0.25)",
      },
    },
  },
  plugins: [],
};
