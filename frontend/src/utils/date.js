// date.js — bilingual (Arabic / English) date & duration formatting helpers.
// Uses Intl so no extra dependency is required. Defaults to the Riyadh locale
// conventions but accepts an explicit locale.

const AR = 'ar-SA';
const EN = 'en-US';

/** Resolve a Date from a Date | ISO string | timestamp. Returns null if invalid. */
export function toDate(value) {
  if (!value) return null;
  const d = value instanceof Date ? value : new Date(value);
  return Number.isNaN(d.getTime()) ? null : d;
}

/** Format a date, e.g. "5 يوليو 2026" (ar) or "Jul 5, 2026" (en). */
export function formatDate(value, locale = 'ar') {
  const d = toDate(value);
  if (!d) return '—';
  return new Intl.DateTimeFormat(locale === 'ar' ? AR : EN, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  }).format(d);
}

/** Format a date & time. */
export function formatDateTime(value, locale = 'ar') {
  const d = toDate(value);
  if (!d) return '—';
  return new Intl.DateTimeFormat(locale === 'ar' ? AR : EN, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(d);
}

/** Whole days between two dates (b - a), rounded down. */
export function daysBetween(a, b) {
  const da = toDate(a);
  const db = toDate(b);
  if (!da || !db) return 0;
  return Math.floor((db.getTime() - da.getTime()) / 86_400_000);
}

/** Days from now until `value` (negative = overdue). */
export function daysRemaining(value) {
  const d = toDate(value);
  if (!d) return null;
  return daysBetween(new Date(), d);
}

/** Human "days remaining" label, bilingual. */
export function daysRemainingLabel(value, locale = 'ar') {
  const days = daysRemaining(value);
  if (days === null) return '—';
  if (locale === 'ar') {
    if (days < 0) return `متأخر ${Math.abs(days)} يوم`;
    if (days === 0) return 'اليوم';
    return `${days} يوم متبقٍ`;
  }
  if (days < 0) return `${Math.abs(days)}d overdue`;
  if (days === 0) return 'Today';
  return `${days}d left`;
}

/** Relative time like "منذ ٣ ساعات" / "3 hours ago". */
export function timeAgo(value, locale = 'ar') {
  const d = toDate(value);
  if (!d) return '—';
  const rtf = new Intl.RelativeTimeFormat(locale === 'ar' ? AR : EN, { numeric: 'auto' });
  const diffMs = d.getTime() - Date.now();
  const units = [
    ['year', 31_536_000_000],
    ['month', 2_592_000_000],
    ['day', 86_400_000],
    ['hour', 3_600_000],
    ['minute', 60_000],
  ];
  for (const [unit, ms] of units) {
    if (Math.abs(diffMs) >= ms || unit === 'minute') {
      return rtf.format(Math.round(diffMs / ms), unit);
    }
  }
  return rtf.format(0, 'minute');
}
