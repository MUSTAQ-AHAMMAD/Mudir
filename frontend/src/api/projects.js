// projects.js — project data access. Prefers Supabase tables when configured,
// otherwise falls back to the backend REST API (/api/projects).
import { supabase, isSupabaseConfigured, apiRequest } from './client';

/** List projects, optionally filtered by status. */
export async function listProjects({ status } = {}) {
  if (isSupabaseConfigured) {
    let query = supabase.from('projects').select('*').order('created_at', { ascending: false });
    if (status) query = query.eq('status', status);
    const { data, error } = await query;
    if (error) throw error;
    return data || [];
  }
  const res = await apiRequest(`/projects${status ? `?status=${encodeURIComponent(status)}` : ''}`);
  return res.projects || [];
}

/** Full project detail (project + tasks + logs) by project code. */
export async function getProject(code) {
  if (isSupabaseConfigured) {
    const { data: project, error } = await supabase
      .from('projects')
      .select('*')
      .eq('code', code)
      .single();
    if (error) throw error;
    const [{ data: tasks }, { data: logs }] = await Promise.all([
      supabase.from('tasks').select('*').eq('project_id', project.id),
      supabase
        .from('communication_logs')
        .select('*')
        .eq('project_id', project.id)
        .order('created_at', { ascending: false }),
    ]);
    return { project, tasks: tasks || [], logs: logs || [] };
  }
  return apiRequest(`/projects/${encodeURIComponent(code)}`);
}

/** Create a project (Supabase only; REST backend creates via WhatsApp). */
export async function createProject(payload) {
  if (!isSupabaseConfigured) {
    return apiRequest('/projects', { method: 'POST', body: JSON.stringify(payload) });
  }
  const { data, error } = await supabase.from('projects').insert(payload).select().single();
  if (error) throw error;
  return data;
}

/** Update a project's fields by id. */
export async function updateProject(id, patch) {
  if (!isSupabaseConfigured) {
    return apiRequest(`/projects/${id}`, { method: 'PATCH', body: JSON.stringify(patch) });
  }
  const { data, error } = await supabase.from('projects').update(patch).eq('id', id).select().single();
  if (error) throw error;
  return data;
}

/** Add a task to a project. */
export async function addTask(projectId, task) {
  if (!isSupabaseConfigured) {
    return apiRequest(`/projects/${projectId}/tasks`, { method: 'POST', body: JSON.stringify(task) });
  }
  const { data, error } = await supabase
    .from('tasks')
    .insert({ project_id: projectId, ...task })
    .select()
    .single();
  if (error) throw error;
  return data;
}
