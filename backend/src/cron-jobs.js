// cron-jobs.js
// -----------------------------------------------------------------------------
// Scheduled background jobs (node-cron):
//   * 09:00 daily — send a bilingual daily summary to every team lead.
//   * hourly      — find overdue tasks; auto-escalate those overdue beyond the
//                   configured threshold to the CEO/escalation contact.
// Both jobs respect the Saudi weekend (skip Friday/Saturday by default).
//
// The scheduling and the work are separated: `dailySummaryJob` and
// `overdueEscalationJob` are plain async functions that can be invoked directly
// from tests, while `start()` wires them to cron expressions.
// -----------------------------------------------------------------------------
'use strict';

const cron = require('node-cron');
const { config } = require('./config');
const logger = require('./logger');
const { isWeekend, daysOverdue } = require('./utils');
const { t } = require('./templates');

/**
 * Send the daily summary to all team leads. Skips weekends.
 * @param {object} [deps] { db, notifier, ai, now }
 */
async function dailySummaryJob(deps = {}) {
  const db = deps.db || require('./database');
  const notifier = deps.notifier || require('./notifications');
  const ai = deps.ai || require('./ai-service');
  const now = deps.now || new Date();

  if (isWeekend(now)) {
    logger.info('Weekend — skipping daily summary');
    return { skipped: true };
  }

  const projects = await db.listProjects();
  const active = projects.filter((p) => p.status !== 'completed');
  if (active.length === 0) {
    logger.info('No active projects — skipping daily summary');
    return { skipped: true };
  }

  // Build a compact status line and, when available, an AI summary.
  const lines = active.map((p) => `• ${p.name} (${p.code}): ${p.status}`);
  let summary = lines.join('\n');
  try {
    summary = await ai.summarizeConversation(lines);
  } catch (err) {
    logger.warn({ err: err.message }, 'AI summary failed; falling back to plain list');
  }

  const leads = await db.listTeamLeads();
  await notifier.broadcast(leads.map((l) => l.whatsapp_number), t('dailySummary', summary));
  logger.info({ projects: active.length, leads: leads.length }, 'Daily summary sent');
  return { skipped: false, count: active.length };
}

/**
 * Find overdue tasks and escalate any beyond the threshold. Skips weekends.
 * @param {object} [deps] { db, notifier, now }
 */
async function overdueEscalationJob(deps = {}) {
  const db = deps.db || require('./database');
  const notifier = deps.notifier || require('./notifications');
  const now = deps.now || new Date();

  if (isWeekend(now)) {
    logger.info('Weekend — skipping overdue escalation');
    return { skipped: true };
  }

  const overdue = await db.listOverdueTasks(now);
  let escalated = 0;
  for (const task of overdue) {
    const days = daysOverdue(task.deadline, now);
    const project = task.projects || {};
    const projectName = project.name || task.project_id;

    // Warn the responsible team lead every day it's overdue.
    const lead = await db.getTeamLead(task.assigned_team);
    if (lead) {
      await notifier.sendMessage(lead.whatsapp_number, t('overdue', task.assigned_team, projectName, days));
    }

    // Auto-escalate once past the threshold.
    if (days >= config.business.escalateAfterDays && lead && lead.escalation_number) {
      await notifier.sendMessage(
        lead.escalation_number,
        t('escalation', projectName, `Task overdue by ${days} day(s): ${task.description}`),
      );
      await db.addLog(task.project_id, `Auto-escalated: ${task.assigned_team} overdue ${days}d.`);
      escalated += 1;
    }
  }
  logger.info({ overdue: overdue.length, escalated }, 'Overdue check complete');
  return { skipped: false, overdue: overdue.length, escalated };
}

/**
 * Wire the jobs to cron schedules. Call once at boot.
 * @returns {import('node-cron').ScheduledTask[]}
 */
function start() {
  const tz = config.business.timezone;
  const tasks = [];
  // 09:00 every day (job self-skips on weekend).
  tasks.push(
    cron.schedule('0 9 * * *', () => dailySummaryJob().catch((e) => logger.error(e, 'daily job failed')), {
      timezone: tz,
    }),
  );
  // Top of every hour.
  tasks.push(
    cron.schedule('0 * * * *', () => overdueEscalationJob().catch((e) => logger.error(e, 'overdue job failed')), {
      timezone: tz,
    }),
  );
  logger.info({ tz }, 'Cron jobs scheduled');
  return tasks;
}

module.exports = { start, dailySummaryJob, overdueEscalationJob };
