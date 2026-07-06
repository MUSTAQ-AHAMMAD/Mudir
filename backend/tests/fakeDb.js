// tests/fakeDb.js
// -----------------------------------------------------------------------------
// In-memory implementation of the database repository interface (see
// src/database.js). Lets us exercise the state machine and command handlers
// with zero external dependencies. It mirrors the real method signatures.
// -----------------------------------------------------------------------------
'use strict';

let idSeq = 1;
const uid = () => `id-${idSeq++}`;

/**
 * Create a fresh in-memory repository. Optionally seed team leads.
 * @param {{teamLeads?: object[]}} [seed]
 */
function createFakeDb(seed = {}) {
  const projects = [];
  const tasks = [];
  const logs = [];
  const teamLeads = [...(seed.teamLeads || [])];

  return {
    _state: { projects, tasks, logs, teamLeads },

    async createProject(project) {
      const row = { id: uid(), created_at: new Date().toISOString(), metadata: {}, ...project };
      projects.push(row);
      return row;
    },
    async getProjectByCode(code) {
      return projects.find((p) => p.code === code) || null;
    },
    async updateProject(id, patch) {
      const row = projects.find((p) => p.id === id);
      Object.assign(row, patch);
      return row;
    },
    async listProjects(filter = {}) {
      let out = [...projects].reverse();
      if (filter.status) out = out.filter((p) => p.status === filter.status);
      return out;
    },
    async nextProjectCode() {
      return `P-${String(projects.length + 1).padStart(3, '0')}`;
    },

    async createTask(task) {
      const row = { id: uid(), status: 'pending', ...task };
      tasks.push(row);
      return row;
    },
    async listTasks(projectId, filter = {}) {
      let out = tasks.filter((t) => t.project_id === projectId);
      if (filter.team) out = out.filter((t) => t.assigned_team === filter.team);
      return out;
    },
    async completeTeamTasks(projectId, team) {
      const affected = tasks.filter(
        (t) => t.project_id === projectId && t.assigned_team === team && t.status !== 'done',
      );
      affected.forEach((t) => {
        t.status = 'done';
      });
      return affected;
    },
    async extendTeamDeadlines(projectId, team, days) {
      const affected = tasks.filter(
        (t) => t.project_id === projectId && t.assigned_team === team && t.status !== 'done' && t.deadline,
      );
      affected.forEach((t) => {
        const d = new Date(t.deadline);
        d.setDate(d.getDate() + days);
        t.deadline = d.toISOString().slice(0, 10);
      });
      return affected;
    },
    async listOverdueTasks(now = new Date()) {
      const today = now.toISOString().slice(0, 10);
      return tasks
        .filter((t) => t.status !== 'done' && t.deadline && t.deadline < today)
        .map((t) => ({ ...t, projects: projects.find((p) => p.id === t.project_id) }));
    },

    async getTeamLead(teamName) {
      return teamLeads.find((l) => l.team_name === teamName) || null;
    },
    async listTeamLeads() {
      return [...teamLeads];
    },
    async upsertTeamLead(lead) {
      const existing = teamLeads.find(
        (l) => l.team_name === lead.team_name && l.whatsapp_number === lead.whatsapp_number,
      );
      if (existing) {
        Object.assign(existing, lead);
        return existing;
      }
      const row = { id: uid(), ...lead };
      teamLeads.push(row);
      return row;
    },

    async addLog(projectId, message) {
      const row = { id: uid(), project_id: projectId, message, created_at: new Date().toISOString() };
      logs.push(row);
      return row;
    },
    async listLogs(projectId) {
      return logs.filter((l) => l.project_id === projectId);
    },
  };
}

/**
 * A notifier test double that records everything it "sends".
 */
function createFakeNotifier() {
  const sent = [];
  return {
    sent,
    async sendMessage(to, body) {
      sent.push({ to, body });
      return { sid: `SM-${sent.length}` };
    },
    async broadcast(recipients, body) {
      (recipients || []).forEach((to) => sent.push({ to, body }));
    },
  };
}

module.exports = { createFakeDb, createFakeNotifier };
