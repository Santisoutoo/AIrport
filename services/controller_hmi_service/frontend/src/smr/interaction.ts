// SMR pan/zoom interaction and middle-button label dragging.

import { setSmrLabelOffset } from '../lib/storage';
import {
  autoFitSMRView,
  rescaleSMRElements,
  SMR_LABEL_DEFAULT_OX,
  SMR_LABEL_DEFAULT_OY,
  smrLabelElByReg,
  smrLabelOffsets,
} from './render';
import { attrNum, smrState, smrSvg } from './state';

let smrDrag: { startX: number; startY: number; startVBx: number; startVBy: number } | null = null;

// Margins between box origin and text origin (kept in sync with render.ts)
const SMR_LBL_TXT_MARGIN_X = 0.4;
const SMR_LBL_TXT_MARGIN_Y = 1.3;

export function initSMRInteraction(): void {
  const svgEl = smrSvg();
  if (!svgEl) return;

  // Zoom with mouse wheel
  svgEl.addEventListener(
    'wheel',
    (e: WheelEvent) => {
      e.preventDefault();
      const zoomFactor = e.deltaY > 0 ? 1.15 : 0.87; // scroll down = zoom out

      // Mouse position in SVG coords
      const rect = svgEl.getBoundingClientRect();
      const mx = (e.clientX - rect.left) / rect.width;
      const my = (e.clientY - rect.top) / rect.height;

      const vb = smrState.viewBox;

      // Point in viewBox under mouse
      const px = vb.x + mx * vb.w;
      const py = vb.y + my * vb.h;

      // New size
      let nw = vb.w * zoomFactor;
      let nh = vb.h * zoomFactor;

      // Clamp: don't zoom out beyond the dynamic max bounds (expanded if ILS active)
      const maxW = smrState.maxBounds.maxX - smrState.maxBounds.minX;
      const maxH = smrState.maxBounds.maxY - smrState.maxBounds.minY;
      const maxSize = Math.max(maxW, maxH);
      if (nw > maxSize) {
        nw = maxSize;
        nh = maxSize;
      }
      // Don't zoom in too far
      if (nw < 5) {
        nw = 5;
        nh = 5;
      }

      // Keep point under mouse fixed
      vb.x = px - mx * nw;
      vb.y = py - my * nh;
      vb.w = nw;
      vb.h = nh;

      clampViewBox();
      applySMRViewBox();
    },
    { passive: false },
  );

  // Pan with mouse drag
  svgEl.addEventListener('mousedown', (e: MouseEvent) => {
    if (e.button !== 0) return; // left button only
    smrDrag = {
      startX: e.clientX,
      startY: e.clientY,
      startVBx: smrState.viewBox.x,
      startVBy: smrState.viewBox.y,
    };
    svgEl.style.cursor = 'grabbing';
    e.preventDefault();
  });

  window.addEventListener('mousemove', (e: MouseEvent) => {
    if (!smrDrag) return;
    const sv = smrSvg();
    if (!sv) return;

    const rect = sv.getBoundingClientRect();
    // Convert pixel delta to viewBox units
    const dx = ((e.clientX - smrDrag.startX) / rect.width) * smrState.viewBox.w;
    const dy = ((e.clientY - smrDrag.startY) / rect.height) * smrState.viewBox.h;

    smrState.viewBox.x = smrDrag.startVBx - dx;
    smrState.viewBox.y = smrDrag.startVBy - dy;

    clampViewBox();
    applySMRViewBox();
  });

  window.addEventListener('mouseup', () => {
    if (smrDrag) {
      smrDrag = null;
      const sv = smrSvg();
      if (sv) sv.style.cursor = 'grab';
    }
  });

  // Double-click to reset view (auto-fit current bounds, ILS included if active)
  svgEl.addEventListener('dblclick', (e: MouseEvent) => {
    e.preventDefault();
    autoFitSMRView();
  });
}

