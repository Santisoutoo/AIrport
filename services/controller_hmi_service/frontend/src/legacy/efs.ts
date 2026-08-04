// efs.ts — 4-column electronic flight strips with drag & drop.

import { getStripStates as fetchStripStates, patchStripState } from '../api/client';
import { formatFL, formatSpeed, formatTime, generateSquawk, truncateRoute } from '../efs/format';
import { moveInOrder, sortByUserOrder, sortFlightPlans } from '../efs/ordering';
import { getStripLabel, setStripLabel } from '../lib/storage';
import type { FlightPlan, StripColumn, StripStates } from '../types/api';
import { currentICAO, flightPlans, rerenderStrips } from '../polling';
import { updateSMRAircraft } from '../smr/render';
import { escapeHtml } from './weather';

// Client-side strip states: { "registration": { phase, column } }
let stripStates: StripStates = {};

// Phase -> Column mapping
const PHASE_COLUMN: Record<string, StripColumn> = {
  PRE_TAXI: 'PRE_TAXI',
  PUSHBACK: 'PRE_TAXI',
  TAXI: 'TAXI',
  LINEUP: 'RUNWAY',
  CLEARED: 'RUNWAY',
  APPROACH: 'ARRIVALS',
  LANDED: 'ARRIVALS',
  VACATING: 'ARRIVALS',
};

// Column body ID -> default phase when a strip is dropped there
const COLUMN_DEFAULT_PHASE: Record<string, string> = {
  'strips-pretaxi': 'PRE_TAXI',
  'strips-taxi': 'TAXI',
  'strips-runway': 'LINEUP',
  'strips-arrivals': 'APPROACH',
};

// Column name -> column body element ID (reverse of COLUMN_DEFAULT_PHASE)
const COLUMN_BODY_ID: Record<StripColumn, string> = {
  PRE_TAXI: 'strips-pretaxi',
  TAXI: 'strips-taxi',
  RUNWAY: 'strips-runway',
  ARRIVALS: 'strips-arrivals',
};

let _dropZonesInited = false;

// User-defined strip order within each column
const stripOrder: Partial<Record<StripColumn, string[]>> = {};

const COLUMNS: StripColumn[] = ['PRE_TAXI', 'TAXI', 'RUNWAY', 'ARRIVALS'];

// ---- Strip order helpers ----

function _ensureOrder(reg: string, column: StripColumn): void {
  const order = (stripOrder[column] ??= []);
  if (order.indexOf(reg) === -1) order.push(reg);
}

function _moveOrder(
  dragReg: string,
  targetReg: string,
  insertBefore: boolean,
  targetColumn: StripColumn,
): void {
  // Remove from all columns first
  for (const col of COLUMNS) {
    const order = stripOrder[col];
    if (order) stripOrder[col] = order.filter((r) => r !== dragReg);
  }
  stripOrder[targetColumn] = moveInOrder(stripOrder[targetColumn] ?? [], dragReg, targetReg, insertBefore);
}

// ---- Load strip states from server ----

export function loadStripStates(callback?: () => void): void {
  fetchStripStates()
    .then((data) => {
      stripStates = data || {};
      if (callback) callback();
    })
    .catch(() => {
      if (callback) callback();
    });
}

// ---- Get/Set strip phase ----

export function getStripPhase(reg: string): string {
  return stripStates[reg]?.phase ?? 'PRE_TAXI';
}

export function getStripColumn(reg: string): StripColumn {
  const phase = getStripPhase(reg);
  return PHASE_COLUMN[phase] || 'PRE_TAXI';
}

export function setStripPhase(reg: string, phase: string): void {
  const column = PHASE_COLUMN[phase] || 'PRE_TAXI';
  stripStates[reg] = { phase, column };

  // Persist to server
  patchStripState(reg, phase).catch((err: unknown) => {
    console.error('Failed to save strip state:', err);
  });
}

