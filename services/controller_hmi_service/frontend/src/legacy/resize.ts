// resize.ts — draggable panel splitters; sizes persisted in localStorage.

import { getPanelSizes, setPanelSizes, type PanelSizes } from '../lib/storage';

const HANDLE_PX = 5;
const MINS = { leftW: 500, dashH: 60, bottomH: 80, commsH: 120 } as const;
const STRIPS_MIN = 100;

let twrLayout: HTMLElement;
let leftPanel: HTMLElement;
let rightPanel: HTMLElement;
let dashEl: HTMLElement;
let bottomEl: HTMLElement;
let commsEl: HTMLElement;

let STATE: PanelSizes = { leftW: 0, dashH: 0, bottomH: 0, commsH: 0 };

function clamp(v: number, lo: number, hi: number): number {
  return Math.min(Math.max(v, lo), hi);
}

function maxLeftW(): number {
  return twrLayout.offsetWidth - 280 - HANDLE_PX;
}
function maxDashH(): number {
  return twrLayout.offsetHeight - STATE.bottomH - STRIPS_MIN - HANDLE_PX * 2;
}
function maxBottomH(): number {
  return twrLayout.offsetHeight - STATE.dashH - STRIPS_MIN - HANDLE_PX * 2;
}
function maxCommsH(): number {
  return twrLayout.offsetHeight - 80;
}

function clampState(): void {
  STATE.leftW = clamp(STATE.leftW, MINS.leftW, maxLeftW());
  STATE.dashH = clamp(STATE.dashH, MINS.dashH, maxDashH());
  STATE.bottomH = clamp(STATE.bottomH, MINS.bottomH, maxBottomH());
  STATE.commsH = clamp(STATE.commsH, MINS.commsH, maxCommsH());
}

function applyLayout(): void {
  leftPanel.style.flex = '0 0 ' + STATE.leftW + 'px';
  rightPanel.style.flex = '1 1 0';
  rightPanel.style.minWidth = '280px';

  dashEl.style.height = STATE.dashH + 'px';
  dashEl.style.flexShrink = '0';
  dashEl.style.flexGrow = '0';
  dashEl.style.overflow = 'hidden';

  bottomEl.style.height = STATE.bottomH + 'px';
  bottomEl.style.flexShrink = '0';
  bottomEl.style.flexGrow = '0';
  bottomEl.style.overflow = 'hidden';

  commsEl.style.height = STATE.commsH + 'px';
}

function wireHandle(
  id: string,
  vertical: boolean,
  getSnap: () => number,
  onDelta: (snap: number, dx: number, dy: number) => void,
): void {
  const el = document.getElementById(id);
  if (!el) return;
  el.addEventListener('mousedown', (e: MouseEvent) => {
    if (e.button !== 0) return;
    e.preventDefault();
    const x0 = e.clientX;
    const y0 = e.clientY;
    const snap = getSnap();
    el.classList.add('resize-handle--dragging');
    document.body.style.cursor = vertical ? 'col-resize' : 'row-resize';
    document.body.style.userSelect = 'none';

    function onMove(ev: MouseEvent): void {
      onDelta(snap, ev.clientX - x0, ev.clientY - y0);
      applyLayout();
    }
    function onUp(): void {
      el!.classList.remove('resize-handle--dragging');
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
      clampState();
      applyLayout();
      setPanelSizes(STATE);
    }
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  });
}

function wireHandles(): void {
  // Vertical splitter: left vs right panel (drag right = left panel wider)
  wireHandle(
    'rh-lr',
    true,
    () => STATE.leftW,
    (s, dx) => {
      STATE.leftW = clamp(s + dx, MINS.leftW, maxLeftW());
    },
  );

  // Horizontal splitter: below dashboard (drag down = dashboard taller)
  wireHandle(
    'rh-dash',
    false,
    () => STATE.dashH,
    (s, _dx, dy) => {
      STATE.dashH = clamp(s + dy, MINS.dashH, maxDashH());
    },
  );

  // Horizontal splitter: above bottom-bar (drag up = bottom-bar taller)
  wireHandle(
    'rh-wind',
    false,
    () => STATE.bottomH,
    (s, _dx, dy) => {
      STATE.bottomH = clamp(s - dy, MINS.bottomH, maxBottomH());
    },
  );

  // Horizontal splitter: above comms panel (drag up = comms taller)
  wireHandle(
    'rh-comms',
    false,
    () => STATE.commsH,
    (s, _dx, dy) => {
      STATE.commsH = clamp(s - dy, MINS.commsH, maxCommsH());
    },
  );
}

function init(): void {
  const layout = document.getElementById('twr-layout');
  const left = document.getElementById('left-panel');
  const right = document.getElementById('right-panel');
  const dash = document.getElementById('dashboard-superior');
  const bottom = document.getElementById('bottom-bar');
  const comms = document.getElementById('comms-panel');

  if (!layout || !left || !right || !dash || !bottom || !comms) return;
  twrLayout = layout;
  leftPanel = left;
  rightPanel = right;
  dashEl = dash;
  bottomEl = bottom;
  commsEl = comms;

  const saved = getPanelSizes();
  if (saved) {
    STATE = saved;
  } else {
    STATE.leftW = leftPanel.offsetWidth;
    STATE.dashH = dashEl.offsetHeight;
    STATE.bottomH = bottomEl.offsetHeight;
    STATE.commsH = commsEl.offsetHeight;
  }

  clampState();
  applyLayout();
  wireHandles();

  window.addEventListener('resize', () => {
    clampState();
    applyLayout();
  });
}

document.addEventListener('DOMContentLoaded', init);
