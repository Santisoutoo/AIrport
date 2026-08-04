import { describe, expect, it } from 'vitest';

import type { FlightPlan } from '../types/api';
import { moveInOrder, sortByUserOrder, sortFlightPlans } from './ordering';

const plan = (reg: string, extra: Partial<FlightPlan> = {}): FlightPlan => ({
  aircraft_registration: reg,
  ...extra,
});

describe('sortFlightPlans', () => {
  const plans = [
    plan('EC-CCC', { departure_time: 1200, destination_ICAO: 'LEMD' }),
    plan('EC-AAA', { departure_time: 900, destination_ICAO: 'LFPG' }),
    plan('EC-BBB', { departure_time: 1030, destination_ICAO: 'EGLL' }),
  ];

  it('sorts by departure time', () => {
    expect(sortFlightPlans(plans, 'departure_time').map((p) => p.aircraft_registration)).toEqual([
      'EC-AAA',
      'EC-BBB',
      'EC-CCC',
    ]);
  });

  it('sorts by callsign (registration)', () => {
    expect(sortFlightPlans(plans, 'callsign').map((p) => p.aircraft_registration)).toEqual([
      'EC-AAA',
      'EC-BBB',
      'EC-CCC',
    ]);
  });

  it('sorts by destination', () => {
    expect(sortFlightPlans(plans, 'destination').map((p) => p.aircraft_registration)).toEqual([
      'EC-BBB',
      'EC-CCC',
      'EC-AAA',
    ]);
  });

  it('unknown key keeps the original order and does not mutate', () => {
    const copy = plans.slice();
    expect(sortFlightPlans(plans, 'nope')).toEqual(copy);
    expect(plans).toEqual(copy);
  });
});

describe('sortByUserOrder', () => {
  it('orders by the user list, unknown regs go last', () => {
    const plans = [plan('B'), plan('C'), plan('A')];
    const out = sortByUserOrder(plans, ['A', 'B']);
    expect(out.map((p) => p.aircraft_registration)).toEqual(['A', 'B', 'C']);
  });
});

describe('moveInOrder', () => {
  it('inserts before the target', () => {
    expect(moveInOrder(['A', 'B', 'C'], 'C', 'A', true)).toEqual(['C', 'A', 'B']);
  });

  it('inserts after the target', () => {
    expect(moveInOrder(['A', 'B', 'C'], 'A', 'C', false)).toEqual(['B', 'C', 'A']);
  });

  it('appends when the target is unknown', () => {
    expect(moveInOrder(['A', 'B'], 'A', 'Z', true)).toEqual(['B', 'A']);
  });

  it('does not mutate the input array', () => {
    const order = ['A', 'B'];
    moveInOrder(order, 'B', 'A', true);
    expect(order).toEqual(['A', 'B']);
  });
});
