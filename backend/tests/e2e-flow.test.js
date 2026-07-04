// tests/e2e-flow.test.js
// End-to-end store-opening flow driven entirely through the webhook's
// processIncoming() using mock WhatsApp messages and in-memory fakes.
'use strict';

const { processIncoming } = require('../src/webhook');
const { createFakeDb, createFakeNotifier } = require('./fakeDb');
const mock = require('./mockMessages');

describe('E2E: complete store opening flow', () => {
  test('property -> marketing -> it -> ready', async () => {
    const db = createFakeDb({
      teamLeads: [
        { team_name: 'property', whatsapp_number: 'whatsapp:+1', escalation_number: 'whatsapp:+9' },
        { team_name: 'marketing', whatsapp_number: 'whatsapp:+2', escalation_number: 'whatsapp:+9' },
        { team_name: 'it', whatsapp_number: 'whatsapp:+3', escalation_number: 'whatsapp:+9' },
      ],
    });
    const notifier = createFakeNotifier();
    const deps = { db, notifier };

    // 1. Property creates the project.
    const created = await processIncoming(mock.text('whatsapp:+1', '/new_project Riyadh Mall Store #342'), deps);
    expect(created).toMatch(/P-001/);

    // 2. Property completes -> Marketing notified.
    const afterProperty = await processIncoming(mock.text('whatsapp:+1', '/complete P-001'), deps);
    expect(afterProperty).toMatch(/property/i);
    expect(notifier.sent.some((m) => m.to === 'whatsapp:+2')).toBe(true);

    // 3. Marketing completes -> IT notified.
    await processIncoming(mock.text('whatsapp:+2', '/complete P-001'), deps);
    expect(notifier.sent.some((m) => m.to === 'whatsapp:+3')).toBe(true);

    // 4. IT completes -> project ready (broadcast to all leads).
    const afterIt = await processIncoming(mock.text('whatsapp:+3', '/complete P-001'), deps);
    expect(afterIt).toMatch(/ready|جاهز/i);

    const project = await db.getProjectByCode('P-001');
    expect(project.status).toBe('ready');
  });

  test('escalation reaches the CEO', async () => {
    const db = createFakeDb({
      teamLeads: [{ team_name: 'property', whatsapp_number: 'whatsapp:+1', escalation_number: 'whatsapp:+9' }],
    });
    const notifier = createFakeNotifier();
    const deps = { db, notifier };
    await processIncoming(mock.text('whatsapp:+1', '/new_project Test'), deps);
    await processIncoming(mock.text('whatsapp:+1', '/escalate P-001 blocker found'), deps);
    expect(notifier.sent.some((m) => m.to === 'whatsapp:+9')).toBe(true);
  });
});
