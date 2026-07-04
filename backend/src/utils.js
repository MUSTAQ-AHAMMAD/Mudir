// utils.js
// -----------------------------------------------------------------------------
// Small, dependency-light helper functions shared across the codebase:
//   - retry logic with exponential backoff (for flaky Twilio/OpenAI calls)
//   - command parsing (turns a WhatsApp text line into a structured command)
//   - Saudi working-day helpers
//   - phone-number normalisation
// Keeping these pure (no I/O) makes them trivial to unit-test.
// -----------------------------------------------------------------------------
'use strict';

const { config } = require('./config');

/**
 * Sleep for a number of milliseconds.
 * @param {number} ms
 * @returns {Promise<void>}
 */
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

/**
 * Retry an async function with exponential backoff. Used to make external API
 * calls (Twilio, OpenAI) resilient to transient failures.
 *
 * @template T
 * @param {() => Promise<T>} fn         The operation to run.
 * @param {object} [opts]
 * @param {number} [opts.retries=3]     Number of retries after the first attempt.
 * @param {number} [opts.baseDelayMs=300] Base delay; doubles each attempt.
 * @param {(err: Error, attempt: number) => void} [opts.onRetry] Retry hook (logging).
 * @returns {Promise<T>}
 */
async function withRetry(fn, opts = {}) {
  const { retries = 3, baseDelayMs = 300, onRetry } = opts;
  let lastError;
  for (let attempt = 0; attempt <= retries; attempt += 1) {
    try {
      return await fn();
    } catch (err) {
      lastError = err;
      if (attempt === retries) break;
      if (onRetry) onRetry(err, attempt + 1);
      // Exponential backoff with a little jitter to avoid thundering herds.
      const delay = baseDelayMs * 2 ** attempt + Math.floor(Math.random() * 100);
      await sleep(delay);
    }
  }
  throw lastError;
}

/**
 * Normalise a WhatsApp / phone identifier to the E.164-ish "whatsapp:+9665..."
 * form that Twilio expects. Accepts raw numbers or already-prefixed values.
 * @param {string} number
 * @returns {string}
 */
function normalizeWhatsApp(number) {
  if (!number) return number;
  let n = String(number).trim();
  if (n.startsWith('whatsapp:')) n = n.slice('whatsapp:'.length);
  n = n.replace(/[\s()-]/g, '');
  if (!n.startsWith('+')) n = `+${n}`;
  return `whatsapp:${n}`;
}

// Recognised slash commands and how to extract their arguments.
// Each entry returns a structured payload consumed by the command router.
const COMMAND_PATTERNS = [
  {
    name: 'new_project',
    // /new_project Riyadh Mall Store #342
    regex: /^\/new_project\s+(.+)$/i,
    parse: (m) => ({ name: m[1].trim() }),
  },
  {
    name: 'assign',
    // /assign marketing "design banners" 2026-07-10
    regex: /^\/assign\s+(\S+)\s+(?:"([^"]+)"|(\S+))\s+(\d{4}-\d{2}-\d{2})$/i,
    parse: (m) => ({ team: m[1].toLowerCase(), task: (m[2] || m[3]).trim(), deadline: m[4] }),
  },
  {
    name: 'complete',
    // /complete P-001
    regex: /^\/complete\s+(\S+)$/i,
    parse: (m) => ({ projectId: m[1].trim() }),
  },
  {
    name: 'extend',
    // /extend P-001 marketing 3
    regex: /^\/extend\s+(\S+)\s+(\S+)\s+(\d+)$/i,
    parse: (m) => ({ projectId: m[1].trim(), team: m[2].toLowerCase(), days: parseInt(m[3], 10) }),
  },
  {
    name: 'status',
    // /status P-001
    regex: /^\/status\s+(\S+)$/i,
    parse: (m) => ({ projectId: m[1].trim() }),
  },
  {
    name: 'escalate',
    // /escalate P-001 site not ready
    regex: /^\/escalate\s+(\S+)\s+(.+)$/i,
    parse: (m) => ({ projectId: m[1].trim(), reason: m[2].trim() }),
  },
  {
    name: 'help',
    regex: /^\/help\s*$/i,
    parse: () => ({}),
  },
];

/**
 * Parse a raw WhatsApp text body into a structured command.
 * @param {string} body Raw message text.
 * @returns {{name: string, args: object}|null} Null when no command matches.
 */
function parseCommand(body) {
  if (!body) return null;
  const line = body.trim();
  for (const pattern of COMMAND_PATTERNS) {
    const match = line.match(pattern.regex);
    if (match) {
      return { name: pattern.name, args: pattern.parse(match) };
    }
  }
  return null;
}

/**
 * Is the given date a Saudi weekend day (Friday/Saturday by default)?
 * @param {Date} [date=new Date()]
 * @returns {boolean}
 */
function isWeekend(date = new Date()) {
  return config.business.weekendDays.includes(date.getDay());
}

/**
 * Whole-day difference between two dates (b - a), rounded down.
 * Positive result means `b` is later than `a`.
 * @param {Date|string} a
 * @param {Date|string} b
 * @returns {number}
 */
function daysBetween(a, b) {
  const msPerDay = 24 * 60 * 60 * 1000;
  const da = a instanceof Date ? a : new Date(a);
  const db = b instanceof Date ? b : new Date(b);
  return Math.floor((db.getTime() - da.getTime()) / msPerDay);
}

/**
 * Number of days a deadline is overdue relative to `now`. 0 when not overdue.
 * @param {Date|string} deadline
 * @param {Date} [now=new Date()]
 * @returns {number}
 */
function daysOverdue(deadline, now = new Date()) {
  const diff = daysBetween(deadline, now);
  return diff > 0 ? diff : 0;
}

module.exports = {
  sleep,
  withRetry,
  normalizeWhatsApp,
  parseCommand,
  isWeekend,
  daysBetween,
  daysOverdue,
  COMMAND_PATTERNS,
};
