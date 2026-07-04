// api.js
// -----------------------------------------------------------------------------
// Lightweight JSON REST API consumed by the React admin dashboard. These
// endpoints are read-mostly and back the Projects, Analytics and Settings pages.
// Authentication/authorisation is intentionally left as a deployment concern
// (put this behind Supabase Auth / an API gateway); do NOT expose publicly as-is.
// -----------------------------------------------------------------------------
'use strict';

const express = require('express');
const logger = require('./logger');
const database = require('./database');
const { daysBetween } = require('./utils');

const router = express.Router();

/** Wrap an async route so rejected promises become 500s instead of crashes. */
const asyncRoute = (fn) => (req, res) => {
  Promise.resolve(fn(req, res)).catch((err) => {
    logger.error({ err: err.message }, 'API route failed');
    res.status(500).json({ error: 'internal_error' });
  });
};

// GET /api/projects?status=... — list projects.
router.get(
  '/projects',
  asyncRoute(async (req, res) => {
    const filter = req.query.status ? { status: String(req.query.status) } : {};
    res.json({ projects: await database.listProjects(filter) });
  }),
);

// GET /api/projects/:code — project detail with tasks + logs.
router.get(
  '/projects/:code',
  asyncRoute(async (req, res) => {
    const project = await database.getProjectByCode(req.params.code);
    if (!project) return res.status(404).json({ error: 'not_found' });
    const [tasks, logs] = await Promise.all([
      database.listTasks(project.id),
      database.listLogs(project.id),
    ]);
    return res.json({ project, tasks, logs });
  }),
);

// GET /api/team-leads — list team leads (Settings page).
router.get(
  '/team-leads',
  asyncRoute(async (req, res) => {
    res.json({ teamLeads: await database.listTeamLeads() });
  }),
);

// PUT /api/team-leads — upsert a team lead (Settings page).
router.put(
  '/team-leads',
  asyncRoute(async (req, res) => {
    const { team_name: teamName, whatsapp_number: whatsapp, escalation_number: escalation } = req.body || {};
    if (!teamName || !whatsapp) return res.status(400).json({ error: 'team_name and whatsapp_number required' });
    const lead = await database.upsertTeamLead({
      team_name: teamName,
      whatsapp_number: whatsapp,
      escalation_number: escalation || null,
    });
    return res.json({ teamLead: lead });
  }),
);

// GET /api/analytics — aggregate metrics for the Analytics page.
router.get(
  '/analytics',
  asyncRoute(async (req, res) => {
    const projects = await database.listProjects();
    const completed = projects.filter((p) => p.status === 'completed');

    // Average completion time (days) across completed projects.
    const durations = completed
      .filter((p) => p.opening_date && p.created_at)
      .map((p) => Math.max(0, daysBetween(p.created_at, p.opening_date)));
    const avgCompletionDays =
      durations.length > 0 ? Math.round(durations.reduce((a, b) => a + b, 0) / durations.length) : null;

    // Escalations per project (counted from logs).
    const escalationsByProject = {};
    let totalEscalations = 0;
    for (const project of projects) {
      const logs = await database.listLogs(project.id);
      const count = logs.filter((l) => /escalat/i.test(l.message)).length;
      escalationsByProject[project.code] = count;
      totalEscalations += count;
    }

    // Delays per team (overdue tasks grouped by team).
    const overdue = await database.listOverdueTasks(new Date());
    const delaysByTeam = {};
    for (const task of overdue) {
      delaysByTeam[task.assigned_team] = (delaysByTeam[task.assigned_team] || 0) + 1;
    }

    res.json({
      totals: {
        projects: projects.length,
        completed: completed.length,
        escalations: totalEscalations,
      },
      avgCompletionDays,
      escalationsByProject,
      delaysByTeam,
    });
  }),
);

module.exports = { router };
