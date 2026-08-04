// SMR rendering: airport layout SVG, ILS centerline, zoom-invariant
// rescaling, and the Aurora-style aircraft labels.

import { getAirportGraph } from '../api/client';
import { getSmrLabelOffset, getStripLabel } from '../lib/storage';
import { getStripColumn, getStripPhase } from '../legacy/efs';
import { escapeHtml } from '../legacy/weather';
import { formatFL, formatSpeed, generateSquawk } from '../efs/format';
import type { FlightPlan, RunwayEnd, StripColumn } from '../types/api';
import { getLivePositions } from '../polling';
import { updateRunwaySelector } from '../runway-sequence';
import { initSMRInteraction, initSMRLabelDrag } from './interaction';
import {
  bearingDeg,
  leaderAttachPoint,
  projectGeoFromBearing,
  type Point,
} from './projection';
import { computeSmrBounds } from './projection';
import { attrNum, smrState, smrSvg, toSVG } from './state';

const ILS_RANGE_NM = 10;
const ILS_TICK_NM = 1;
const ILS_TICK_HALF_NM = 0.15;

// Margins between box origin and text origin (in base SVG units, constant)
const SMR_LBL_TXT_MARGIN_X = 0.4;
const SMR_LBL_TXT_MARGIN_Y = 1.3;

export const SMR_LABEL_DEFAULT_OX = 1.8;
export const SMR_LABEL_DEFAULT_OY = -5.0;

// Persisted user-drag offsets, lazy-loaded per registration.
export const smrLabelOffsets: Record<string, { ox: number; oy: number }> = {};

export function initSMRMap(): void {
  const container = document.getElementById('smr-map');
  if (!container) return;

  container.innerHTML =
    '<svg viewBox="0 0 100 100"><text x="50" y="50" text-anchor="middle" fill="#5a6672" font-size="3.5" font-family="monospace">Loading airport data...</text></svg>';

  getAirportGraph()
    .then((data) => {
      smrState.graph = data;
      smrState.bounds = computeSmrBounds(data);
      renderSMRFromData();
      updateRunwaySelector();
    })
    .catch((err: unknown) => {
      console.error('Failed to load airport graph:', err);
      container.innerHTML =
        '<svg viewBox="0 0 100 100"><text x="50" y="50" text-anchor="middle" fill="#ff1744" font-size="3" font-family="monospace">No airport data</text></svg>';
    });
}

