// database.js
// -----------------------------------------------------------------------------
// Data-access layer. Every SQL/Supabase interaction lives here so the rest of
// the app talks to a small, well-typed repository interface. This is what makes
// the state machine and command handlers unit-testable: tests can pass an
// in-memory repository with the same shape (see tests/fakeDb.js).
// -----------------------------------------------------------------------------
'use strict';

const { getSupabase } = require('./supabaseClient');

/**
 * Throw if a Supabase response contains an error.
 * @param {{error: any}} res
 * @param {string} context
 */
function assertOk(res, context) {
  if (res.error) {
    const err = new Error(`DB error (${context}): ${res.error.message}`);
    err.cause = res.error;
    throw err;
  }
  return res;
}

const database = {
  // ----- projects ----------------------------------------------------------

  /**
   * Create a new project.
   * @param {object} project
   * @returns {Promise<object>} The inserted project row.
   */
  async createProject(project) {
    const res = assertOk(
      await getSupabase().from('projects').insert(project).select().single(),
      'createProject',
    );
    return res.data;
  },

  /**
   * Look up a project by its human-friendly code (e.g. "P-001").
   * @param {string} code
   * @returns {Promise<object|null>}
   */
  async getProjectByCode(code) {
    const res = assertOk(
      await getSupabase().from('projects').select('*').eq('code', code).maybeSingle(),
      'getProjectByCode',
    );
    return res.data;
  },

  /**
   * Update a project by id and return the updated row.
   * @param {string} id
   * @param {object} patch
   * @returns {Promise<object>}
   */
  async updateProject(id, patch) {
    const res = assertOk(
      await getSupabase().from('projects').update(patch).eq('id', id).select().single(),
      'updateProject',
    );
    return res.data;
  },

  /**
   * List all projects (optionally filtered by status).
   * @param {{status?: string}} [filter]
   * @returns {Promise<object[]>}
   */
  async listProjects(filter = {}) {
    let query = getSupabase().from('projects').select('*').order('created_at', { ascending: false });
    if (filter.status) query = query.eq('status', filter.status);
    const res = assertOk(await query, 'listProjects');
    return res.data;
  },

  /**
   * Generate the next sequential project code ("P-001", "P-002", ...).
   * @returns {Promise<string>}
   */
  async nextProjectCode() {
    const res = assertOk(
      await getSupabase()
        .from('projects')
        .select('code')
        .order('created_at', { ascending: false })
        .limit(1),
      'nextProjectCode',
    );
    const last = res.data && res.data[0];
    const lastNum = last ? parseInt(String(last.code).replace(/[^0-9]/g, ''), 10) || 0 : 0;
    return `P-${String(lastNum + 1).padStart(3, '0')}`;
  },

  // ----- tasks -------------------------------------------------------------

  /**
   * Create a task for a project.
   * @param {object} task
   * @returns {Promise<object>}
   */
  async createTask(task) {
    const res = assertOk(
      await getSupabase().from('tasks').insert(task).select().single(),
      'createTask',
    );
    return res.data;
  },

  /**
   * List tasks for a project, optionally filtered by team.
   * @param {string} projectId
   * @param {{team?: string}} [filter]
   * @returns {Promise<object[]>}
   */
  async listTasks(projectId, filter = {}) {
    let query = getSupabase().from('tasks').select('*').eq('project_id', projectId);
    if (filter.team) query = query.eq('assigned_team', filter.team);
    const res = assertOk(await query.order('created_at', { ascending: true }), 'listTasks');
    return res.data;
  },

  /**
   * Mark all of a team's tasks on a project as done. Returns affected rows.
   * @param {string} projectId
   * @param {string} team
   * @returns {Promise<object[]>}
   */
  async completeTeamTasks(projectId, team) {
    const res = assertOk(
      await getSupabase()
        .from('tasks')
        .update({ status: 'done' })
        .eq('project_id', projectId)
        .eq('assigned_team', team)
        .neq('status', 'done')
        .select(),
      'completeTeamTasks',
    );
    return res.data;
  },

  /**
   * Extend the deadline of a team's open tasks by N days.
   * @param {string} projectId
   * @param {string} team
   * @param {number} days
   * @returns {Promise<object[]>}
   */
  async extendTeamDeadlines(projectId, team, days) {
    const tasks = await this.listTasks(projectId, { team });
    const updated = [];
    for (const task of tasks) {
      if (task.status === 'done' || !task.deadline) continue;
      const newDeadline = new Date(task.deadline);
      newDeadline.setDate(newDeadline.getDate() + days);
      const res = assertOk(
        await getSupabase()
          .from('tasks')
          .update({ deadline: newDeadline.toISOString().slice(0, 10) })
          .eq('id', task.id)
          .select()
          .single(),
        'extendTeamDeadlines',
      );
      updated.push(res.data);
    }
    return updated;
  },

  /**
   * All open (not done) tasks with a deadline in the past.
   * @param {Date} [now=new Date()]
   * @returns {Promise<object[]>}
   */
  async listOverdueTasks(now = new Date()) {
    const today = now.toISOString().slice(0, 10);
    const res = assertOk(
      await getSupabase()
        .from('tasks')
        .select('*, projects(code, name)')
        .neq('status', 'done')
        .lt('deadline', today),
      'listOverdueTasks',
    );
    return res.data;
  },

  // ----- team_leads --------------------------------------------------------

  /**
   * Get a team lead by team name.
   * @param {string} teamName
   * @returns {Promise<object|null>}
   */
  async getTeamLead(teamName) {
    const res = assertOk(
      await getSupabase().from('team_leads').select('*').eq('team_name', teamName).maybeSingle(),
      'getTeamLead',
    );
    return res.data;
  },

  /**
   * List all team leads.
   * @returns {Promise<object[]>}
   */
  async listTeamLeads() {
    const res = assertOk(await getSupabase().from('team_leads').select('*'), 'listTeamLeads');
    return res.data;
  },

  /**
   * Upsert a team lead (create or update by team_name).
   * @param {object} lead
   * @returns {Promise<object>}
   */
  async upsertTeamLead(lead) {
    const res = assertOk(
      await getSupabase()
        .from('team_leads')
        .upsert(lead, { onConflict: 'team_name,whatsapp_number' })
        .select()
        .single(),
      'upsertTeamLead',
    );
    return res.data;
  },

  // ----- project_logs ------------------------------------------------------

  /**
   * Append a log line to a project's audit trail.
   * @param {string} projectId
   * @param {string} message
   * @returns {Promise<object>}
   */
  async addLog(projectId, message) {
    const res = assertOk(
      await getSupabase().from('project_logs').insert({ project_id: projectId, message }).select().single(),
      'addLog',
    );
    return res.data;
  },

  /**
   * List a project's logs (oldest first).
   * @param {string} projectId
   * @returns {Promise<object[]>}
   */
  async listLogs(projectId) {
    const res = assertOk(
      await getSupabase()
        .from('project_logs')
        .select('*')
        .eq('project_id', projectId)
        .order('created_at', { ascending: true }),
      'listLogs',
    );
    return res.data;
  },
};

module.exports = database;
