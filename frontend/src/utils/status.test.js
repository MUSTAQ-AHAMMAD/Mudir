import { describe, it, expect } from 'vitest';
import { isOverdue, projectHealth, stageProgress, statusLabel, PROJECT_STAGES } from './status';

describe('status utils', () => {
  it('detects overdue projects', () => {
    expect(isOverdue({ opening_date: '2000-01-01', status: 'it_pending' })).toBe(true);
    expect(isOverdue({ opening_date: '2000-01-01', status: 'completed' })).toBe(false);
    expect(isOverdue({})).toBe(false);
  });

  it('classifies project health', () => {
    expect(projectHealth({ status: 'completed' })).toBe('completed');
    expect(projectHealth({ opening_date: '2000-01-01', status: 'it_pending' })).toBe('delayed');
    const soon = new Date(Date.now() + 86400000).toISOString();
    expect(projectHealth({ opening_date: soon, status: 'it_pending' })).toBe('at_risk');
  });

  it('computes stage progress', () => {
    expect(stageProgress({ status: 'completed' })).toBe(100);
    expect(stageProgress({ status: PROJECT_STAGES[0] })).toBe(0);
  });

  it('returns bilingual labels', () => {
    expect(statusLabel('ready', 'en')).toBe('Ready');
    expect(statusLabel('ready', 'ar')).toBe('جاهز');
  });
});
