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
      },
      boxShadow: {
        'subtle': '0 1px 2px 0 rgba(0, 0, 0, 0.05)',
        'elevated': '0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06)',
      },
    },
  },
  plugins: [],
};