export function renderSMRFromData(): void {
  const container = document.getElementById('smr-map');
  const graph = smrState.graph;
  if (!container || !graph || !smrState.bounds) return;

  smrState.viewBox = { x: 0, y: 0, w: 100, h: 100 };

  let svg = '<svg id="smr-svg" viewBox="0 0 100 100" preserveAspectRatio="xMidYMid meet" style="cursor:grab">';

  // Background grid
  for (let gx = 0; gx <= 100; gx += 10) {
    svg += '<line x1="' + gx + '" y1="0" x2="' + gx + '" y2="100" stroke="#0d1520" stroke-width="0.15" vector-effect="non-scaling-stroke"/>';
  }
  for (let gy = 0; gy <= 100; gy += 10) {
    svg += '<line x1="0" y1="' + gy + '" x2="100" y2="' + gy + '" stroke="#0d1520" stroke-width="0.15" vector-effect="non-scaling-stroke"/>';
  }

  // --- Runways ---
  graph.runways.forEach((rwy) => {
    const p1 = toSVG(rwy.end1.lat, rwy.end1.lon);
    const p2 = toSVG(rwy.end2.lat, rwy.end2.lon);

    // Thick runway strip
    svg +=
      '<line id="smr-runway-rect" x1="' + p1.x + '" y1="' + p1.y +
      '" x2="' + p2.x + '" y2="' + p2.y +
      '" stroke="#1a3a1a" stroke-width="3" stroke-linecap="round"/>';

    // Centerline dashes
    svg +=
      '<line x1="' + p1.x + '" y1="' + p1.y +
      '" x2="' + p2.x + '" y2="' + p2.y +
      '" stroke="#2a4a2a" stroke-width="0.3" stroke-dasharray="1.5,1.5"/>';

    // Designators
    svg +=
      '<text x="' + p1.x + '" y="' + (p1.y - 1.5) +
      '" text-anchor="middle" fill="#3a6a3a" data-base-fs="2.5" font-size="2.5" font-family="monospace" font-weight="700">' +
      rwy.end1.designator + '</text>';
    svg +=
      '<text x="' + p2.x + '" y="' + (p2.y + 3) +
      '" text-anchor="middle" fill="#3a6a3a" data-base-fs="2.5" font-size="2.5" font-family="monospace" font-weight="700">' +
      rwy.end2.designator + '</text>';
  });

  // --- Taxiway edges ---
  // One label per unique taxiway name, positioned at the average of all matching elements
  const labelByName: Record<string, { sx: number; sy: number; n: number }> = {};

  graph.edges.forEach((edge) => {
    const n1 = graph.nodes[edge.from];
    const n2 = graph.nodes[edge.to];
    if (!n1 || !n2) return;

    const p1 = toSVG(n1.lat, n1.lon);
    const p2 = toSVG(n2.lat, n2.lon);

    const isRunway = edge.category === 'runway';

    const color = isRunway ? '#1a3a1a' : '#243a55';
    const width = isRunway ? '1.5' : '0.8';

    svg +=
      '<line x1="' + p1.x + '" y1="' + p1.y +
      '" x2="' + p2.x + '" y2="' + p2.y +
      '" stroke="' + color + '" stroke-width="' + width + '" stroke-linecap="round"/>';

    if (!isRunway && edge.name && edge.name !== 'Unnamed edge') {
      const entry = (labelByName[edge.name] ??= { sx: 0, sy: 0, n: 0 });
      entry.sx += (p1.x + p2.x) / 2;
      entry.sy += (p1.y + p2.y) / 2;
      entry.n++;
    }
  });

  // Also accumulate clean named taxi nodes (skip internal routing names)
  Object.keys(graph.nodes).forEach((id) => {
    const n = graph.nodes[id]!;
    if (!n.name) return;
    if (/^Node\s+\d+$/.test(n.name)) return;
    if (n.name.indexOf('_') !== -1) return;
    if (n.name.length > 4) return;
    const pn = toSVG(n.lat, n.lon);
    const entry = (labelByName[n.name] ??= { sx: 0, sy: 0, n: 0 });
    entry.sx += pn.x;
    entry.sy += pn.y;
    entry.n++;
  });

  // --- Taxiway labels: one per name at the average position ---
  Object.keys(labelByName).forEach((name) => {
    const d = labelByName[name]!;
    const mx = d.sx / d.n;
    const my = d.sy / d.n;
    // Smaller, less obtrusive marker
    svg +=
      '<circle class="smr-twy-label-bg" cx="' + mx + '" cy="' + my +
      '" r="1.1" data-base-r="1.1"' +
      ' fill="#1a1108" stroke="#5a3a10" stroke-width="0.2" opacity="0.9"/>';
    svg +=
      '<text x="' + mx + '" y="' + my +
      '" text-anchor="middle" dominant-baseline="central"' +
      ' fill="#ffc94a" data-base-fs="1.4" font-size="1.4"' +
      ' font-family="monospace" font-weight="700">' +
      name + '</text>';
  });

  // --- Stands / Gates ---
  graph.stands.forEach((stand) => {
    const p = toSVG(stand.lat, stand.lon);

    const isMil = stand.name.indexOf('Mil') !== -1;
    const isGA =
      stand.size_cats &&
      (stand.size_cats.indexOf('helos') !== -1 || stand.size_cats.indexOf('props') !== -1);
    const dotColor = isMil ? '#6a7a8a' : isGA ? '#3a80c0' : '#00e5ff';

    svg +=
      '<rect class="smr-stand" data-cx="' + p.x + '" data-cy="' + p.y +
      '" x="' + (p.x - 0.6) + '" y="' + (p.y - 0.6) +
      '" width="1.2" height="1.2" data-base-size="1.2" fill="' + dotColor +
      '" opacity="0.9" rx="0.2"/>';

    svg +=
      '<text class="smr-stand-label" x="' + p.x + '" y="' + (p.y + 2.2) +
      '" data-cy="' + p.y + '" data-base-dy="1.2"' +
      ' text-anchor="middle" fill="' + dotColor +
      '" stroke="#040c16" stroke-width="2" data-base-sw="2" paint-order="stroke"' +
      ' data-base-fs="1.3" font-size="1.3" font-family="monospace" font-weight="bold">' +
      stand.name + '</text>';
  });

  // --- Taxi nodes (dim dots) ---
  Object.keys(graph.nodes).forEach((id) => {
    const n = graph.nodes[id]!;
    const p = toSVG(n.lat, n.lon);
    svg += '<circle cx="' + p.x + '" cy="' + p.y + '" r="0.3" data-base-r="0.3" fill="#1a2a3a" opacity="0.2"/>';
  });

  // Aircraft overlay group (on top)
  svg += '<g id="smr-ils-group"></g>';
  svg += '<g id="smr-aircraft-group"></g>';

  svg += '</svg>';
  container.innerHTML = svg;

  initSMRInteraction();
  drawILSCenterline();
}

