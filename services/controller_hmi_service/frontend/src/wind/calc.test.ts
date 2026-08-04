import { describe, expect, it } from 'vitest';

import { checkWindLimits, computeWindComponents } from './calc';

describe('computeWindComponents', () => {
  it('pure headwind when wind is aligned with the runway', () => {
    const c = computeWindComponents(170, 20, 170);
    expect(c.headwind).toBe(20);
    expect(c.crosswind).toBe(0);
    expect(c.tailwind).toBe(0);
    expect(c.hwDisplay).toBe(20);
  });

  it('pure tailwind when wind is opposite the runway', () => {
    const c = computeWindComponents(350, 12, 170);
    expect(c.headwind).toBe(-12);
    expect(c.tailwind).toBe(12);
    expect(c.hwDisplay).toBe(0);
    expect(c.crosswind).toBe(0);
  });

  it('pure crosswind at 90°', () => {
    const c = computeWindComponents(260, 15, 170);
    expect(c.crosswind).toBe(15);
    expect(Math.abs(c.headwind)).toBeLessThanOrEqual(1); // rounding
  });

  it('45° split: components are speed·cos(45) rounded', () => {
    const c = computeWindComponents(215, 20, 170);
    expect(c.headwind).toBe(14);
    expect(c.crosswind).toBe(14);
  });

  it('handles wrap-around directions (350° wind on runway 010)', () => {
    const c = computeWindComponents(350, 10, 10);
    expect(c.headwind).toBe(9); // 20° off-axis
    expect(c.crosswind).toBe(3);
  });
});

describe('checkWindLimits', () => {
  it('flags crosswind first', () => {
    expect(checkWindLimits(25, 10, 20, 5)).toEqual({
      exceeded: true,
      message: 'XW LIMIT EXCEEDED',
    });
  });

  it('flags tailwind when crosswind is within limits', () => {
    expect(checkWindLimits(10, 7, 20, 5)).toEqual({
      exceeded: true,
      message: 'TW LIMIT EXCEEDED',
    });
  });

  it('passes at the exact limit', () => {
    expect(checkWindLimits(20, 5, 20, 5)).toEqual({ exceeded: false, message: null });
  });
});