// ---- Render strips into 4 columns ----

export function renderFlightStrips(plans: FlightPlan[]): void {
  const containers: Record<StripColumn, HTMLElement | null> = {
    PRE_TAXI: document.getElementById('strips-pretaxi'),
    TAXI: document.getElementById('strips-taxi'),
    RUNWAY: document.getElementById('strips-runway'),
    ARRIVALS: document.getElementById('strips-arrivals'),
  };

  if (!containers.PRE_TAXI || !containers.TAXI || !containers.RUNWAY || !containers.ARRIVALS)
    return;

  containers.PRE_TAXI.innerHTML = '';
  containers.TAXI.innerHTML = '';
  containers.RUNWAY.innerHTML = '';
  containers.ARRIVALS.innerHTML = '';

  const counts: Record<StripColumn, number> = { PRE_TAXI: 0, TAXI: 0, RUNWAY: 0, ARRIVALS: 0 };

  if (!plans || plans.length === 0) {
    containers.PRE_TAXI.innerHTML = emptyState();
    containers.ARRIVALS.innerHTML = emptyState();
    updateColumnCounts(counts);
    return;
  }

  // Group plans by column and register in stripOrder
  const byColumn: Record<StripColumn, FlightPlan[]> = {
    PRE_TAXI: [],
    TAXI: [],
    RUNWAY: [],
    ARRIVALS: [],
  };
  plans.forEach((plan) => {
    const reg = plan.aircraft_registration;
    const isArrival = plan.destination_ICAO === currentICAO;
    if (!stripStates[reg]) {
      const defaultPhase = isArrival ? 'APPROACH' : 'PRE_TAXI';
      stripStates[reg] = { phase: defaultPhase, column: PHASE_COLUMN[defaultPhase]! };
    }
    const column = getStripColumn(reg);
    _ensureOrder(reg, column);
    byColumn[column].push(plan);
  });

  // Sort each column by user-defined order, new arrivals go to the end
  COLUMNS.forEach((col) => {
    byColumn[col] = sortByUserOrder(byColumn[col], stripOrder[col] || []);
  });

  // Render each column in order
  COLUMNS.forEach((col) => {
    byColumn[col].forEach((plan) => {
      const reg = plan.aircraft_registration;
      const isArrival = plan.destination_ICAO === currentICAO;
      const strip = createStripElement(plan, getStripPhase(reg), isArrival);
      containers[col]!.appendChild(strip);
      counts[col]++;
    });
  });

  if (counts.PRE_TAXI === 0) containers.PRE_TAXI.innerHTML = emptyState();
  if (counts.TAXI === 0) containers.TAXI.innerHTML = emptyState();
  if (counts.RUNWAY === 0) containers.RUNWAY.innerHTML = emptyState();
  if (counts.ARRIVALS === 0) containers.ARRIVALS.innerHTML = emptyState();

  updateColumnCounts(counts);

  if (!_dropZonesInited) {
    _initDropZones();
    _dropZonesInited = true;
  }
}

function updateColumnCounts(counts: Record<StripColumn, number>): void {
  let el = document.getElementById('count-pretaxi');
  if (el) el.textContent = String(counts.PRE_TAXI);
  el = document.getElementById('count-taxi');
  if (el) el.textContent = String(counts.TAXI);
  el = document.getElementById('count-runway');
  if (el) el.textContent = String(counts.RUNWAY);
  el = document.getElementById('count-arrivals');
  if (el) el.textContent = String(counts.ARRIVALS);
}

function emptyState(): string {
  return (
    '<div class="strips-empty">' +
    '<div class="strips-empty-icon">&#9992;</div>' +
    '<div>Empty</div></div>'
  );
}

// Format helpers now live in src/efs/format.ts (re-exported below).

// ---- Create Strip Card (IVAO paper-strip grid) ----

