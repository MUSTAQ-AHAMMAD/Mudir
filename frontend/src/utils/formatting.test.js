import { describe, it, expect } from 'vitest';
import { initials, titleCase, formatPercent } from './formatting';

describe('formatting utils', () => {
  it('derives initials', () => {
    expect(initials('Ahmed Ali')).toBe('AA');
    expect(initials('Mudir')).toBe('MU');
    expect(initials('')).toBe('?');
  });

  it('title-cases snake_case', () => {
    expect(titleCase('property_pending')).toBe('Property Pending');
  });

  it('formats percentages', () => {
    expect(formatPercent(50, 'en')).toBe('50%');
    expect(formatPercent(0.5, 'en', { fromFraction: true })).toBe('50%');
  });
});
