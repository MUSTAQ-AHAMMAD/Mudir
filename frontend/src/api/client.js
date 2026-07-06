// client.js — Supabase client + a small REST helper for the Mudir backend.
//
// The dashboard prefers Supabase (auth + realtime + data), but many read
// endpoints are also served by the existing Node backend at /api. Both are
// supported: `supabase` is null when env vars are missing so the app can still
// run against the REST API (or mock data) during local development.
import { createClient } from '@supabase/supabase-js';

export const SUPABASE_URL = import.meta.env.VITE_SUPABASE_URL || '';
export const SUPABASE_ANON_KEY = import.meta.env.VITE_SUPABASE_ANON_KEY || '';
export const API_BASE = import.meta.env.VITE_API_URL || '';

/** True when Supabase credentials are configured. */
export const isSupabaseConfigured = Boolean(SUPABASE_URL && SUPABASE_ANON_KEY);

// A single shared client. Null when not configured (guards must check first).
export const supabase = isSupabaseConfigured
  ? createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
      auth: { persistSession: true, autoRefreshToken: true },
    })
  : null;

/**
 * REST helper for the Node backend. Base URL defaults to same-origin so the
 * Vite dev server proxy (/api → backend) works without CORS during dev.
 */
export async function apiRequest(path, options = {}) {
  const res = await fetch(`${API_BASE}/api${path}`, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  });
  if (!res.ok) {
    const message = await res.text().catch(() => '');
    throw new Error(`API ${res.status}: ${path}${message ? ` — ${message}` : ''}`);
  }
  if (res.status === 204) return null;
  return res.json();
}

export default supabase;
