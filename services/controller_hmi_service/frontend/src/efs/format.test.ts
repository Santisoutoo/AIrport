import { describe, expect, it } from 'vitest';

import { formatFL, formatSpeed, formatTime, generateSquawk, truncateRoute } from './format';

describe('formatFL', () => {
  it('renders flight levels at/above 10000 ft', () => {
    expect(formatFL(35000)).toBe('F350');
    expect(formatFL(10000)).toBe('F100');
  });

  it('renders altitudes below 10000 ft with A prefix and 3 digits', () => {
    expect(formatFL(4500)).toBe('A045');
    expect(formatFL(900)).toBe('A009');
  });

  it('falls back for missing values', () => {
    expect(formatFL(undefined)).toBe('----');
    expect(formatFL(0)).toBe('----');
  });
});

describe('formatSpeed', () => {
  it('zero-pads to 4 digits with N prefix', () => {
    expect(formatSpeed(460)).toBe('N0460');
    expect(formatSpeed(85)).toBe('N0085');
  });

  it('falls back for missing values', () => {
    expect(formatSpeed(undefined)).toBe('-----');
  });
});

describe('formatTime', () => {
  it('renders hhmm numbers as hh:mm', () => {
    expect(formatTime(1430)).toBe('14:30');
    expect(formatTime(905)).toBe('09:05');
  });

  it('renders midnight (0) and missing differently', () => {
    expect(formatTime(0)).toBe('00:00');
    expect(formatTime(undefined)).toBe('--:--');
  });
});

describe('generateSquawk', () => {
  it('is deterministic per registration', () => {
    expect(generateSquawk('EC-ABC')).toBe(generateSquawk('EC-ABC'));
  });

  it('produces 4 digits, each 0-7', () => {
    for (const reg of ['EC-ABC', 'N12345', 'D-AIBL', 'G-EZTH']) {
      const sq = generateSquawk(reg);
      expect(sq).toMatch(/^[0-7]{4}$/);
    }
  });

  it('differs across registrations (hash actually varies)', () => {
    expect(generateSquawk('EC-AAA')).not.toBe(generateSquawk('EC-ZZZ'));
  });
});

describe('truncateRoute', () => {
  it('returns DCT for empty routes', () => {
    expect(truncateRoute(undefined, 10)).toBe('DCT');
    expect(truncateRoute('', 10)).toBe('DCT');
  });

  it('keeps short routes and truncates long ones with ellipsis', () => {
    expect(truncateRoute('DCT ROSTO', 20)).toBe('DCT ROSTO');
    expect(truncateRoute('ABCDEFGHIJ', 4)).toBe('ABCD...');
  });
});
