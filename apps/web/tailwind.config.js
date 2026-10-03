/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  darkMode: "class",
  theme: {
    extend: {
      fontFamily: {
        mono: [
          '"JetBrains Mono"',
          '"Fira Code"',
          '"Roboto Mono"',
          '"SF Mono"',
          'Consolas',
          'monospace',
        ],
        sans: [
          'Inter',
          '-apple-system',
          'BlinkMacSystemFont',
          '"Segoe UI"',
          'Roboto',
          'sans-serif',
        ],
        display: [
          'Orbitron',
          '"Share Tech Mono"',
          'Rajdhani',
          'monospace',
        ],
      },
      colors: {
        void: '#08090d',
        surface: '#0e1017',
        elevated: '#151922',
        subtle: '#222938',
        panel: '#11141c',
        thermal: {
          950: "#08090d",
          900: "#0e1017",
          850: "#151922",
          800: "#1c2130",
          700: "#2b334a",
          amber: "#f59e0b",
          flame: "#ff5722",
          orange: "#ff6b00",
          infrared: "#ec4899",
          hotspot: "#ff3b30",
        },
        cyber: {
          cyan: "#00d4ff",
          green: "#00ff88",
          magenta: "#ff007f",
          crimson: "#ff3366",
          amber: "#ffaa00",
          muted: "#1c1c2e",
        },
      },
      boxShadow: {
        'neon-thermal': '0 0 8px rgba(255, 107, 0, 0.4), 0 0 20px rgba(255, 107, 0, 0.2)',
        'neon-cyan': '0 0 8px rgba(0, 212, 255, 0.4), 0 0 20px rgba(0, 212, 255, 0.2)',
        'neon-green': '0 0 8px rgba(0, 255, 136, 0.4), 0 0 20px rgba(0, 255, 136, 0.2)',
        'neon-red': '0 0 8px rgba(255, 51, 102, 0.4), 0 0 20px rgba(255, 51, 102, 0.2)',
        'neon-amber': '0 0 8px rgba(245, 158, 11, 0.4), 0 0 20px rgba(245, 158, 11, 0.2)',
      },
    },
  },
  plugins: [],
};

