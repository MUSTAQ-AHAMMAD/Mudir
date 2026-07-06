// commands.js
// -----------------------------------------------------------------------------
// Command handlers. Each handler takes the parsed command args plus the sender,
// performs the business action, and returns a reply string to send back over
// WhatsApp. Dependencies (db, state machine, notifier) are injected so the
// handlers can be unit-tested against an in-memory repository.
// -----------------------------------------------------------------------------
'use strict';

const database = require('./database');
const notifications = require('./notifications');
const stateMachine = require('./state-machine');
const { t } = require('./templates');
const logger = require('./logger');

/**
 * Build the dependency bundle, defaulting to the real modules.
 * @param {object} [deps]
 */
function resolveDeps(deps = {}) {
  return {
    db: deps.db || database,
    notifier: deps.notifier || notifications,
    sm: deps.sm || stateMachine,
  };
}

/**
 * /new_project [name] — create a project, seed the first team's turn, notify.
 * @returns {Promise<string>} Reply text.
 */
async function handleNewProject(args, sender, deps = {}) {
  const { db, notifier, sm } = resolveDeps(deps);
  const workflow = sm.WORKFLOW;
  const firstTeam = workflow[0];
  const code = await db.nextProjectCode();
  const project = await db.createProject({
    code,
    name: args.name,
    status: sm.stateForTeam(firstTeam),
    current_team: firstTeam,
    metadata: { workflow },
  });
  await db.addLog(project.id, `Project created by ${sender}.`);

  // Notify the first team lead it's their turn.
  const lead = await db.getTeamLead(firstTeam);
  if (lead) {
    await notifier.sendMessage(lead.whatsapp_number, t('teamNotified', firstTeam, project.name));
  }
  logger.info({ code, name: args.name }, 'Project created');
  return t('projectCreated', code, project.name, firstTeam);
}

/**
 * /assign [team] [task] [deadline] — add a task to a project.
 * The project is inferred from the most recent project the sender interacts
 * with; callers may also pass `args.projectCode`.
 * @returns {Promise<string>}
 */
async function handleAssign(args, sender, deps = {}) {
  const { db } = resolveDeps(deps);
  // Assign to the newest project when no explicit code is provided.
  const projects = await db.listProjects();
  const project = args.projectCode
    ? await db.getProjectByCode(args.projectCode)
    : projects[0];
  if (!project) return '❌ No project found to assign to. / لا يوجد مشروع.';
  const task = await db.createTask({
    project_id: project.id,
    assigned_team: args.team,
    description: args.task,
    deadline: args.deadline,
    status: 'pending',
  });
  await db.addLog(project.id, `Task assigned to ${args.team}: ${args.task} (due ${args.deadline}).`);
  return t('taskAssigned', args.team, task.description, args.deadline);
}

/**
 * /complete [project_id] — the sender's team completes their tasks; the state
 * machine transitions the project and notifies the next team.
 * @returns {Promise<string>}
 */
async function handleComplete(args, sender, deps = {}) {
  const { db, sm } = resolveDeps(deps);
  const project = await db.getProjectByCode(args.projectId);
  if (!project) return `❌ Project ${args.projectId} not found. / المشروع غير موجود.`;

  const team = sm.teamForState(project.status);
  if (!team) {
    return t('projectReady', project.name);
  }
  const result = await sm.completeCurrentTeam({ project, team }, deps);
  if (!result.transitioned) {
    return `⏳ Cannot complete right now (${result.blocked && result.blocked.reason}).`;
  }
  if (result.to === sm.READY) {
    return t('projectReady', project.name);
  }
  return t('teamCompleted', team, project.name);
}

/**
 * /extend [project_id] [team] [days] — request a deadline extension. Extends
 * the team's open task deadlines and alerts the escalation contact (CEO) for
 * awareness/approval.
 * @returns {Promise<string>}
 */
async function handleExtend(args, sender, deps = {}) {
  const { db, notifier } = resolveDeps(deps);
  const project = await db.getProjectByCode(args.projectId);
  if (!project) return `❌ Project ${args.projectId} not found. / المشروع غير موجود.`;

  await db.extendTeamDeadlines(project.id, args.team, args.days);
  await db.addLog(project.id, `${sender} requested +${args.days}d extension for ${args.team}.`);

  // Notify the escalation contact for approval/awareness.
  const lead = await db.getTeamLead(args.team);
  const escalationTo = lead && lead.escalation_number;
  if (escalationTo) {
    await notifier.sendMessage(escalationTo, t('extensionRequested', project.name, args.team, args.days));
  }
  return t('extensionRequested', project.name, args.team, args.days);
}

/**
 * /status [project_id] — produce a timeline report of the project.
 * @returns {Promise<string>}
 */
async function handleStatus(args, sender, deps = {}) {
  const { db } = resolveDeps(deps);
  const project = await db.getProjectByCode(args.projectId);
  if (!project) return `❌ Project ${args.projectId} not found. / المشروع غير موجود.`;

  const tasks = await db.listTasks(project.id);
  const icon = { done: '✅', in_progress: '🔄', pending: '⏳', blocked: '⛔' };
  const lines = tasks.map(
    (task) =>
      `${icon[task.status] || '•'} [${task.assigned_team}] ${task.description}` +
      (task.deadline ? ` (🗓️ ${task.deadline})` : ''),
  );
  const header =
    `📊 *${project.name}* (${project.code})\n` +
    `الحالة/Status: *${project.status}*\n` +
    (project.opening_date ? `🏬 Opening: ${project.opening_date}\n` : '');
  return `${header}\n${lines.join('\n') || 'No tasks yet. / لا توجد مهام.'}`;
}

/**
 * /escalate [project_id] [reason] — send an urgent alert to the escalation
 * contact (CEO) for the project's current team.
 * @returns {Promise<string>}
 */
async function handleEscalate(args, sender, deps = {}) {
  const { db, notifier, sm } = resolveDeps(deps);
  const project = await db.getProjectByCode(args.projectId);
  if (!project) return `❌ Project ${args.projectId} not found. / المشروع غير موجود.`;

  const team = sm.teamForState(project.status);
  const lead = team ? await db.getTeamLead(team) : null;
  const escalationTo = lead && lead.escalation_number;
  await db.addLog(project.id, `ESCALATION by ${sender}: ${args.reason}`);
  if (escalationTo) {
    await notifier.sendMessage(escalationTo, t('escalation', project.name, args.reason));
  }
  logger.warn({ project: project.code, reason: args.reason }, 'Escalation raised');
  return t('escalation', project.name, args.reason);
}

/**
 * /help — list available commands.
 * @returns {Promise<string>}
 */
async function handleHelp() {
  return t('help');
}

// Router table: command name -> handler.
const HANDLERS = {
  new_project: handleNewProject,
  assign: handleAssign,
  complete: handleComplete,
  extend: handleExtend,
  status: handleStatus,
  escalate: handleEscalate,
  help: handleHelp,
};

/**
 * Dispatch a parsed command to its handler.
 * @param {{name: string, args: object}} command
 * @param {string} sender WhatsApp id of the sender.
 * @param {object} [deps]
 * @returns {Promise<string>} Reply text (falls back to "unknown" template).
 */
async function dispatch(command, sender, deps = {}) {
  if (!command || !HANDLERS[command.name]) return t('unknown');
  return HANDLERS[command.name](command.args, sender, deps);
}

module.exports = {
  handleNewProject,
  handleAssign,
  handleComplete,
  handleExtend,
  handleStatus,
  handleEscalate,
  handleHelp,
  dispatch,
  HANDLERS,
};
