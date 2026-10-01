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
      colors: {
        thermal: {
          950: "#0b0f19",
          900: "#111827",
          850: "#161f33",
          800: "#1f293d",
          700: "#374151",
          amber: "#f59e0b",
          flame: "#ef4444",
          infrared: "#ec4899",
          hotspot: "#ff5722",
        },
      },
    },
  },
  plugins: [],
};