export function setILSForArrivalRunway(rawDesignator: string | null | undefined): void {
  if (rawDesignator == null) {
    smrState.activeILSRunway = null;
  } else {
    const token = String(rawDesignator).trim().toUpperCase().split(/[\s/]+/)[0];
    smrState.activeILSRunway = token || null;
  }
  drawILSCenterline();
  autoFitSMRView();
}

function _findRunwayEnds(designator: string): { threshold: RunwayEnd; otherEnd: RunwayEnd } | null {
  if (!smrState.graph) return null;
  for (const r of smrState.graph.runways) {
    if (r.end1.designator === designator) return { threshold: r.end1, otherEnd: r.end2 };
    if (r.end2.designator === designator) return { threshold: r.end2, otherEnd: r.end1 };
  }
  return null;
}

export function autoFitSMRView(): void {
  let minX = 0,
    minY = 0,
    maxX = 100,
    maxY = 100;

  if (smrState.activeILSRunway && smrState.graph && smrState.bounds) {
    const ends = _findRunwayEnds(smrState.activeILSRunway);
    if (ends) {
      const { threshold, otherEnd } = ends;
      const brDeg = bearingDeg(otherEnd.lat, otherEnd.lon, threshold.lat, threshold.lon);
      const endGeo = projectGeoFromBearing(threshold.lat, threshold.lon, brDeg, ILS_RANGE_NM);
      const endSvg = toSVG(endGeo.lat, endGeo.lon);
      const pad = 5;
      minX = Math.min(minX, endSvg.x - pad);
      minY = Math.min(minY, endSvg.y - pad);
      maxX = Math.max(maxX, endSvg.x + pad);
      maxY = Math.max(maxY, endSvg.y + pad);
    }
  }

  smrState.maxBounds = { minX, minY, maxX, maxY };

  const w = maxX - minX;
  const h = maxY - minY;
  const size = Math.max(w, h);
  const cx = (minX + maxX) / 2;
  const cy = (minY + maxY) / 2;
  smrState.viewBox = { x: cx - size / 2, y: cy - size / 2, w: size, h: size };

  const svgEl = smrSvg();
  if (svgEl) {
    svgEl.setAttribute(
      'viewBox',
      smrState.viewBox.x + ' ' + smrState.viewBox.y + ' ' + smrState.viewBox.w + ' ' + smrState.viewBox.h,
    );
    rescaleSMRElements();
  }
}

