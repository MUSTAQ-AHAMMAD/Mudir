// settings.js — system settings & WhatsApp integration status.
// Settings are largely server-configured (env vars); these endpoints surface
// what can be read/written from the dashboard. All calls degrade gracefully.
import { isSupabaseConfigured, apiRequest, supabase } from './client';

const DEFAULT_SETTINGS = {
  ai_model: 'gpt-4o-mini',
  working_days: { Sun: true, Mon: true, Tue: true, Wed: true, Thu: true, Fri: false, Sat: false },
  escalate_after_days: 2,
  timezone: 'Asia/Riyadh',
  notifications: { email: true, whatsapp: true, daily_summary: true },
};

/** Read system settings, falling back to sensible defaults. */
export async function getSettings() {
  if (isSupabaseConfigured) {
    const { data, error } = await supabase.from('settings').select('*').limit(1).maybeSingle();
    if (error) throw error;
    return { ...DEFAULT_SETTINGS, ...(data || {}) };
  }
  try {
    const res = await apiRequest('/settings');
    return { ...DEFAULT_SETTINGS, ...(res.settings || res) };
  } catch {
    return { ...DEFAULT_SETTINGS };
  }
}

/** Persist system settings. */
export async function saveSettings(settings) {
  if (isSupabaseConfigured) {
    const { data, error } = await supabase.from('settings').upsert(settings).select().single();
    if (error) throw error;
    return data;
  }
  const res = await apiRequest('/settings', { method: 'PUT', body: JSON.stringify(settings) });
  return res.settings || settings;
}

/** WhatsApp / WATI integration status for the WhatsAppSettings page. */
export async function getWhatsAppStatus() {
  try {
    const res = await apiRequest('/whatsapp/status');
    return res;
  } catch {
    return { connected: false, provider: 'unknown', webhook: 'unknown', groups: [] };
  }
}

/** Send a WhatsApp test message. */
export async function sendTestMessage({ to, message }) {
  return apiRequest('/whatsapp/test', {
    method: 'POST',
    body: JSON.stringify({ to, message }),
  });
}
