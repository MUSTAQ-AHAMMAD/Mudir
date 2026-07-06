// tests/cron-jobs.test.js
// Verifies weekend-skip logic and overdue auto-escalation.
'use strict';

const cron = require('../src/cron-jobs');
const { createFakeDb, createFakeNotifier } = require('./fakeDb');

describe('cron jobs', () => {
  test('overdue job skips on Friday (Saudi weekend)', async () => {
    const db = createFakeDb();
    const notifier = createFakeNotifier();
    // 2026-07-03 is a Friday.
    const result = await cron.overdueEscalationJob({ db, notifier, now: new Date('2026-07-03T09:00:00Z') });
    expect(result.skipped).toBe(true);
  });

  test('overdue job escalates tasks past the threshold on a working day', async () => {
    const db = createFakeDb({
      teamLeads: [{ team_name: 'marketing', whatsapp_number: 'whatsapp:+2', escalation_number: 'whatsapp:+9' }],
    });
    const notifier = createFakeNotifier();
    const project = await db.createProject({ code: 'P-001', name: 'X', status: 'marketing_pending' });
    await db.createTask({
      project_id: project.id,
      assigned_team: 'marketing',
      description: 'banners',
      deadline: '2026-06-28',
      status: 'pending',
    });
    // 2026-07-01 is a Wednesday, 3 days overdue (>= threshold of 2).
    const result = await cron.overdueEscalationJob({ db, notifier, now: new Date('2026-07-01T09:00:00Z') });
    expect(result.skipped).toBe(false);
    expect(result.escalated).toBe(1);
    expect(notifier.sent.some((m) => m.to === 'whatsapp:+9')).toBe(true);
  });

  test('daily summary skips weekend and runs on working day', async () => {
    const db = createFakeDb({ teamLeads: [{ team_name: 'it', whatsapp_number: 'whatsapp:+3' }] });
    const notifier = createFakeNotifier();
    const ai = { summarizeConversation: async () => 'summary' };
    await db.createProject({ code: 'P-001', name: 'X', status: 'it_pending' });

    const weekend = await cron.dailySummaryJob({ db, notifier, ai, now: new Date('2026-07-03T09:00:00Z') });
    expect(weekend.skipped).toBe(true);

    const workday = await cron.dailySummaryJob({ db, notifier, ai, now: new Date('2026-07-01T09:00:00Z') });
    expect(workday.skipped).toBe(false);
    expect(notifier.sent.length).toBeGreaterThan(0);
  });
});