export function drawILSCenterline(): void {
  const group = document.getElementById('smr-ils-group');
  if (!group) return;
  group.innerHTML = '';
  if (!smrState.activeILSRunway || !smrState.graph || !smrState.bounds) return;

  const ends = _findRunwayEnds(smrState.activeILSRunway);
  if (!ends) return;
  const { threshold, otherEnd } = ends;

  // Bearing from otherEnd -> threshold = landing direction
  const landingBrg = bearingDeg(otherEnd.lat, otherEnd.lon, threshold.lat, threshold.lon);
  const perpDeg = (landingBrg + 90) % 360;

  const thrSvg = toSVG(threshold.lat, threshold.lon);
  const endGeo = projectGeoFromBearing(threshold.lat, threshold.lon, landingBrg, ILS_RANGE_NM);
  const endSvg = toSVG(endGeo.lat, endGeo.lon);

  let svg =
    '<line x1="' + thrSvg.x + '" y1="' + thrSvg.y +
    '" x2="' + endSvg.x + '" y2="' + endSvg.y +
    '" stroke="#00aaff" stroke-width="0.4" stroke-dasharray="1.5,1"' +
    ' vector-effect="non-scaling-stroke" opacity="0.85"/>';

  for (let n = ILS_TICK_NM; n <= ILS_RANGE_NM; n += ILS_TICK_NM) {
    const c = projectGeoFromBearing(threshold.lat, threshold.lon, landingBrg, n);
    const a = projectGeoFromBearing(c.lat, c.lon, perpDeg, ILS_TICK_HALF_NM);
    const b = projectGeoFromBearing(c.lat, c.lon, perpDeg, -ILS_TICK_HALF_NM);
    const pa = toSVG(a.lat, a.lon);
    const pb = toSVG(b.lat, b.lon);
    svg +=
      '<line x1="' + pa.x + '" y1="' + pa.y +
      '" x2="' + pb.x + '" y2="' + pb.y +
      '" stroke="#00aaff" stroke-width="0.5"' +
      ' vector-effect="non-scaling-stroke" opacity="0.85"/>';
  }
  group.innerHTML = svg;
}

// --- Rescale elements to keep constant visual size at any zoom level ---

