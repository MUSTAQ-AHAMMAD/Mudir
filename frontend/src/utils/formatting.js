// formatting.js — number, percentage and currency formatting (Arabic/English).
// Currency defaults to Saudi Riyal (SAR).

const AR = 'ar-SA';
const EN = 'en-US';

function loc(locale) {
  return locale === 'ar' ? AR : EN;
}

/** Format an integer/decimal with locale grouping. */
export function formatNumber(value, locale = 'ar', options = {}) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—';
  return new Intl.NumberFormat(loc(locale), options).format(Number(value));
}

/** Format a 0-100 (or 0-1) value as a percentage. */
export function formatPercent(value, locale = 'ar', { fromFraction = false, digits = 0 } = {}) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—';
  const n = fromFraction ? Number(value) : Number(value) / 100;
  return new Intl.NumberFormat(loc(locale), {
    style: 'percent',
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(n);
}

/** Format a currency amount (SAR by default). */
export function formatCurrency(value, locale = 'ar', currency = 'SAR') {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—';
  return new Intl.NumberFormat(loc(locale), { style: 'currency', currency }).format(Number(value));
}

/** Compact number (e.g. 12K / ١٢ ألف). */
export function formatCompact(value, locale = 'ar') {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—';
  return new Intl.NumberFormat(loc(locale), { notation: 'compact' }).format(Number(value));
}

/** Initials from a name, e.g. "Ahmed Ali" → "AA". */
export function initials(name = '') {
  const parts = String(name).trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return '?';
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

/** Title-case a snake_case or space string. */
export function titleCase(str = '') {
  return String(str)
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}
