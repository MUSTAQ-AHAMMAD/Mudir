// tests/voice-handler.test.js
// Voice-note flow: transcript -> intent -> confirmation -> execution.
'use strict';

const voice = require('../src/voice-handler');
const { processIncoming } = require('../src/webhook');
const { createFakeDb, createFakeNotifier } = require('./fakeDb');
const mock = require('./mockMessages');

describe('voice handler', () => {
  test('detects a "we are done" intent and maps to /complete', () => {
    const cmd = voice.transcriptToCommand('ok we are done here', 'P-001');
    expect(cmd).toEqual({ name: 'complete', args: { projectId: 'P-001' } });
  });

  test('parseConfirmation handles Arabic + English', () => {
    expect(voice.parseConfirmation('yes')).toBe('yes');
    expect(voice.parseConfirmation('نعم')).toBe('yes');
    expect(voice.parseConfirmation('no')).toBe('no');
    expect(voice.parseConfirmation('maybe')).toBeNull();
  });

  test('voice note asks for confirmation, then executes on "yes"', async () => {
    const db = createFakeDb({
      teamLeads: [
        { team_name: 'property', whatsapp_number: 'whatsapp:+1', escalation_number: 'whatsapp:+9' },
        { team_name: 'marketing', whatsapp_number: 'whatsapp:+2', escalation_number: 'whatsapp:+9' },
      ],
    });
    const notifier = createFakeNotifier();
    // Stub the AI service so no network call is made.
    const ai = { transcribeAudio: async () => 'we are done' };
    const deps = { db, notifier, ai };

    await processIncoming(mock.text('whatsapp:+1', '/new_project Riyadh'), deps);

    const prompt = await processIncoming(mock.voice('whatsapp:+1', 'https://media/x.ogg'), deps);
    expect(prompt).toMatch(/confirm|نعم/i);

    const done = await processIncoming(mock.text('whatsapp:+1', 'yes'), deps);
    expect(done).toMatch(/property|جاهز|ready/i);
    const project = await db.getProjectByCode('P-001');
    expect(project.status).toBe('marketing_pending');
  });
});
