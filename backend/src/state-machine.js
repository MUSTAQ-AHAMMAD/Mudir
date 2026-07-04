// state-machine.js
// -----------------------------------------------------------------------------
// The project state machine. Projects move through a strict, sequential set of
// team-owned states:
//
//   property_pending -> marketing_pending -> it_pending -> ready -> completed
//
// Design notes:
//   * The core transition logic (nextState / stateForTeam / teamForState) is
//     PURE — no I/O — so it is trivially unit-testable.
//   * `completeCurrentTeam` orchestrates the side effects (DB writes +
//     notifications). Its dependencies are injected, again for testability.
//   * A dependency checker prevents a team from completing out of turn.
// -----------------------------------------------------------------------------
'use strict';

const database = require('./database');
const notifications = require('./notifications');
const { t } = require('./templates');
const logger = require('./logger');

// Ordered list of team-owned "pending" states. Extend this to add more teams
// (e.g. logistics) — the whole engine adapts automatically.
const WORKFLOW = ['property', 'marketing', 'it'];

// Terminal / non-team states.
const READY = 'ready';
const COMPLETED = 'completed';

/**
 * Map a team name to its "pending" state, e.g. "marketing" -> "marketing_pending".
 * @param {string} team
 * @returns {string}
 */
function stateForTeam(team) {
  return `${team}_pending`;
}

/**
 * Map a state to the team that owns it, or null for non-team states.
 * @param {string} state
 * @returns {string|null}
 */
function teamForState(state) {
  if (state === READY || state === COMPLETED) return null;
  return state.replace(/_pending$/, '');
}

/**
 * Compute the next state given the current state and the workflow order.
 * @param {string} currentState
 * @param {string[]} [workflow=WORKFLOW]
 * @returns {string} The next state.
 */
function nextState(currentState, workflow = WORKFLOW) {
  if (currentState === READY) return COMPLETED;
  if (currentState === COMPLETED) return COMPLETED; // idempotent terminal
  const team = teamForState(currentState);
  const idx = workflow.indexOf(team);
  if (idx === -1) return currentState; // unknown state — no transition
  if (idx === workflow.length - 1) return READY; // last team done -> ready
  return stateForTeam(workflow[idx + 1]);
}

/**
 * Return the workflow order for a project (custom workflow lives in metadata).
 * @param {object} project
 * @returns {string[]}
 */
function workflowFor(project) {
  const custom = project && project.metadata && project.metadata.workflow;
  return Array.isArray(custom) && custom.length > 0 ? custom : WORKFLOW;
}

/**
 * Dependency checker: can this team complete right now? A team may only
 * complete when the project is currently in that team's pending state.
 * @param {object} project
 * @param {string} team
 * @returns {{ok: boolean, reason?: string}}
 */
function canComplete(project, team) {
  if (!project) return { ok: false, reason: 'project_not_found' };
  if (project.status === COMPLETED || project.status === READY) {
    return { ok: false, reason: 'already_finished' };
  }
  const activeTeam = teamForState(project.status);
  if (activeTeam !== team) {
    return { ok: false, reason: 'not_your_turn', expected: activeTeam };
  }
  return { ok: true };
}

/**
 * Complete the current team's work and transition the project forward.
 * Performs, in order: mark tasks done -> compute next state -> update project
 * -> log -> notify the next team (or announce readiness).
 *
 * @param {object} params
 * @param {object} params.project        The project row.
 * @param {string} params.team           The team completing their work.
 * @param {object} [deps]                Injected dependencies (for tests).
 * @param {object} [deps.db]             Repository (defaults to ./database).
 * @param {object} [deps.notifier]       Notifier (defaults to ./notifications).
 * @returns {Promise<{project: object, transitioned: boolean, to: string}>}
 */
async function completeCurrentTeam({ project, team }, deps = {}) {
  const db = deps.db || database;
  const notifier = deps.notifier || notifications;

  const check = canComplete(project, team);
  if (!check.ok) {
    return { project, transitioned: false, to: project.status, blocked: check };
  }

  const workflow = workflowFor(project);

  // 1. Mark the team's tasks as done.
  await db.completeTeamTasks(project.id, team);

  // 2. Compute the next state.
  const to = nextState(project.status, workflow);

  // 3. Persist the new status + current team.
  const updated = await db.updateProject(project.id, {
    status: to,
    current_team: teamForState(to),
  });

  // 4. Audit log.
  await db.addLog(project.id, `Team '${team}' completed. Status ${project.status} -> ${to}.`);
  logger.info({ project: project.code, from: project.status, to }, 'Project transitioned');

  // 5. Notify.
  if (to === READY) {
    // Announce readiness to every team lead.
    const leads = await db.listTeamLeads();
    await notifier.broadcast(
      leads.map((l) => l.whatsapp_number),
      t('projectReady', project.name),
    );
  } else {
    const nextTeam = teamForState(to);
    const lead = await db.getTeamLead(nextTeam);
    if (lead) {
      await notifier.sendMessage(lead.whatsapp_number, t('teamNotified', nextTeam, project.name));
    }
  }

  return { project: updated, transitioned: true, to };
}

module.exports = {
  WORKFLOW,
  READY,
  COMPLETED,
  stateForTeam,
  teamForState,
  nextState,
  workflowFor,
  canComplete,
  completeCurrentTeam,
};