export function rescaleSMRElements(): void {
  const svgEl = smrSvg();
  if (!svgEl) return;

  const s = smrState.viewBox.w / 100; // zoom scale: 1 = no zoom, 0.1 = zoomed 10x
  // Label SIZE scale: full visual size at ≥3x zoom (s≤0.35), shrinks when zoomed out.
  // Position offsets (distance from dot) still use s → fixed visual gap at all zooms.
  const sL = Math.min(s, 0.35);

  // Rescale all text with data-base-fs
  svgEl.querySelectorAll('text[data-base-fs]').forEach((t) => {
    t.setAttribute('font-size', String(attrNum(t, 'data-base-fs') * s));
  });

  // Rescale and reposition stand labels
  const showLabels = s < 0.28;
  svgEl.querySelectorAll<SVGTextElement>('.smr-stand-label').forEach((lbl) => {
    const lcy = attrNum(lbl, 'data-cy');
    const baseDy = attrNum(lbl, 'data-base-dy');
    const baseSw = attrNum(lbl, 'data-base-sw');
    // Keep label just below the stand square at any zoom level
    lbl.setAttribute('y', String(lcy + baseDy * s + 0.6 * s));
    lbl.setAttribute('stroke-width', String(baseSw * s));
    lbl.style.display = showLabels ? '' : 'none';
  });

  // Rescale stand rects (commercial)
  svgEl.querySelectorAll('rect.smr-stand').forEach((rect) => {
    const cx = attrNum(rect, 'data-cx');
    const cy = attrNum(rect, 'data-cy');
    const sz = attrNum(rect, 'data-base-size') * s;
    rect.setAttribute('x', String(cx - sz / 2));
    rect.setAttribute('y', String(cy - sz / 2));
    rect.setAttribute('width', String(sz));
    rect.setAttribute('height', String(sz));
    rect.setAttribute('rx', String(0.3 * s));
  });

  // Rescale node circles
  svgEl.querySelectorAll('circle[data-base-r]').forEach((c) => {
    c.setAttribute('r', String(attrNum(c, 'data-base-r') * s));
  });

  // Aurora label background rects
  // Position (x,y) uses s → fixed visual gap from dot at all zooms.
  // Size (w,h,rx,sw) uses sL → shrinks when zoomed out, full size at ≥3x zoom.
  svgEl.querySelectorAll('.smr-label-bg').forEach((lbEl) => {
    const dotX = attrNum(lbEl, 'data-dot-x');
    const dotY = attrNum(lbEl, 'data-dot-y');
    lbEl.setAttribute('x', String(dotX + attrNum(lbEl, 'data-base-ox') * sL));
    lbEl.setAttribute('y', String(dotY + attrNum(lbEl, 'data-base-oy') * sL));
    lbEl.setAttribute('width', String(attrNum(lbEl, 'data-base-w') * sL));
    lbEl.setAttribute('height', String(attrNum(lbEl, 'data-base-h') * sL));
    lbEl.setAttribute('rx', String(attrNum(lbEl, 'data-base-rx') * sL));
    lbEl.setAttribute('stroke-width', String(attrNum(lbEl, 'data-base-sw') * sL));
  });

  // Aurora label leader lines — attach to nearest box edge
  svgEl.querySelectorAll('.smr-label-line').forEach((llEl) => {
    const dotX = attrNum(llEl, 'data-dot-x');
    const dotY = attrNum(llEl, 'data-dot-y');
    llEl.setAttribute('x1', String(dotX));
    llEl.setAttribute('y1', String(dotY));
    llEl.setAttribute('stroke-width', String(attrNum(llEl, 'data-base-sw') * sL));

    // Look up matching bg rect to get current box geometry
    const reg = llEl.getAttribute('data-reg');
    const bg = reg ? smrLabelElByReg(svgEl, 'smr-label-bg', reg) : null;
    if (bg) {
      const boxX = dotX + attrNum(bg, 'data-base-ox') * sL;
      const boxY = dotY + attrNum(bg, 'data-base-oy') * sL;
      const att = leaderAttachPoint(
        dotX,
        dotY,
        boxX,
        boxY,
        attrNum(bg, 'data-base-w') * sL,
        attrNum(bg, 'data-base-h') * sL,
      );
      llEl.setAttribute('x2', String(att.x));
      llEl.setAttribute('y2', String(att.y));
    }
  });

  // Aurora label text blocks (position uses s, line-spacing uses sL)
  svgEl.querySelectorAll('.smr-label-text').forEach((ltEl) => {
    const dotX = attrNum(ltEl, 'data-dot-x');
    const dotY = attrNum(ltEl, 'data-dot-y');
    const baseDy = attrNum(ltEl, 'data-base-dy');
    const newX = dotX + attrNum(ltEl, 'data-base-ox') * sL;
    const newY = dotY + attrNum(ltEl, 'data-base-oy') * sL;
    ltEl.setAttribute('x', String(newX));
    ltEl.setAttribute('y', String(newY));
    ltEl.querySelectorAll('tspan').forEach((tspan, idx) => {
      tspan.setAttribute('x', String(newX));
      if (idx > 0) tspan.setAttribute('dy', String(baseDy * sL));
    });
  });

  // Aurora label font size (separate from generic text loop, uses sL)
  svgEl.querySelectorAll('text[data-lbl-fs]').forEach((el) => {
    el.setAttribute('font-size', String(attrNum(el, 'data-lbl-fs') * sL));
  });
}

export function smrLabelElByReg(svgEl: SVGSVGElement, cls: string, reg: string): Element | null {
  const els = svgEl.querySelectorAll('.' + cls);
  for (const el of els) {
    if (el.getAttribute('data-reg') === reg) return el;
  }
  return null;
}

