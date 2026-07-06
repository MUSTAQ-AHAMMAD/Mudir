// colors.js — status → Tailwind class maps and helpers shared across badges,
// cards and charts. Keeps colour decisions in one place.
import { STATUS_COLORS } from '../styles/themes';

// Tailwind utility classes per status (badges).
export const STATUS_BADGE_CLASSES = {
  property_pending: 'bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-200',
  marketing_pending: 'bg-orange-100 text-orange-800 dark:bg-orange-900/40 dark:text-orange-200',
  it_pending: 'bg-purple-100 text-purple-800 dark:bg-purple-900/40 dark:text-purple-200',
  ready: 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-200',
  completed: 'bg-gray-200 text-gray-700 dark:bg-white/10 dark:text-gray-200',
  overdue: 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-200',
  delayed: 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-200',
  at_risk: 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200',
  on_track: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-200',
  done: 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-200',
  in_progress: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/40 dark:text-yellow-200',
  pending: 'bg-gray-100 text-gray-600 dark:bg-white/10 dark:text-gray-300',
  blocked: 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-200',
};

export function badgeClass(status) {
  return STATUS_BADGE_CLASSES[status] || 'bg-gray-100 text-gray-600 dark:bg-white/10 dark:text-gray-300';
}

// Tailwind background classes for progress bars keyed by health.
export const HEALTH_BAR_CLASSES = {
  on_track: 'bg-brand-greenLight',
  at_risk: 'bg-brand-gold',
  delayed: 'bg-red-500',
  completed: 'bg-brand-green',
};

export function healthBarClass(health) {
  return HEALTH_BAR_CLASSES[health] || 'bg-brand-green';
}

/** Hex colour for a health/status key (charts, inline styles). */
export function statusHex(key) {
  return STATUS_COLORS[key] || '#0d5c36';
}

// Deterministic avatar background from a string (team member initials, etc.).
const AVATAR_COLORS = ['#0d5c36', '#1a7a4a', '#d4af37', '#2563eb', '#7c3aed', '#0891b2', '#db2777'];
export function avatarColor(seed = '') {
  let hash = 0;
  for (let i = 0; i < seed.length; i += 1) hash = (hash * 31 + seed.charCodeAt(i)) >>> 0;
  return AVATAR_COLORS[hash % AVATAR_COLORS.length];
}
