// lib/api.js
// Tiny fetch wrapper for the Mudir backend REST API. All dashboard data access
// goes through here. Base URL defaults to same-origin (dev server proxies /api).
const BASE = import.meta.env.VITE_API_BASE || '';

async function request(path, options = {}) {
  const res = await fetch(`${BASE}/api${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) throw new Error(`API ${res.status}: ${path}`);
  return res.json();
}

export const api = {
  listProjects: (status) => request(`/projects${status ? `?status=${status}` : ''}`),
  getProject: (code) => request(`/projects/${code}`),
  listTeamLeads: () => request('/team-leads'),
  upsertTeamLead: (lead) => request('/team-leads', { method: 'PUT', body: JSON.stringify(lead) }),
  analytics: () => request('/analytics'),
};