function renderSMRLabel(pos: Point, plan: FlightPlan, column: StripColumn, phase: string): string {
  const reg = plan.aircraft_registration;

  // Lazy-load persisted drag offset
  if (!smrLabelOffsets[reg]) {
    smrLabelOffsets[reg] = getSmrLabelOffset(reg);
  }
  const userOx = smrLabelOffsets[reg]!.ox;
  const userOy = smrLabelOffsets[reg]!.oy;

  const typeWtc = escapeHtml(
    (plan.aircraft_type || '----') + '/' + (plan.wake_turbulence_category || '-'),
  );
  const squawk = escapeHtml(String(plan.squawk || generateSquawk(reg)));
  const depDest = escapeHtml((plan.departure_ICAO || '----') + '>' + (plan.destination_ICAO || '----'));
  const cflSpd = escapeHtml(formatFL(plan.cruising_altitude) + ' ' + formatSpeed(plan.cruising_speed));

  // Strip annotation labels lb1–lb5 from localStorage
  const lblParts: string[] = [];
  ['lb1', 'lb2', 'lb3', 'lb4', 'lb5'].forEach((key) => {
    const v = getStripLabel(reg, key);
    if (v && v.trim()) lblParts.push(v.trim());
  });
  const annotation = lblParts.join('  ');

  const isRunway = column === 'RUNWAY';
  const isIncursion = isRunway && phase !== 'CLEARED' && phase !== 'LINEUP';
  const dotColor = isIncursion ? '#ff1744' : isRunway ? '#00e5ff' : '#ffc94a';
  const dimColor = isIncursion
    ? 'rgba(255,23,68,0.60)'
    : isRunway
      ? 'rgba(0,229,255,0.55)'
      : 'rgba(255,201,74,0.55)';
  const noteColor = 'rgba(220,220,255,0.85)';

  const dx = pos.x,
    dy = pos.y;

  const LINE_DY = 1.78;
  const BOX_OX = SMR_LABEL_DEFAULT_OX + userOx;
  const BOX_OY = SMR_LABEL_DEFAULT_OY + userOy;
  const BOX_W = 13.5;
  const BOX_H = LINE_DY * (annotation ? 6 : 5) + 2.0;
  const TXT_OX = BOX_OX + SMR_LBL_TXT_MARGIN_X;
  const TXT_OY = BOX_OY + SMR_LBL_TXT_MARGIN_Y;
  const eReg = escapeHtml(reg);
  const callsign = plan.callsign || reg;
  const eCallsign = escapeHtml(callsign);
  let svg = '';

  // Background rect (cursor:move signals middle-drag)
  svg +=
    '<rect class="smr-label-bg" data-reg="' + eReg + '"' +
    ' x="' + (dx + BOX_OX) + '" y="' + (dy + BOX_OY) + '"' +
    ' width="' + BOX_W + '" height="' + BOX_H + '"' +
    ' data-dot-x="' + dx + '" data-dot-y="' + dy + '"' +
    ' data-base-ox="' + BOX_OX + '" data-base-oy="' + BOX_OY + '"' +
    ' data-base-w="' + BOX_W + '" data-base-h="' + BOX_H + '"' +
    ' data-base-rx="0.4" data-base-sw="0.15"' +
    ' fill="rgba(4,12,22,0.85)" stroke="' + dotColor + '" stroke-width="0.15" rx="0.4"' +
    ' style="cursor:move"/>';

  // Leader line: dot → nearest edge of label box
  const lp = leaderAttachPoint(dx, dy, dx + BOX_OX, dy + BOX_OY, BOX_W, BOX_H);
  svg +=
    '<line class="smr-label-line" data-reg="' + eReg + '"' +
    ' x1="' + dx + '" y1="' + dy + '"' +
    ' x2="' + lp.x + '" y2="' + lp.y + '"' +
    ' data-dot-x="' + dx + '" data-dot-y="' + dy + '"' +
    ' data-base-sw="0.12"' +
    ' stroke="' + dotColor + '" stroke-width="0.12" opacity="0.6"/>';

  // Label text block
  svg +=
    '<text class="smr-label-text" data-reg="' + eReg + '"' +
    ' x="' + (dx + TXT_OX) + '" y="' + (dy + TXT_OY) + '"' +
    ' data-dot-x="' + dx + '" data-dot-y="' + dy + '"' +
    ' data-base-ox="' + TXT_OX + '" data-base-oy="' + TXT_OY + '"' +
    ' data-lbl-fs="1.7" data-base-dy="' + LINE_DY + '"' +
    ' font-size="1.7" font-family="monospace" style="cursor:move">';
  svg += '<tspan x="' + (dx + TXT_OX) + '" dy="0" fill="' + dotColor + '" font-weight="700">' + eCallsign + '</tspan>';
  svg += '<tspan x="' + (dx + TXT_OX) + '" dy="' + LINE_DY + '" fill="' + dimColor + '">' + typeWtc + '</tspan>';
  svg += '<tspan x="' + (dx + TXT_OX) + '" dy="' + LINE_DY + '" fill="' + dimColor + '">' + squawk + '</tspan>';
  svg += '<tspan x="' + (dx + TXT_OX) + '" dy="' + LINE_DY + '" fill="' + dimColor + '">' + depDest + '</tspan>';
  svg += '<tspan x="' + (dx + TXT_OX) + '" dy="' + LINE_DY + '" fill="' + dimColor + '">' + cflSpd + '</tspan>';
  if (annotation) {
    svg +=
      '<tspan x="' + (dx + TXT_OX) + '" dy="' + LINE_DY + '" fill="' + noteColor + '">' +
      escapeHtml(annotation) + '</tspan>';
  }
  svg += '</text>';

  return svg;
}

