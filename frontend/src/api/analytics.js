// analytics.js — aggregate metrics for the Analytics & Dashboard pages.
import { isSupabaseConfigured, apiRequest, supabase } from './client';

/**
 * Fetch analytics. The Node backend exposes a ready-made /api/analytics
 * endpoint; when running against Supabase directly we compute a lightweight
 * summary client-side from the projects table.
 */
export async function getAnalytics() {
  if (!isSupabaseConfigured) {
    return apiRequest('/analytics');
  }
  const { data: projects, error } = await supabase.from('projects').select('*');
  if (error) throw error;
  const list = projects || [];
  const completed = list.filter((p) => p.status === 'completed');
  const durations = completed
    .filter((p) => p.opening_date && p.created_at)
    .map((p) => Math.max(0, Math.round((new Date(p.opening_date) - new Date(p.created_at)) / 86_400_000)));
  const avgCompletionDays = durations.length
    ? Math.round(durations.reduce((a, b) => a + b, 0) / durations.length)
    : null;
  return {
    totals: { projects: list.length, completed: completed.length, escalations: 0 },
    avgCompletionDays,
    escalationsByProject: {},
    delaysByTeam: {},
  };
}

/** AI learning-engine insights/suggestions for the dashboard. */
export async function getInsights() {
  if (isSupabaseConfigured) {
    const { data, error } = await supabase
      .from('ai_insights')
      .select('*')
      .order('created_at', { ascending: false })
      .limit(10);
    if (error) throw error;
    return data || [];
  }
  try {
    const res = await apiRequest('/insights');
    return res.insights || [];
  } catch {
    return [];
  }
}
