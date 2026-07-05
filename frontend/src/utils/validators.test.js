import { describe, it, expect } from 'vitest';
import { required, isPhone, isEmail, compose } from './validators';

describe('validators', () => {
  it('requires a value', () => {
    expect(required('x')).toBe(true);
    expect(typeof required('')).toBe('string');
  });

  it('validates phone numbers', () => {
    expect(isPhone('+966512345678')).toBe(true);
    expect(typeof isPhone('abc')).toBe('string');
    expect(isPhone('')).toBe(true);
  });

  it('validates emails', () => {
    expect(isEmail('a@b.co')).toBe(true);
    expect(typeof isEmail('bad')).toBe('string');
  });

  it('composes validators returning the first error', () => {
    const v = compose(required, isEmail);
    expect(typeof v('')).toBe('string');
    expect(v('a@b.co')).toBe(true);
  });
});
