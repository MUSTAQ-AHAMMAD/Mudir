/** Tailwind config with the Mudir brand palette (deep green + gold) and dark
 *  mode driven by a `class` on <html> (toggled by ThemeContext). */
export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        brand: {
          green: '#0d5c36',
          greenLight: '#1a7a4a',
          greenDark: '#083d24',
          gold: '#d4af37',
          goldMuted: '#c9a84c',
        },
      },
      fontFamily: {
        sans: ['Tajawal', 'system-ui', '-apple-system', 'Segoe UI', 'Roboto', 'sans-serif'],
      },
      backgroundImage: {
        // Subtle Saudi-inspired geometric pattern used behind headers/cards.
        'saudi-pattern':
          "url(\"data:image/svg+xml,%3Csvg width='40' height='40' viewBox='0 0 40 40' xmlns='http://www.w3.org/2000/svg'%3E%3Cpath d='M20 0l20 20-20 20L0 20z' fill='none' stroke='%230d5c36' stroke-opacity='0.06' stroke-width='1'/%3E%3C/svg%3E\")",
      },
      keyframes: {
        'progress-fill': {
          from: { width: '0%' },
        },
        'toast-in': {
          from: { opacity: '0', transform: 'translateY(-8px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
      },
      animation: {
        'progress-fill': 'progress-fill 0.8s ease-out',
        'toast-in': 'toast-in 0.2s ease-out',
      },
    },
  },
  plugins: [],
};