// --- Place aircraft on SMR based on strip phase ---

export function updateSMRAircraft(plans: FlightPlan[]): void {
  const group = document.getElementById('smr-aircraft-group');
  const graph = smrState.graph;
  if (!group || !graph || !smrState.bounds) return;

  group.innerHTML = '';
  if (!plans || plans.length === 0) return;

  // Build zone positions from real data
  const standPositions: Point[] = [];
  const taxiPositions: Point[] = [];
  const runwayPositions: Point[] = [];

  graph.stands.forEach((s) => {
    standPositions.push(toSVG(s.lat, s.lon));
  });

  // Collect unique taxiway node positions
  const seenTaxiNodes: Record<string, boolean> = {};
  graph.edges.forEach((edge) => {
    if (edge.category !== 'runway') {
      if (!seenTaxiNodes[edge.from]) {
        const n = graph.nodes[edge.from];
        if (n) {
          taxiPositions.push(toSVG(n.lat, n.lon));
          seenTaxiNodes[edge.from] = true;
        }
      }
    }
  });

  // Interpolated positions along runway
  graph.runways.forEach((rwy) => {
    const p1 = toSVG(rwy.end1.lat, rwy.end1.lon);
    const p2 = toSVG(rwy.end2.lat, rwy.end2.lon);
    for (let t = 0.2; t <= 0.8; t += 0.1) {
      runwayPositions.push({
        x: p1.x + (p2.x - p1.x) * t,
        y: p1.y + (p2.y - p1.y) * t,
      });
    }
  });

  const counters: Record<string, number> = { PRE_TAXI: 0, TAXI: 0, RUNWAY: 0 };
  const livePositions = getLivePositions();
  let html = '';

  plans.forEach((plan) => {
    const reg = plan.aircraft_registration;
    const column = getStripColumn(reg);
    const phase = getStripPhase(reg);
    const idx = counters[column] ?? 0;
    counters[column] = idx + 1;
    let pos: Point;

    // 1) Preferred: live lat/lon from the Redis state store
    const live = livePositions[reg];
    if (live && isFinite(live.latitude) && isFinite(live.longitude)) {
      pos = toSVG(live.latitude, live.longitude);
    }
    // 2) Fallback: place by column index when no live position is available
    else if (column === 'PRE_TAXI' && standPositions.length > 0) {
      pos = standPositions[idx % standPositions.length]!;
    } else if (column === 'TAXI' && taxiPositions.length > 0) {
      pos = taxiPositions[idx % taxiPositions.length]!;
    } else if (column === 'RUNWAY' && runwayPositions.length > 0) {
      pos = runwayPositions[idx % runwayPositions.length]!;
    } else {
      pos = { x: 50, y: 50 };
    }

    let dotClass = 'smr-aircraft-dot';
    if (column === 'RUNWAY' && (phase === 'CLEARED' || phase === 'LINEUP')) {
      dotClass += ' cleared';
    } else if (column === 'RUNWAY') {
      dotClass += ' incursion';
    } else if (column === 'TAXI') {
      dotClass += ' on-runway';
    }

    html +=
      '<circle class="' + dotClass + '" cx="' + pos.x + '" cy="' + pos.y + '" r="1.0" data-base-r="1.0"/>' +
      renderSMRLabel(pos, plan, column, phase);
  });
  group.innerHTML = html;
  // Rescale immediately to match current zoom level
  rescaleSMRElements();
  // Attach middle-button drag handlers to the freshly rendered labels
  initSMRLabelDrag();
}
