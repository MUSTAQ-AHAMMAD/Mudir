// supabaseClient.js
// -----------------------------------------------------------------------------
// Lazily creates a single Supabase client using the service-role key so the
// backend can read/write regardless of row-level-security policies.
// The client is created on first use to avoid throwing during tests that never
// touch the database.
// -----------------------------------------------------------------------------
'use strict';

const { createClient } = require('@supabase/supabase-js');
const { config } = require('./config');
const logger = require('./logger');

let client = null;

/**
 * Get the shared Supabase client, creating it on first call.
 * @returns {import('@supabase/supabase-js').SupabaseClient}
 */
function getSupabase() {
  if (client) return client;
  if (!config.supabase.url || !config.supabase.serviceKey) {
    throw new Error('Supabase is not configured (SUPABASE_URL / SUPABASE_SERVICE_KEY).');
  }
  client = createClient(config.supabase.url, config.supabase.serviceKey, {
    auth: { persistSession: false, autoRefreshToken: false },
  });
  logger.debug('Supabase client initialised');
  return client;
}

module.exports = { getSupabase };
