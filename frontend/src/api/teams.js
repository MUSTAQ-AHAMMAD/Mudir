// teams.js — team & team-lead data access (Supabase or REST fallback).
import { supabase, isSupabaseConfigured, apiRequest } from './client';

/** List team leads / teams. */
export async function listTeams() {
  if (isSupabaseConfigured) {
    const { data, error } = await supabase.from('team_leads').select('*').order('team_name');
    if (error) throw error;
    return data || [];
  }
  const res = await apiRequest('/team-leads');
  return res.teamLeads || [];
}

/** Create or update a team lead. */
export async function upsertTeam(lead) {
  const payload = {
    team_name: lead.team_name,
    whatsapp_number: lead.whatsapp_number,
    escalation_number: lead.escalation_number || null,
    ...(lead.name ? { name: lead.name } : {}),
  };
  if (isSupabaseConfigured) {
    const { data, error } = await supabase
      .from('team_leads')
      .upsert(payload, { onConflict: 'team_name' })
      .select()
      .single();
    if (error) throw error;
    return data;
  }
  const res = await apiRequest('/team-leads', { method: 'PUT', body: JSON.stringify(payload) });
  return res.teamLead;
}

/** Delete a team lead by id (Supabase only). */
export async function deleteTeam(id) {
  if (!isSupabaseConfigured) {
    return apiRequest(`/team-leads/${id}`, { method: 'DELETE' });
  }
  const { error } = await supabase.from('team_leads').delete().eq('id', id);
  if (error) throw error;
  return true;
}
