// themes.js — theme configuration and brand palette shared with JS (charts,
// inline styles) so we don't hardcode hex values across the app.

export const BRAND = {
  green: '#0d5c36',
  greenLight: '#1a7a4a',
  greenDark: '#083d24',
  gold: '#d4af37',
  goldMuted: '#c9a84c',
  white: '#ffffff',
};

// Semantic status colours (used by StatusBadge, charts, progress bars).
export const STATUS_COLORS = {
  on_track: '#1a7a4a',
  at_risk: '#d4af37',
  delayed: '#dc2626',
  completed: '#4b5563',
  ready: '#0d5c36',
};

export const THEMES = {
  light: {
    name: 'light',
    bg: '#f9fafb',
    surface: '#ffffff',
    text: '#1f2937',
    grid: 'rgba(0,0,0,0.08)',
  },
  dark: {
    name: 'dark',
    bg: '#083d24',
    surface: 'rgba(255,255,255,0.05)',
    text: '#f3f4f6',
    grid: 'rgba(255,255,255,0.12)',
  },
};

// Ordered palette for charts with multiple series.
export const CHART_PALETTE = [
  BRAND.green,
  BRAND.gold,
  BRAND.greenLight,
  '#2563eb',
  '#dc2626',
  '#7c3aed',
  '#0891b2',
];

export default THEMES;
