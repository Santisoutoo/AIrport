// RIMCAS — runway incursion alerting from strip states.

import { getStripColumn, getStripPhase } from './legacy/efs';
import type { FlightPlan } from './types/api';

export function checkRIMCAS(plans: FlightPlan[]): void {
  let hasIncursion = false;

  plans.forEach((plan) => {
    const reg = plan.aircraft_registration;
    const column = getStripColumn(reg);
    const phase = getStripPhase(reg);

    // Incursion: aircraft in RUNWAY column without authorization (not LINEUP nor CLEARED)
    if (column === 'RUNWAY' && phase !== 'LINEUP' && phase !== 'CLEARED') {
      hasIncursion = true;
    }
  });

  const alertEl = document.getElementById('rimcas-alert');
  const rwyRect = document.getElementById('smr-runway-rect');

  if (hasIncursion) {
    if (alertEl) alertEl.classList.remove('hidden');
    if (rwyRect) rwyRect.classList.add('smr-runway-incursion');
  } else {
    if (alertEl) alertEl.classList.add('hidden');
    if (rwyRect) rwyRect.classList.remove('smr-runway-incursion');
  }
}
