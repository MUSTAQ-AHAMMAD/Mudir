// config.js
// -----------------------------------------------------------------------------
// Centralised configuration. All environment variables are read in exactly one
// place so the rest of the codebase never touches `process.env` directly. This
// makes the app easy to test (inject fakes) and easy to audit.
// -----------------------------------------------------------------------------
'use strict';

require('dotenv').config();

/**
 * Read an environment variable, optionally falling back to a default.
 * @param {string} key      Environment variable name.
 * @param {string} [fallback] Value to use when the variable is not set.
 * @returns {string}
 */
function env(key, fallback = undefined) {
  const value = process.env[key];
  if (value === undefined || value === '') {
    return fallback;
  }
  return value;
}

const config = {
  // Runtime
  env: env('NODE_ENV', 'development'),
  port: parseInt(env('PORT', '3000'), 10),
  logLevel: env('LOG_LEVEL', 'info'),
  // Public base URL of this service (used to build media/webhook URLs).
  publicUrl: env('PUBLIC_URL', 'http://localhost:3000'),

  // Twilio (WhatsApp Business API)
  twilio: {
    accountSid: env('TWILIO_ACCOUNT_SID'),
    authToken: env('TWILIO_AUTH_TOKEN'),
    // WhatsApp-enabled sender, e.g. "whatsapp:+14155238886" (sandbox default).
    whatsappFrom: env('TWILIO_WHATSAPP_FROM', 'whatsapp:+14155238886'),
    // When true, incoming webhook signatures are verified. Disable only in tests.
    validateSignature: env('TWILIO_VALIDATE_SIGNATURE', 'true') === 'true',
  },

  // Supabase (PostgreSQL)
  supabase: {
    url: env('SUPABASE_URL'),
    // Service-role key is required for server-side writes that bypass RLS.
    serviceKey: env('SUPABASE_SERVICE_KEY'),
  },

  // OpenAI (summaries) + Whisper (voice transcription)
  openai: {
    apiKey: env('OPENAI_API_KEY'),
    chatModel: env('OPENAI_CHAT_MODEL', 'gpt-4o-mini'),
    whisperModel: env('OPENAI_WHISPER_MODEL', 'whisper-1'),
  },

  // Business rules
  business: {
    // Saudi working week is Sunday–Thursday. 5 = Friday, 6 = Saturday (JS getDay()).
    // Reminders/escalations are skipped on these days.
    weekendDays: (env('WEEKEND_DAYS', '5,6'))
      .split(',')
      .map((d) => parseInt(d.trim(), 10))
      .filter((d) => !Number.isNaN(d)),
    // IANA timezone used for cron scheduling and "today" calculations.
    timezone: env('TIMEZONE', 'Asia/Riyadh'),
    // A task overdue by this many days is auto-escalated to the CEO.
    escalateAfterDays: parseInt(env('ESCALATE_AFTER_DAYS', '2'), 10),
    // Default number of teams for a fresh store-opening workflow.
    defaultTeamCount: parseInt(env('DEFAULT_TEAM_COUNT', '3'), 10),
  },

  // Rate limiting for the public webhook (protects against spam/abuse).
  rateLimit: {
    windowMs: parseInt(env('RATE_LIMIT_WINDOW_MS', '60000'), 10),
    max: parseInt(env('RATE_LIMIT_MAX', '60'), 10),
  },
};

/**
 * Fail fast in production when required secrets are missing.
 * In development/test we allow missing values so the app can boot with fakes.
 */
function assertProductionConfig() {
  if (config.env !== 'production') return;
  const required = [
    ['TWILIO_ACCOUNT_SID', config.twilio.accountSid],
    ['TWILIO_AUTH_TOKEN', config.twilio.authToken],
    ['SUPABASE_URL', config.supabase.url],
    ['SUPABASE_SERVICE_KEY', config.supabase.serviceKey],
    ['OPENAI_API_KEY', config.openai.apiKey],
  ];
  const missing = required.filter(([, v]) => !v).map(([k]) => k);
  if (missing.length > 0) {
    throw new Error(`Missing required environment variables: ${missing.join(', ')}`);
  }
}

module.exports = { config, assertProductionConfig };