export function clampViewBox(): void {
  const vb = smrState.viewBox;
  const mb = smrState.maxBounds;
  if (vb.x < mb.minX) vb.x = mb.minX;
  if (vb.y < mb.minY) vb.y = mb.minY;
  if (vb.x + vb.w > mb.maxX) vb.x = mb.maxX - vb.w;
  if (vb.y + vb.h > mb.maxY) vb.y = mb.maxY - vb.h;
}

export function applySMRViewBox(): void {
  const svgEl = smrSvg();
  if (!svgEl) return;
  const vb = smrState.viewBox;
  svgEl.setAttribute('viewBox', vb.x + ' ' + vb.y + ' ' + vb.w + ' ' + vb.h);
  rescaleSMRElements();
}

// --- Middle-button drag to reposition SMR labels ---

let _smrLabelDragState: {
  reg: string;
  startX: number;
  startY: number;
  startBgOx: number;
  startBgOy: number;
} | null = null;
let _smrLabelDragInited = false;

export function initSMRLabelDrag(): void {
  const svgEl = smrSvg();
  if (!svgEl) return;

  // Attach middle-mousedown on freshly rendered bg and text elements
  svgEl.querySelectorAll('.smr-label-bg, .smr-label-text').forEach((el) => {
    el.addEventListener('mousedown', (e: Event) => {
      const me = e as MouseEvent;
      if (me.button !== 1) return;
      me.preventDefault();
      const reg = el.getAttribute('data-reg');
      if (!reg) return;
      const bg = smrLabelElByReg(svgEl, 'smr-label-bg', reg);
      if (!bg) return;
      _smrLabelDragState = {
        reg,
        startX: me.clientX,
        startY: me.clientY,
        startBgOx: attrNum(bg, 'data-base-ox'),
        startBgOy: attrNum(bg, 'data-base-oy'),
      };
      svgEl.style.cursor = 'move';
    });
  });

  // Window-level handlers registered only once for the lifetime of the page
  if (_smrLabelDragInited) return;
  _smrLabelDragInited = true;

  window.addEventListener('mousemove', (e: MouseEvent) => {
    if (!_smrLabelDragState) return;
    const sv = smrSvg();
    if (!sv) return;

    const rect = sv.getBoundingClientRect();
    // Delta in base SVG units (scale-independent: 100 / rendered px)
    const dOx = ((e.clientX - _smrLabelDragState.startX) * 100) / rect.width;
    const dOy = ((e.clientY - _smrLabelDragState.startY) * 100) / rect.height;

    const reg = _smrLabelDragState.reg;
    const newBgOx = _smrLabelDragState.startBgOx + dOx;
    const newBgOy = _smrLabelDragState.startBgOy + dOy;

    const bg = smrLabelElByReg(sv, 'smr-label-bg', reg);
    const txt = smrLabelElByReg(sv, 'smr-label-text', reg);

    if (!bg) return;

    bg.setAttribute('data-base-ox', String(newBgOx));
    bg.setAttribute('data-base-oy', String(newBgOy));
    if (txt) {
      txt.setAttribute('data-base-ox', String(newBgOx + SMR_LBL_TXT_MARGIN_X));
      txt.setAttribute('data-base-oy', String(newBgOy + SMR_LBL_TXT_MARGIN_Y));
    }

    rescaleSMRElements();
  });

  window.addEventListener('mouseup', (e: MouseEvent) => {
    if (!_smrLabelDragState || e.button !== 1) return;
    const reg = _smrLabelDragState.reg;
    const sv = smrSvg();
    const bg = sv ? smrLabelElByReg(sv, 'smr-label-bg', reg) : null;
    if (bg) {
      const finalOx = attrNum(bg, 'data-base-ox');
      const finalOy = attrNum(bg, 'data-base-oy');
      // Store offset relative to the hardcoded defaults
      const offset = { ox: finalOx - SMR_LABEL_DEFAULT_OX, oy: finalOy - SMR_LABEL_DEFAULT_OY };
      smrLabelOffsets[reg] = offset;
      setSmrLabelOffset(reg, offset);
    }
    _smrLabelDragState = null;
    if (sv) sv.style.cursor = 'grab';
  });
}