function createStripElement(plan: FlightPlan, phase: string, isArrival: boolean): HTMLDivElement {
  const strip = document.createElement('div');
  strip.className = 'flight-strip phase-' + phase.toLowerCase();
  strip.dataset.registration = plan.aircraft_registration;
  strip.draggable = true;
  strip.addEventListener('dragstart', (e: DragEvent) => {
    e.dataTransfer?.setData('text/plain', plan.aircraft_registration);
    if (e.dataTransfer) e.dataTransfer.effectAllowed = 'move';
    setTimeout(() => strip.classList.add('dragging'), 0);
  });
  strip.addEventListener('dragend', () => {
    strip.classList.remove('dragging');
  });

  const reg = plan.aircraft_registration;
  const callsign = plan.callsign || reg;
  const isIFR = plan.flight_rules !== 'V';
  const cfl = formatFL(plan.cruising_altitude);
  const spd = formatSpeed(plan.cruising_speed);
  const depTime = formatTime(plan.departure_time);
  const acType = escapeHtml(plan.aircraft_type || '----');
  const wtc = escapeHtml(plan.wake_turbulence_category || '-');
  const squawk = plan.squawk || generateSquawk(reg);
  const depIcao = escapeHtml(plan.departure_ICAO || '----');
  const destIcao = escapeHtml(plan.destination_ICAO || '----');
  const route = escapeHtml(plan.route || 'DCT');
  const remarks = escapeHtml(plan.other_info || plan.remarks || '');

  function lbl(key: string): string {
    return '<div class="fs-cell fs-label" data-key="' + key + '"></div>';
  }

  // Grid layout (4 rows × 5 cols, route spans rows 1-3 in col 5):
  // Row 1: dep | cfl  | callsign | dest    | route (span 3)
  // Row 2: I/V | type | label-1  | empty   |
  // Row 3: --- | spd  | label-2  | depTime |
  // Row 4: sqk | lbl3 | label-4  | label-5 | remarks
  strip.innerHTML =
    '<div class="fs-grid">' +
    // Row 1
    '<div class="fs-cell fs-dep">' + depIcao + '</div>' +
    '<div class="fs-cell fs-cfl">' + cfl + '</div>' +
    '<div class="fs-cell fs-call">' + escapeHtml(callsign) + '</div>' +
    '<div class="fs-cell fs-dest' + (isArrival ? ' fs-arr-dest' : '') + '">' + destIcao + '</div>' +
    '<div class="fs-cell fs-route">' + route + '</div>' +
    // Row 2
    '<div class="fs-cell fs-rules ' + (isIFR ? 'fs-ifr' : 'fs-vfr') + '">' + (isIFR ? 'I' : 'V') + '</div>' +
    '<div class="fs-cell fs-type">' + acType + '/' + wtc + '</div>' +
    lbl('lb1') +
    '<div class="fs-cell fs-emp"></div>' +
    // Row 3
    '<div class="fs-cell fs-emp"></div>' +
    '<div class="fs-cell fs-speed">' + spd + '</div>' +
    lbl('lb2') +
    '<div class="fs-cell fs-time">' + depTime + '</div>' +
    // Row 4
    '<div class="fs-cell fs-squawk">' + squawk + '</div>' +
    lbl('lb3') +
    lbl('lb4') +
    lbl('lb5') +
    '<div class="fs-cell fs-rmk">' + remarks + '</div>' +
    '</div>';

  // Load saved label content from localStorage
  strip.querySelectorAll<HTMLElement>('.fs-label').forEach((label) => {
    const saved = getStripLabel(reg, label.dataset.key ?? '');
    if (saved) label.textContent = saved;
    label.contentEditable = 'true';
  });

  // Labels: pause dragging while editing, save on blur
  strip.querySelectorAll<HTMLElement>('.fs-label').forEach((label) => {
    label.addEventListener('mousedown', (e) => {
      strip.draggable = false;
      e.stopPropagation();
    });
    label.addEventListener('blur', () => {
      strip.draggable = true;
      setStripLabel(reg, label.dataset.key ?? '', (label.textContent ?? '').trim());
      // Reflect updated annotation on the SMR label immediately
      updateSMRAircraft(flightPlans);
    });
    label.addEventListener('keydown', (e: KeyboardEvent) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        label.blur();
      }
    });
  });

  // Intra-column reordering (and cross-column drop at specific position)
  strip.addEventListener('dragover', (e: DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    const rect = strip.getBoundingClientRect();
    const before = e.clientY < rect.top + rect.height / 2;
    strip.dataset.dropInsert = before ? 'before' : 'after';
    strip.classList.toggle('drop-before', before);
    strip.classList.toggle('drop-after', !before);
  });

  strip.addEventListener('dragleave', (e: DragEvent) => {
    if (!strip.contains(e.relatedTarget as Node | null)) {
      strip.classList.remove('drop-before', 'drop-after');
      delete strip.dataset.dropInsert;
    }
  });

  strip.addEventListener('drop', (e: DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    const insertBefore = strip.dataset.dropInsert !== 'after';
    strip.classList.remove('drop-before', 'drop-after');
    delete strip.dataset.dropInsert;

    const dragReg = e.dataTransfer?.getData('text/plain');
    if (!dragReg || dragReg === reg) return;

    const dragColumn = getStripColumn(dragReg);
    const targetColumn = getStripColumn(reg);

    _moveOrder(dragReg, reg, insertBefore, targetColumn);

    if (dragColumn === targetColumn) {
      // Same bay: move the DOM element directly, no full rerender
      let dragEl: HTMLElement | null = null;
      document.querySelectorAll<HTMLElement>('.flight-strip').forEach((el) => {
        if (el.dataset.registration === dragReg) dragEl = el;
      });
      if (dragEl && strip.parentNode) {
        strip.parentNode.insertBefore(dragEl, insertBefore ? strip : strip.nextSibling);
      }
    } else {
      // Different column: change phase then rerender
      const newPhase = COLUMN_DEFAULT_PHASE[COLUMN_BODY_ID[targetColumn]];
      if (newPhase) {
        setStripPhase(dragReg, newPhase);
        rerenderStrips();
      }
    }
  });

  return strip;
}

