// tests/state-machine.test.js
// Unit tests for the pure state-machine logic and the orchestrated transition.
'use strict';

const sm = require('../src/state-machine');
const { createFakeDb, createFakeNotifier } = require('./fakeDb');

describe('state machine (pure logic)', () => {
  test('nextState follows property -> marketing -> it -> ready -> completed', () => {
    expect(sm.nextState('property_pending')).toBe('marketing_pending');
    expect(sm.nextState('marketing_pending')).toBe('it_pending');
    expect(sm.nextState('it_pending')).toBe('ready');
    expect(sm.nextState('ready')).toBe('completed');
    expect(sm.nextState('completed')).toBe('completed');
  });

  test('teamForState / stateForTeam round-trip', () => {
    expect(sm.stateForTeam('marketing')).toBe('marketing_pending');
    expect(sm.teamForState('marketing_pending')).toBe('marketing');
    expect(sm.teamForState('ready')).toBeNull();
    expect(sm.teamForState('completed')).toBeNull();
  });

  test('canComplete enforces turn order', () => {
    const project = { status: 'property_pending' };
    expect(sm.canComplete(project, 'property').ok).toBe(true);
    expect(sm.canComplete(project, 'marketing').ok).toBe(false);
    expect(sm.canComplete({ status: 'completed' }, 'it').ok).toBe(false);
  });

  test('nextState honours a custom workflow with an extra team', () => {
    const wf = ['property', 'marketing', 'it', 'logistics'];
    expect(sm.nextState('it_pending', wf)).toBe('logistics_pending');
    expect(sm.nextState('logistics_pending', wf)).toBe('ready');
  });
});

describe('completeCurrentTeam (orchestration)', () => {
  test('transitions and notifies the next team', async () => {
    const db = createFakeDb({
      teamLeads: [
        { team_name: 'property', whatsapp_number: 'whatsapp:+1', escalation_number: 'whatsapp:+9' },
        { team_name: 'marketing', whatsapp_number: 'whatsapp:+2', escalation_number: 'whatsapp:+9' },
      ],
    });
    const notifier = createFakeNotifier();
    const project = await db.createProject({
      code: 'P-001',
      name: 'Riyadh Mall',
      status: 'property_pending',
      current_team: 'property',
      metadata: { workflow: ['property', 'marketing', 'it'] },
    });
    await db.createTask({ project_id: project.id, assigned_team: 'property', description: 'site', status: 'pending' });

    const result = await sm.completeCurrentTeam({ project, team: 'property' }, { db, notifier });

    expect(result.transitioned).toBe(true);
    expect(result.to).toBe('marketing_pending');
    // Marketing lead was notified.
    expect(notifier.sent.some((m) => m.to === 'whatsapp:+2')).toBe(true);
    // Property task marked done.
    const tasks = await db.listTasks(project.id, { team: 'property' });
    expect(tasks[0].status).toBe('done');
  });

  test('refuses to complete out of turn', async () => {
    const db = createFakeDb();
    const notifier = createFakeNotifier();
    const project = await db.createProject({ code: 'P-002', name: 'X', status: 'property_pending' });
    const result = await sm.completeCurrentTeam({ project, team: 'it' }, { db, notifier });
    expect(result.transitioned).toBe(false);
    expect(result.blocked.reason).toBe('not_your_turn');
  });
});
