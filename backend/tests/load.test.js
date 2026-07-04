// tests/load.test.js
// Lightweight load simulation: drives 100 concurrent store-opening projects
// end-to-end through the webhook using in-memory fakes. This verifies the
// state machine and command routing hold up under concurrency WITHOUT hitting
// Twilio/OpenAI/Supabase. For real HTTP load testing use a tool like k6 or
// autocannon against a deployed instance (see README).
'use strict';

const { processIncoming } = require('../src/webhook');
const { createFakeDb, createFakeNotifier } = require('./fakeDb');
const mock = require('./mockMessages');

describe('load: 100 concurrent projects', () => {
  test('all projects complete the full flow', async () => {
    const db = createFakeDb({
      teamLeads: [
        { team_name: 'property', whatsapp_number: 'whatsapp:+1', escalation_number: 'whatsapp:+9' },
        { team_name: 'marketing', whatsapp_number: 'whatsapp:+2', escalation_number: 'whatsapp:+9' },
        { team_name: 'it', whatsapp_number: 'whatsapp:+3', escalation_number: 'whatsapp:+9' },
      ],
    });
    const notifier = createFakeNotifier();
    const deps = { db, notifier };
    const N = 100;

    // Create N projects (sequential creation yields unique P-NNN codes, just
    // as the backend allocates codes one message at a time).
    for (let i = 0; i < N; i += 1) {
      // eslint-disable-next-line no-await-in-loop
      await processIncoming(mock.text('whatsapp:+1', `/new_project Store ${i + 1}`), deps);
    }
    const projects = await db.listProjects();
    expect(projects.length).toBe(N);

    // Drive each project property -> marketing -> it concurrently.
    await Promise.all(
      projects.map(async (p) => {
        await processIncoming(mock.text('whatsapp:+1', `/complete ${p.code}`), deps);
        await processIncoming(mock.text('whatsapp:+2', `/complete ${p.code}`), deps);
        await processIncoming(mock.text('whatsapp:+3', `/complete ${p.code}`), deps);
      }),
    );

    const finished = await db.listProjects();
    expect(finished.every((p) => p.status === 'ready')).toBe(true);
  });
});