function _initDropZones(): void {
  Object.keys(COLUMN_DEFAULT_PHASE).forEach((colId) => {
    const col = document.getElementById(colId);
    if (!col) return;

    col.addEventListener('dragover', (e: DragEvent) => {
      e.preventDefault();
      if (e.dataTransfer) e.dataTransfer.dropEffect = 'move';
      col.classList.add('drag-over');
    });

    col.addEventListener('dragleave', (e: DragEvent) => {
      // Only remove if leaving the column itself, not entering a child
      if (!col.contains(e.relatedTarget as Node | null)) {
        col.classList.remove('drag-over');
      }
    });

    col.addEventListener('drop', (e: DragEvent) => {
      e.preventDefault();
      col.classList.remove('drag-over');
      const reg = e.dataTransfer?.getData('text/plain');
      if (!reg) return;
      const newPhase = COLUMN_DEFAULT_PHASE[colId];
      if (newPhase) {
        const targetColumn = PHASE_COLUMN[newPhase] || 'PRE_TAXI';
        // Remove from old column order and append to end of target column
        for (const c of COLUMNS) {
          const order = stripOrder[c];
          if (order) stripOrder[c] = order.filter((r) => r !== reg);
        }
        _ensureOrder(reg, targetColumn);
        if (getStripPhase(reg) !== newPhase) {
          setStripPhase(reg, newPhase);
          rerenderStrips();
        }
      }
    });
  });
}

// Re-export the pure helpers so existing importers keep one entry point.
export { formatFL, formatSpeed, formatTime, generateSquawk, truncateRoute, sortFlightPlans };
