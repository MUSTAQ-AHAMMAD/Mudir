// tests/utils.test.js
// Unit tests for command parsing and Saudi working-day helpers.
'use strict';

const { parseCommand, normalizeWhatsApp, daysBetween, daysOverdue } = require('../src/utils');

describe('parseCommand', () => {
  test('parses /new_project', () => {
    expect(parseCommand('/new_project Riyadh Mall Store #342')).toEqual({
      name: 'new_project',
      args: { name: 'Riyadh Mall Store #342' },
    });
  });

  test('parses /assign with quoted task', () => {
    expect(parseCommand('/assign marketing "design banners" 2026-07-10')).toEqual({
      name: 'assign',
      args: { team: 'marketing', task: 'design banners', deadline: '2026-07-10' },
    });
  });

  test('parses /complete, /extend, /status, /escalate', () => {
    expect(parseCommand('/complete P-001').name).toBe('complete');
    expect(parseCommand('/extend P-001 marketing 3').args).toEqual({
      projectId: 'P-001',
      team: 'marketing',
      days: 3,
    });
    expect(parseCommand('/status P-001').args.projectId).toBe('P-001');
    expect(parseCommand('/escalate P-001 site not ready').args.reason).toBe('site not ready');
  });

  test('returns null for non-commands', () => {
    expect(parseCommand('hello there')).toBeNull();
    expect(parseCommand('')).toBeNull();
  });
});

describe('normalizeWhatsApp', () => {
  test('adds whatsapp: prefix and +', () => {
    expect(normalizeWhatsApp('966500000001')).toBe('whatsapp:+966500000001');
    expect(normalizeWhatsApp('whatsapp:+966500000001')).toBe('whatsapp:+966500000001');
    expect(normalizeWhatsApp('+966 50 000 0001')).toBe('whatsapp:+966500000001');
  });
});

describe('date helpers', () => {
  test('daysBetween and daysOverdue', () => {
    expect(daysBetween('2026-01-01', '2026-01-11')).toBe(10);
    expect(daysOverdue('2026-01-01', new Date('2026-01-04'))).toBe(3);
    expect(daysOverdue('2026-01-10', new Date('2026-01-04'))).toBe(0);
  });
});
