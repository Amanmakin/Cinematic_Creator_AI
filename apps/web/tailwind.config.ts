import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        surface: "#1e1e23",
        panel: "#18181b",
        border: "#3f3f46",
        accent: "#818cf8",
        "accent-hover": "#6366f1",
      },
    },
  },
  plugins: [],
};

export default config;
