// validators.js — lightweight form validation helpers. Return `true` when valid
// or a bilingual error string when invalid, so they plug into React Hook Form's
// `validate` option directly.

export function required(value, msg = 'هذا الحقل مطلوب / Required') {
  const ok = value !== null && value !== undefined && String(value).trim() !== '';
  return ok || msg;
}

// E.164-ish WhatsApp number, e.g. +9665XXXXXXXX.
const PHONE_RE = /^\+?[1-9]\d{7,14}$/;
export function isPhone(value, msg = 'رقم هاتف غير صالح / Invalid phone number') {
  if (!value) return true; // use with required() when mandatory
  return PHONE_RE.test(String(value).trim()) || msg;
}

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
export function isEmail(value, msg = 'بريد إلكتروني غير صالح / Invalid email') {
  if (!value) return true;
  return EMAIL_RE.test(String(value).trim()) || msg;
}

export function minLength(n, msg) {
  return (value) =>
    (value && String(value).length >= n) || msg || `الحد الأدنى ${n} أحرف / Min ${n} chars`;
}

export function maxLength(n, msg) {
  return (value) =>
    !value || String(value).length <= n || msg || `الحد الأقصى ${n} حرف / Max ${n} chars`;
}

export function isDate(value, msg = 'تاريخ غير صالح / Invalid date') {
  if (!value) return true;
  return !Number.isNaN(new Date(value).getTime()) || msg;
}

/** Validate an ISO date is not in the past. */
export function notPast(value, msg = 'يجب أن يكون التاريخ في المستقبل / Date must be in the future') {
  if (!value) return true;
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return 'تاريخ غير صالح / Invalid date';
  return d >= new Date(new Date().toDateString()) || msg;
}

/** Run a list of validators, returning the first error or true. */
export function compose(...validators) {
  return (value) => {
    for (const v of validators) {
      const result = v(value);
      if (result !== true) return result;
    }
    return true;
  };
}
