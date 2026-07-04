/** Tailwind config with the Mudir brand palette (deep green + gold). */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        brand: {
          green: '#0d5c36',
          greenLight: '#1a7a4a',
          gold: '#d4af37',
          goldMuted: '#c9a84c',
        },
      },
    },
  },
  plugins: [],
};
