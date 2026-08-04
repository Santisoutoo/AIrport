// Runway sequence monitor (arrivals/departures panels) and the dynamic
// runway selector that feeds the wind widget.

import { getStripColumn, getStripPhase } from './legacy/efs';
import { escapeHtml } from './legacy/weather';
import { setRunwayGroups, type RunwayGroup } from './legacy/wind';
import { currentICAO } from './polling';
import { smrState } from './smr/state';
import type { FlightPlan, StripColumn } from './types/api';

// WTC lookup by aircraft type prefix
const WTC_MAP: Record<string, string> = {
  A388: 'J', A380: 'J', B748: 'H', B744: 'H', B77W: 'H',
  B772: 'H', B773: 'H', A346: 'H', A345: 'H', A343: 'H',
  A332: 'H', A333: 'H', A339: 'H', A359: 'H', A35K: 'H',
  B789: 'H', B788: 'H', B787: 'H', B763: 'H', B764: 'H',
  A321: 'M', A320: 'M', A319: 'M', A318: 'M', B738: 'M',
  B737: 'M', B739: 'M', E195: 'M', E190: 'M', B752: 'M',
  CRJ9: 'M', CRJ7: 'M', E170: 'M', E75L: 'M', AT76: 'M',
  AT75: 'M', DH8D: 'M', C172: 'L', PA28: 'L', C152: 'L',
  P28A: 'L', BE20: 'L', C208: 'L', PC12: 'L',
};

export function getWTC(acType: string | undefined): string {
  if (!acType) return 'M';
  const code = acType.toUpperCase().replace(/-/g, '');
  const known = WTC_MAP[code];
  if (known) return known;
  // Guess from prefix
  if (code.indexOf('A3') === 0 && parseInt(code.charAt(2)) >= 3) return 'H';
  if (code.indexOf('B7') === 0 && parseInt(code.charAt(2)) >= 4) return 'H';
  return 'M';
}

/** Collect runway designators from the loaded graph, group by heading and
 * hand them to the wind widget. */
export function updateRunwaySelector(): void {
  const graph = smrState.graph;
  if (!graph || !graph.runways) return;

  const designators: { label: string; hdg: number }[] = [];
  graph.runways.forEach((rwy) => {
    designators.push({ label: rwy.end1.designator, hdg: parseInt(rwy.end1.designator) * 10 });
    designators.push({ label: rwy.end2.designator, hdg: parseInt(rwy.end2.designator) * 10 });
  });

  if (designators.length === 0) return;

  // Group by heading (e.g., 36L + 36R share the same heading)
  const groupMap: Record<number, RunwayGroup> = {};
  designators.forEach((d) => {
    const group = (groupMap[d.hdg] ??= { hdg: d.hdg, labels: [] });
    group.labels.push(d.label);
  });

  const groups = Object.values(groupMap).sort((a, b) => a.hdg - b.hdg);
  setRunwayGroups(groups);
}

interface SequenceEntry {
  callsign: string;
  type: string;
  wtc: string;
  phase: string;
  column: StripColumn;
}

export function updateRunwaySequence(plans: FlightPlan[]): void {
  const arrContainer = document.getElementById('rwy-seq-arrivals');
  const depContainer = document.getElementById('rwy-seq-departures');
  if (!arrContainer || !depContainer) return;

  const arrivals: SequenceEntry[] = [];
  const departures: SequenceEntry[] = [];

  if (plans && plans.length > 0) {
    plans.forEach((plan) => {
      const reg = plan.aircraft_registration || '';
      const col = getStripColumn(reg);
      const phase = getStripPhase(reg);
      const type = plan.aircraft_type || '';
      const wtc = getWTC(type);

      const entry: SequenceEntry = { callsign: reg, type, wtc, phase, column: col };
      if (plan.flight_type === 'arrival' || plan.arrival_airport === currentICAO) {
        arrivals.push(entry);
      } else {
        departures.push(entry);
      }
    });
  }

  // Render arrivals (max 3)
  if (arrivals.length === 0) {
    arrContainer.innerHTML = '<div class="rwy-seq-empty">No traffic</div>';
  } else {
    let arrHtml = '';
    let prevWtc: string | null = null;
    arrivals.slice(0, 3).forEach((a, i) => {
      const wtcClass = 'wtc-' + a.wtc.toLowerCase();
      const wtcWarn = prevWtc === 'H' || prevWtc === 'J' ? ' title="Wake turbulence caution"' : '';
      arrHtml +=
        '<div class="rwy-seq-item seq-arr"' + wtcWarn + '>' +
        '<span class="seq-pos">' + (i + 1) + '</span>' +
        '<span class="seq-callsign">' + escapeHtml(a.callsign) + '</span>' +
        '<span class="seq-type">' + escapeHtml(a.type || '--') + '</span>' +
        '<span class="seq-wtc ' + wtcClass + '">' + a.wtc + '</span>';
      if (prevWtc === 'H' || prevWtc === 'J') {
        arrHtml += '<span class="seq-wtc wtc-h" style="font-size:7px">WK!</span>';
      }
      arrHtml += '</div>';
      prevWtc = a.wtc;
    });
    arrContainer.innerHTML = arrHtml;
  }

  // Render departures (max 3)
  if (departures.length === 0) {
    depContainer.innerHTML = '<div class="rwy-seq-empty">No traffic</div>';
  } else {
    let depHtml = '';
    departures.slice(0, 3).forEach((d, i) => {
      const wtcClass = 'wtc-' + d.wtc.toLowerCase();
      let statusLabel = '';
      if (d.phase === 'CLEARED') statusLabel = '<span class="seq-freq">CLR</span>';
      else if (d.phase === 'LINEUP') statusLabel = '<span class="seq-freq">L/U</span>';
      else if (d.column === 'TAXI') statusLabel = '<span class="seq-freq">TAXI</span>';

      depHtml +=
        '<div class="rwy-seq-item seq-dep">' +
        '<span class="seq-pos">' + (i + 1) + '</span>' +
        '<span class="seq-callsign">' + escapeHtml(d.callsign) + '</span>' +
        '<span class="seq-type">' + escapeHtml(d.type || '--') + '</span>' +
        '<span class="seq-wtc ' + wtcClass + '">' + d.wtc + '</span>' +
        statusLabel +
        '</div>';
    });
    depContainer.innerHTML = depHtml;
  }
}
