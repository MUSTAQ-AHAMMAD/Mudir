// workflows.js — workflow definitions and AI-discovered workflow suggestions.
// Backend support may be partial; functions degrade gracefully to empty lists.
import { supabase, isSupabaseConfigured, apiRequest } from './client';

/** List saved workflow definitions. */
export async function listWorkflows() {
  if (isSupabaseConfigured) {
    const { data, error } = await supabase.from('workflows').select('*').order('created_at', {
      ascending: false,
    });
    if (error) throw error;
    return data || [];
  }
  try {
    const res = await apiRequest('/workflows');
    return res.workflows || [];
  } catch {
    return [];
  }
}

/** List AI-discovered workflow suggestions (with confidence scores). */
export async function listWorkflowSuggestions() {
  if (isSupabaseConfigured) {
    const { data, error } = await supabase
      .from('workflow_suggestions')
      .select('*')
      .order('confidence', { ascending: false });
    if (error) throw error;
    return data || [];
  }
  try {
    const res = await apiRequest('/workflows/suggestions');
    return res.suggestions || [];
  } catch {
    return [];
  }
}

/** Persist a new/edited workflow. */
export async function saveWorkflow(workflow) {
  if (isSupabaseConfigured) {
    const { data, error } = await supabase.from('workflows').upsert(workflow).select().single();
    if (error) throw error;
    return data;
  }
  const res = await apiRequest('/workflows', { method: 'POST', body: JSON.stringify(workflow) });
  return res.workflow || workflow;
}

/** Accept or reject an AI workflow suggestion. */
export async function resolveSuggestion(id, accepted) {
  if (isSupabaseConfigured) {
    const { data, error } = await supabase
      .from('workflow_suggestions')
      .update({ status: accepted ? 'accepted' : 'rejected' })
      .eq('id', id)
      .select()
      .single();
    if (error) throw error;
    return data;
  }
  return apiRequest(`/workflows/suggestions/${id}`, {
    method: 'PATCH',
    body: JSON.stringify({ status: accepted ? 'accepted' : 'rejected' }),
  });
}
