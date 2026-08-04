// Pure ordering helpers for flight strips.

import type { FlightPlan } from '../types/api';

export function sortFlightPlans(plans: FlightPlan[], sortBy: string): FlightPlan[] {
  return plans.slice().sort((a, b) => {
    switch (sortBy) {
      case 'departure_time':
        return (a.departure_time ?? 0) - (b.departure_time ?? 0);
      case 'callsign':
        return a.aircraft_registration.localeCompare(b.aircraft_registration);
      case 'destination':
        return (a.destination_ICAO ?? '').localeCompare(b.destination_ICAO ?? '');
      default:
        return 0;
    }
  });
}

/** Sort one column's plans by a user-defined registration order; plans not
 * in the order list keep their relative position at the end. */
export function sortByUserOrder(plans: FlightPlan[], order: string[]): FlightPlan[] {
  return plans.slice().sort((a, b) => {
    let ai = order.indexOf(a.aircraft_registration);
    let bi = order.indexOf(b.aircraft_registration);
    if (ai === -1) ai = Infinity;
    if (bi === -1) bi = Infinity;
    return ai - bi;
  });
}

/** Insert dragReg into order relative to targetReg (before/after), removing
 * any previous occurrence. Returns a new array. */
export function moveInOrder(
  order: string[],
  dragReg: string,
  targetReg: string,
  insertBefore: boolean,
): string[] {
  const next = order.filter((r) => r !== dragReg);
  const idx = next.indexOf(targetReg);
  if (idx === -1) {
    next.push(dragReg);
  } else if (insertBefore) {
    next.splice(idx, 0, dragReg);
  } else {
    next.splice(idx + 1, 0, dragReg);
  }
  return next;
}
