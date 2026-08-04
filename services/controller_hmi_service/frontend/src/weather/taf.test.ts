import { describe, expect, it } from 'vitest';

import { extractTafPortion, parseTaf, parseWeatherTokens } from './taf';

const LEST_TAF =
  'TAF LEST 041100Z 0412/0512 17010KT 9999 SCT020 BKN035 ' +
  'TX18/0414Z TN09/0506Z ' +
  'TEMPO 0412/0418 17015G25KT 4000 RA BKN012 ' +
  'BECMG 0418/0420 25008KT CAVOK';

describe('extractTafPortion', () => {
  it('strips METAR noise before the TAF token', () => {
    const mixed = 'METAR LEST 041030Z 17008KT 9999 FEW020\n' + LEST_TAF;
    expect(extractTafPortion(mixed).startsWith('TAF LEST')).toBe(true);
  });

  it('returns the input unchanged when no TAF token exists', () => {
    expect(extractTafPortion('no forecast here')).toBe('no forecast here');
  });
});

describe('parseTaf', () => {
  const parsed = parseTaf(LEST_TAF);

  it('extracts the validity window', () => {
    expect(parsed.validity).toBe('04d 12Z → 05d 12Z');
  });

  it('extracts TX/TN', () => {
    expect(parsed.tempMax).toBe('18°C @ 0414Z');
    expect(parsed.tempMin).toBe('09°C @ 0506Z');
  });

  it('parses the base group', () => {
    expect(parsed.base?.wind).toBe('170°/10kt');
    expect(parsed.base?.clouds).toBe('SCT 2000ft BKN 3500ft');
  });

  it('parses TEMPO and BECMG change groups in order', () => {
    expect(parsed.changes).toHaveLength(2);
    expect(parsed.changes[0]?.type).toBe('TEMPO');
    expect(parsed.changes[0]?.wind).toBe('170°/15kt G25');
    // Known quirk inherited from the original parser: the change-group time
    // window (0412/0418) matches the 4-digit visibility regex before the
    // real visibility token (4000) does. Pinned here so a future fix is a
    // conscious behavior change, not an accident.
    expect(parsed.changes[0]?.vis).toBe('0.4 km');
    expect(parsed.changes[0]?.wx).toContain('RA');
    expect(parsed.changes[1]?.type).toBe('BECMG');
    expect(parsed.changes[1]?.vis).toBe('CAVOK');
  });

  it('handles null input', () => {
    const empty = parseTaf(null);
    expect(empty.base).toBeNull();
    expect(empty.changes).toEqual([]);
  });
});

describe('parseWeatherTokens', () => {
  it('parses variable wind', () => {
    expect(parseWeatherTokens('VRB03KT 9999').wind).toBe('VRB/03kt');
  });

  it('parses CAVOK over numeric visibility', () => {
    expect(parseWeatherTokens('25010KT CAVOK').vis).toBe('CAVOK');
  });

  it('renders 9999 as >10 km', () => {
    expect(parseWeatherTokens('25010KT 9999').vis).toBe('>10 km');
  });

  it('collects weather phenomena with intensity prefix', () => {
    expect(parseWeatherTokens('17015KT 2000 -RA BR').wx).toContain('-RA');
  });
});
