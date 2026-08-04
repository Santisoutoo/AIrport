import { describe, expect, it } from 'vitest';

import type { AirportGraph } from '../types/api';
import {
  bearingDeg,
  computeSmrBounds,
  geoToSVG,
  leaderAttachPoint,
  projectGeoFromBearing,
} from './projection';

// Minimal graph around Santiago (LEST-ish latitudes) — a 0.02° square.
const GRAPH: AirportGraph = {
  nodes: {
    n1: { lat: 42.89, lon: -8.43 },
    n2: { lat: 42.91, lon: -8.41 },
  },
  edges: [{ from: 'n1', to: 'n2' }],
  stands: [{ name: 'S1', lat: 42.9, lon: -8.42 }],
  runways: [
    {
      end1: { designator: '17', lat: 42.9118, lon: -8.4203 },
      end2: { designator: '35', lat: 42.8895, lon: -8.4143 },
    },
  ],
};

describe('computeSmrBounds', () => {
  it('wraps all coordinates with an 8% margin and cosine correction', () => {
    const b = computeSmrBounds(GRAPH)!;
    expect(b).not.toBeNull();
    expect(b.minLat).toBeLessThan(42.89);
    expect(b.maxLat).toBeGreaterThan(42.91);
    expect(b.minLon).toBeLessThan(-8.43);
    expect(b.maxLon).toBeGreaterThan(-8.41);
    expect(b.cosLat).toBeCloseTo(Math.cos((42.9 * Math.PI) / 180), 3);
  });

  it('returns null for an empty graph', () => {
    expect(computeSmrBounds({ nodes: {}, edges: [], stands: [], runways: [] })).toBeNull();
  });
});

describe('geoToSVG', () => {
  const bounds = computeSmrBounds(GRAPH)!;

  it('falls back to the viewBox centre without bounds', () => {
    expect(geoToSVG(null, 42.9, -8.42)).toEqual({ x: 50, y: 50 });
  });

  it('maps the bounds centre to the viewBox centre', () => {
    const p = geoToSVG(bounds, (bounds.minLat + bounds.maxLat) / 2, (bounds.minLon + bounds.maxLon) / 2);
    expect(p.x).toBeCloseTo(50, 5);
    expect(p.y).toBeCloseTo(50, 5);
  });

  it('maps north to the top (higher latitude → smaller y)', () => {
    const north = geoToSVG(bounds, 42.91, -8.42);
    const south = geoToSVG(bounds, 42.89, -8.42);
    expect(north.y).toBeLessThan(south.y);
  });

  it('keeps every graph coordinate inside the padded viewBox', () => {
    for (const n of Object.values(GRAPH.nodes)) {
      const p = geoToSVG(bounds, n.lat, n.lon);
      expect(p.x).toBeGreaterThanOrEqual(0);
      expect(p.x).toBeLessThanOrEqual(100);
      expect(p.y).toBeGreaterThanOrEqual(0);
      expect(p.y).toBeLessThanOrEqual(100);
    }
  });
});

describe('bearingDeg', () => {
  it('is 0 due north and 90 due east', () => {
    expect(bearingDeg(42.9, -8.42, 43.0, -8.42)).toBeCloseTo(0, 0);
    expect(bearingDeg(0, 0, 0, 1)).toBeCloseTo(90, 0);
  });

  it('matches the runway 17 orientation (~south-southeast)', () => {
    const brg = bearingDeg(
      GRAPH.runways[0]!.end2.lat,
      GRAPH.runways[0]!.end2.lon,
      GRAPH.runways[0]!.end1.lat,
      GRAPH.runways[0]!.end1.lon,
    );
    // end2 (35) → end1 (17): flying towards ~350°, i.e. landing runway 35's
    // reciprocal; the value must sit in the north-west quadrant
    expect(brg).toBeGreaterThan(340);
    expect(brg).toBeLessThan(360);
  });
});

describe('projectGeoFromBearing', () => {
  it('moves ~1/60 degree of latitude per NM going north', () => {
    const p = projectGeoFromBearing(42.9, -8.42, 0, 6);
    expect(p.lat).toBeCloseTo(42.9 + 0.1, 5);
    expect(p.lon).toBeCloseTo(-8.42, 5);
  });

  it('round-trips: out along a bearing and back along the reciprocal', () => {
    const out = projectGeoFromBearing(42.9, -8.42, 73, 5);
    const back = projectGeoFromBearing(out.lat, out.lon, (73 + 180) % 360, 5);
    expect(back.lat).toBeCloseTo(42.9, 3);
    expect(back.lon).toBeCloseTo(-8.42, 3);
  });
});

describe('leaderAttachPoint', () => {
  // Box: x=10..20, y=10..14
  it('attaches to the left edge when the dot is left of the box', () => {
    const p = leaderAttachPoint(0, 12, 10, 10, 10, 4);
    expect(p.x).toBeCloseTo(10, 5);
    expect(p.y).toBeGreaterThanOrEqual(10);
    expect(p.y).toBeLessThanOrEqual(14);
  });

  it('attaches to the top edge when the dot is above the box', () => {
    const p = leaderAttachPoint(15, 0, 10, 10, 10, 4);
    expect(p.y).toBeCloseTo(10, 5);
    expect(p.x).toBeGreaterThanOrEqual(10);
    expect(p.x).toBeLessThanOrEqual(20);
  });

  it('degenerates gracefully when the dot is at the box centre', () => {
    const p = leaderAttachPoint(15, 12, 10, 10, 10, 4);
    expect(p).toEqual({ x: 10, y: 12 });
  });
});
