// app.ts — main application controller & SMR map.

import {
  getAircraftPositions,
  getAirport,
  getAirportGraph,
  getStrips,
  getTaf,
  getWeather,
} from '../api/client';
import { getSmrLabelOffset, getStripLabel, setSmrLabelOffset } from '../lib/storage';
import {
  bearingDeg,
  computeSmrBounds,
  geoToSVG,
  leaderAttachPoint,
  projectGeoFromBearing,
  type Point,
  type SmrBounds,
} from '../smr/projection';
import type {
  AircraftPosition,
  AirportGraph,
  FlightPlan,
  RunwayEnd,
  StripColumn,
} from '../types/api';
import {
  formatFL,
  formatSpeed,
  generateSquawk,
  getStripColumn,
  getStripPhase,
  loadStripStates,
  renderFlightStrips,
} from './efs';
import {
  escapeHtml,
  renderTafModule,
  renderWeatherModule,
  setConnectionStatus,
  startUTCClock,
  updateRefreshTimestamp,
} from './weather';
import { initWindInstruments, setRunwayGroups, updateWindInstruments, type RunwayGroup } from './wind';

const STRIP_REFRESH_MS = 15000;
const WEATHER_REFRESH_MS = 60000;
const AIRPORT_REFRESH_MS = 30000;
const POSITIONS_REFRESH_MS = 1000; // live aircraft positions

export let flightPlans: FlightPlan[] = [];
let livePositions: Record<string, AircraftPosition> = {};

// ---- Initialization ----

document.addEventListener('DOMContentLoaded', () => {
  startUTCClock();
  initWindInstruments();
  initLightingControls();
  initSMRMap();

  loadAirport();
  loadStripStates(() => {
    loadFlightStrips();
  });
  loadWeather();
  loadTaf();

  // Auto-refresh
  setInterval(loadAirport, AIRPORT_REFRESH_MS);
  setInterval(() => {
    loadStripStates(() => loadFlightStrips());
  }, STRIP_REFRESH_MS);
  setInterval(loadWeather, WEATHER_REFRESH_MS);
  setInterval(loadTaf, WEATHER_REFRESH_MS);

  // Live aircraft positions for the SMR map — faster cadence so dots track movement
  loadAircraftPositions();
  setInterval(loadAircraftPositions, POSITIONS_REFRESH_MS);
});

function loadAircraftPositions(): void {
  getAircraftPositions()
    .then((arr) => {
      const next: Record<string, AircraftPosition> = {};
      (arr || []).forEach((a) => {
        if (a && a.registration) next[a.registration] = a;
      });
      livePositions = next;
      updateSMRAircraft(flightPlans);
    })
    .catch(() => {
      /* ignore transient failures */
    });
}

// ---- Data Loading ----

function loadFlightStrips(): void {
  getStrips()
    .then((data) => {
      flightPlans = data;
      rerenderStrips();
      updateRefreshTimestamp();
      setConnectionStatus(true);
    })
    .catch((err: unknown) => {
      console.error('Failed to load strips:', err);
      setConnectionStatus(false);
    });
}

export function rerenderStrips(): void {
  renderFlightStrips(flightPlans);
  updateSMRAircraft(flightPlans);
  updateRunwaySequence(flightPlans);
  checkRIMCAS();
}

function loadWeather(): void {
  getWeather()
    .then((data) => {
      renderWeatherModule(data);
      updateWindInstruments(data);
    })
    .catch((err: unknown) => {
      console.error('Failed to load weather:', err);
    });
}

export let currentICAO = '';

function loadAirport(): void {
  getAirport()
    .then((data) => {
      const icao = data.icao || '----';
      const badge = document.getElementById('airport-badge');
      if (badge) badge.textContent = icao;
      const smrLabel = document.getElementById('smr-airport');
      if (smrLabel) smrLabel.textContent = icao;

      // Reload map, weather & TAF when airport changes
      if (icao !== currentICAO && icao !== '----') {
        currentICAO = icao;
        activeILSRunway = null;
        initSMRMap();
        loadWeather();
        loadTaf();
      }
    })
    .catch((err: unknown) => {
      console.error('Failed to load airport:', err);
    });
}

function loadTaf(): void {
  getTaf()
    .then((data) => {
      // Handle various response structures from the weather service
      let rawTaf: string | null = null;
      if (typeof data === 'string') {
        rawTaf = data;
      } else if (data.raw_taf) {
        rawTaf = data.raw_taf;
      } else if (data.raw) {
        rawTaf = data.raw;
      } else if (data.taf) {
        rawTaf = data.taf;
      }
      renderTafModule(rawTaf);
    })
    .catch((err: unknown) => {
      console.error('Failed to load TAF:', err);
      renderTafModule('TAF unavailable');
    });
}

// ============================================
// SMR Map (Surface Movement Radar) - Real Data
// ============================================

let smrGraph: AirportGraph | null = null; // Airport graph data from API
let smrBounds: SmrBounds | null = null;

// Pan & Zoom state
let smrViewBox = { x: 0, y: 0, w: 100, h: 100 };
let smrDrag: { startX: number; startY: number; startVBx: number; startVBy: number } | null = null;

// ILS extended centerline overlay
const ILS_RANGE_NM = 10;
const ILS_TICK_NM = 1;
const ILS_TICK_HALF_NM = 0.15;
let activeILSRunway: string | null = null;
// Dynamic max viewBox bounds — expanded when ILS centerline goes outside [0,100]
let smrViewMaxBounds = { minX: 0, minY: 0, maxX: 100, maxY: 100 };

function _smrSvg(): SVGSVGElement | null {
  return document.querySelector<SVGSVGElement>('#smr-svg');
}

function initSMRMap(): void {
  const container = document.getElementById('smr-map');
  if (!container) return;

  container.innerHTML =
    '<svg viewBox="0 0 100 100"><text x="50" y="50" text-anchor="middle" fill="#5a6672" font-size="3.5" font-family="monospace">Loading airport data...</text></svg>';

  getAirportGraph()
    .then((data) => {
      smrGraph = data;
      computeSMRBounds();
      renderSMRFromData();
      updateRunwaySelector();
    })
    .catch((err: unknown) => {
      console.error('Failed to load airport graph:', err);
      container.innerHTML =
        '<svg viewBox="0 0 100 100"><text x="50" y="50" text-anchor="middle" fill="#ff1744" font-size="3" font-family="monospace">No airport data</text></svg>';
    });
}

function computeSMRBounds(): void {
  smrBounds = smrGraph ? computeSmrBounds(smrGraph) : null;
}

// Convert GPS lat/lon to SVG x/y using the current bounds
function toSVG(lat: number, lon: number): Point {
  return geoToSVG(smrBounds, lat, lon);
}

function renderSMRFromData(): void {
  const container = document.getElementById('smr-map');
  if (!container || !smrGraph || !smrBounds) return;

  smrViewBox = { x: 0, y: 0, w: 100, h: 100 };

  let svg = '<svg id="smr-svg" viewBox="0 0 100 100" preserveAspectRatio="xMidYMid meet" style="cursor:grab">';

  // Background grid
  for (let gx = 0; gx <= 100; gx += 10) {
    svg += '<line x1="' + gx + '" y1="0" x2="' + gx + '" y2="100" stroke="#0d1520" stroke-width="0.15" vector-effect="non-scaling-stroke"/>';
  }
  for (let gy = 0; gy <= 100; gy += 10) {
    svg += '<line x1="0" y1="' + gy + '" x2="100" y2="' + gy + '" stroke="#0d1520" stroke-width="0.15" vector-effect="non-scaling-stroke"/>';
  }

  // --- Runways ---
  smrGraph.runways.forEach((rwy) => {
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

  smrGraph.edges.forEach((edge) => {
    const n1 = smrGraph!.nodes[edge.from];
    const n2 = smrGraph!.nodes[edge.to];
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
  Object.keys(smrGraph.nodes).forEach((id) => {
    const n = smrGraph!.nodes[id]!;
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
  smrGraph.stands.forEach((stand) => {
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
  Object.keys(smrGraph.nodes).forEach((id) => {
    const n = smrGraph!.nodes[id]!;
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
    activeILSRunway = null;
  } else {
    const token = String(rawDesignator).trim().toUpperCase().split(/[\s/]+/)[0];
    activeILSRunway = token || null;
  }
  drawILSCenterline();
  autoFitSMRView();
}

function _findRunwayEnds(designator: string): { threshold: RunwayEnd; otherEnd: RunwayEnd } | null {
  if (!smrGraph) return null;
  for (const r of smrGraph.runways) {
    if (r.end1.designator === designator) return { threshold: r.end1, otherEnd: r.end2 };
    if (r.end2.designator === designator) return { threshold: r.end2, otherEnd: r.end1 };
  }
  return null;
}

function autoFitSMRView(): void {
  let minX = 0,
    minY = 0,
    maxX = 100,
    maxY = 100;

  if (activeILSRunway && smrGraph && smrBounds) {
    const ends = _findRunwayEnds(activeILSRunway);
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

  smrViewMaxBounds = { minX, minY, maxX, maxY };

  const w = maxX - minX;
  const h = maxY - minY;
  const size = Math.max(w, h);
  const cx = (minX + maxX) / 2;
  const cy = (minY + maxY) / 2;
  smrViewBox = { x: cx - size / 2, y: cy - size / 2, w: size, h: size };

  const svgEl = _smrSvg();
  if (svgEl) {
    svgEl.setAttribute(
      'viewBox',
      smrViewBox.x + ' ' + smrViewBox.y + ' ' + smrViewBox.w + ' ' + smrViewBox.h,
    );
    rescaleSMRElements();
  }
}

function drawILSCenterline(): void {
  const group = document.getElementById('smr-ils-group');
  if (!group) return;
  group.innerHTML = '';
  if (!activeILSRunway || !smrGraph || !smrBounds) return;

  const ends = _findRunwayEnds(activeILSRunway);
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

function _attrNum(el: Element, name: string): number {
  return parseFloat(el.getAttribute(name) ?? '0');
}

function rescaleSMRElements(): void {
  const svgEl = _smrSvg();
  if (!svgEl) return;

  const s = smrViewBox.w / 100; // zoom scale: 1 = no zoom, 0.1 = zoomed 10x
  // Label SIZE scale: full visual size at ≥3x zoom (s≤0.35), shrinks when zoomed out.
  // Position offsets (distance from dot) still use s → fixed visual gap at all zooms.
  const sL = Math.min(s, 0.35);

  // Rescale all text with data-base-fs
  svgEl.querySelectorAll('text[data-base-fs]').forEach((t) => {
    t.setAttribute('font-size', String(_attrNum(t, 'data-base-fs') * s));
  });

  // Rescale and reposition stand labels
  const showLabels = s < 0.28;
  svgEl.querySelectorAll<SVGTextElement>('.smr-stand-label').forEach((lbl) => {
    const lcy = _attrNum(lbl, 'data-cy');
    const baseDy = _attrNum(lbl, 'data-base-dy');
    const baseSw = _attrNum(lbl, 'data-base-sw');
    // Keep label just below the stand square at any zoom level
    lbl.setAttribute('y', String(lcy + baseDy * s + 0.6 * s));
    lbl.setAttribute('stroke-width', String(baseSw * s));
    lbl.style.display = showLabels ? '' : 'none';
  });

  // Rescale stand rects (commercial)
  svgEl.querySelectorAll('rect.smr-stand').forEach((rect) => {
    const cx = _attrNum(rect, 'data-cx');
    const cy = _attrNum(rect, 'data-cy');
    const sz = _attrNum(rect, 'data-base-size') * s;
    rect.setAttribute('x', String(cx - sz / 2));
    rect.setAttribute('y', String(cy - sz / 2));
    rect.setAttribute('width', String(sz));
    rect.setAttribute('height', String(sz));
    rect.setAttribute('rx', String(0.3 * s));
  });

  // Rescale node circles
  svgEl.querySelectorAll('circle[data-base-r]').forEach((c) => {
    c.setAttribute('r', String(_attrNum(c, 'data-base-r') * s));
  });

  // Aurora label background rects
  // Position (x,y) uses s → fixed visual gap from dot at all zooms.
  // Size (w,h,rx,sw) uses sL → shrinks when zoomed out, full size at ≥3x zoom.
  svgEl.querySelectorAll('.smr-label-bg').forEach((lbEl) => {
    const dotX = _attrNum(lbEl, 'data-dot-x');
    const dotY = _attrNum(lbEl, 'data-dot-y');
    lbEl.setAttribute('x', String(dotX + _attrNum(lbEl, 'data-base-ox') * sL));
    lbEl.setAttribute('y', String(dotY + _attrNum(lbEl, 'data-base-oy') * sL));
    lbEl.setAttribute('width', String(_attrNum(lbEl, 'data-base-w') * sL));
    lbEl.setAttribute('height', String(_attrNum(lbEl, 'data-base-h') * sL));
    lbEl.setAttribute('rx', String(_attrNum(lbEl, 'data-base-rx') * sL));
    lbEl.setAttribute('stroke-width', String(_attrNum(lbEl, 'data-base-sw') * sL));
  });

  // Aurora label leader lines — attach to nearest box edge
  svgEl.querySelectorAll('.smr-label-line').forEach((llEl) => {
    const dotX = _attrNum(llEl, 'data-dot-x');
    const dotY = _attrNum(llEl, 'data-dot-y');
    llEl.setAttribute('x1', String(dotX));
    llEl.setAttribute('y1', String(dotY));
    llEl.setAttribute('stroke-width', String(_attrNum(llEl, 'data-base-sw') * sL));

    // Look up matching bg rect to get current box geometry
    const reg = llEl.getAttribute('data-reg');
    const bg = reg ? _smrLabelElByReg(svgEl, 'smr-label-bg', reg) : null;
    if (bg) {
      const boxX = dotX + _attrNum(bg, 'data-base-ox') * sL;
      const boxY = dotY + _attrNum(bg, 'data-base-oy') * sL;
      const att = leaderAttachPoint(
        dotX,
        dotY,
        boxX,
        boxY,
        _attrNum(bg, 'data-base-w') * sL,
        _attrNum(bg, 'data-base-h') * sL,
      );
      llEl.setAttribute('x2', String(att.x));
      llEl.setAttribute('y2', String(att.y));
    }
  });

  // Aurora label text blocks (position uses s, line-spacing uses sL)
  svgEl.querySelectorAll('.smr-label-text').forEach((ltEl) => {
    const dotX = _attrNum(ltEl, 'data-dot-x');
    const dotY = _attrNum(ltEl, 'data-dot-y');
    const baseDy = _attrNum(ltEl, 'data-base-dy');
    const newX = dotX + _attrNum(ltEl, 'data-base-ox') * sL;
    const newY = dotY + _attrNum(ltEl, 'data-base-oy') * sL;
    ltEl.setAttribute('x', String(newX));
    ltEl.setAttribute('y', String(newY));
    ltEl.querySelectorAll('tspan').forEach((tspan, idx) => {
      tspan.setAttribute('x', String(newX));
      if (idx > 0) tspan.setAttribute('dy', String(baseDy * sL));
    });
  });

  // Aurora label font size (separate from generic text loop, uses sL)
  svgEl.querySelectorAll('text[data-lbl-fs]').forEach((el) => {
    el.setAttribute('font-size', String(_attrNum(el, 'data-lbl-fs') * sL));
  });
}

// --- Pan & Zoom interaction ---

function initSMRInteraction(): void {
  const svgEl = _smrSvg();
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

      // Point in viewBox under mouse
      const px = smrViewBox.x + mx * smrViewBox.w;
      const py = smrViewBox.y + my * smrViewBox.h;

      // New size
      let nw = smrViewBox.w * zoomFactor;
      let nh = smrViewBox.h * zoomFactor;

      // Clamp: don't zoom out beyond the dynamic max bounds (expanded if ILS active)
      const maxW = smrViewMaxBounds.maxX - smrViewMaxBounds.minX;
      const maxH = smrViewMaxBounds.maxY - smrViewMaxBounds.minY;
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
      smrViewBox.x = px - mx * nw;
      smrViewBox.y = py - my * nh;
      smrViewBox.w = nw;
      smrViewBox.h = nh;

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
      startVBx: smrViewBox.x,
      startVBy: smrViewBox.y,
    };
    svgEl.style.cursor = 'grabbing';
    e.preventDefault();
  });

  window.addEventListener('mousemove', (e: MouseEvent) => {
    if (!smrDrag) return;
    const sv = _smrSvg();
    if (!sv) return;

    const rect = sv.getBoundingClientRect();
    // Convert pixel delta to viewBox units
    const dx = ((e.clientX - smrDrag.startX) / rect.width) * smrViewBox.w;
    const dy = ((e.clientY - smrDrag.startY) / rect.height) * smrViewBox.h;

    smrViewBox.x = smrDrag.startVBx - dx;
    smrViewBox.y = smrDrag.startVBy - dy;

    clampViewBox();
    applySMRViewBox();
  });

  window.addEventListener('mouseup', () => {
    if (smrDrag) {
      smrDrag = null;
      const sv = _smrSvg();
      if (sv) sv.style.cursor = 'grab';
    }
  });

  // Double-click to reset view (auto-fit current bounds, ILS included if active)
  svgEl.addEventListener('dblclick', (e: MouseEvent) => {
    e.preventDefault();
    autoFitSMRView();
  });
}

function clampViewBox(): void {
  if (smrViewBox.x < smrViewMaxBounds.minX) smrViewBox.x = smrViewMaxBounds.minX;
  if (smrViewBox.y < smrViewMaxBounds.minY) smrViewBox.y = smrViewMaxBounds.minY;
  if (smrViewBox.x + smrViewBox.w > smrViewMaxBounds.maxX)
    smrViewBox.x = smrViewMaxBounds.maxX - smrViewBox.w;
  if (smrViewBox.y + smrViewBox.h > smrViewMaxBounds.maxY)
    smrViewBox.y = smrViewMaxBounds.maxY - smrViewBox.h;
}

function applySMRViewBox(): void {
  const svgEl = _smrSvg();
  if (!svgEl) return;
  svgEl.setAttribute(
    'viewBox',
    smrViewBox.x + ' ' + smrViewBox.y + ' ' + smrViewBox.w + ' ' + smrViewBox.h,
  );
  rescaleSMRElements();
}

// --- Aurora-style HMI ground label for SMR ---

const smrLabelOffsets: Record<string, { ox: number; oy: number }> = {}; // persisted user-drag offsets
let _smrLabelDragState: {
  reg: string;
  startX: number;
  startY: number;
  startBgOx: number;
  startBgOy: number;
} | null = null;
let _smrLabelDragInited = false;

// Margins between box origin and text origin (in base SVG units, constant)
const SMR_LBL_TXT_MARGIN_X = 0.4;
const SMR_LBL_TXT_MARGIN_Y = 1.3;

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
  const BOX_OX = 1.8 + userOx;
  const BOX_OY = -5.0 + userOy;
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

// --- Middle-button drag to reposition SMR labels ---

function _smrLabelElByReg(svgEl: SVGSVGElement, cls: string, reg: string): Element | null {
  const els = svgEl.querySelectorAll('.' + cls);
  for (const el of els) {
    if (el.getAttribute('data-reg') === reg) return el;
  }
  return null;
}

function initSMRLabelDrag(): void {
  const svgEl = _smrSvg();
  if (!svgEl) return;

  // Attach middle-mousedown on freshly rendered bg and text elements
  svgEl.querySelectorAll('.smr-label-bg, .smr-label-text').forEach((el) => {
    el.addEventListener('mousedown', (e: Event) => {
      const me = e as MouseEvent;
      if (me.button !== 1) return;
      me.preventDefault();
      const reg = el.getAttribute('data-reg');
      if (!reg) return;
      const bg = _smrLabelElByReg(svgEl, 'smr-label-bg', reg);
      if (!bg) return;
      _smrLabelDragState = {
        reg,
        startX: me.clientX,
        startY: me.clientY,
        startBgOx: _attrNum(bg, 'data-base-ox'),
        startBgOy: _attrNum(bg, 'data-base-oy'),
      };
      svgEl.style.cursor = 'move';
    });
  });

  // Window-level handlers registered only once for the lifetime of the page
  if (_smrLabelDragInited) return;
  _smrLabelDragInited = true;

  window.addEventListener('mousemove', (e: MouseEvent) => {
    if (!_smrLabelDragState) return;
    const sv = _smrSvg();
    if (!sv) return;

    const rect = sv.getBoundingClientRect();
    // Delta in base SVG units (scale-independent: 100 / rendered px)
    const dOx = ((e.clientX - _smrLabelDragState.startX) * 100) / rect.width;
    const dOy = ((e.clientY - _smrLabelDragState.startY) * 100) / rect.height;

    const reg = _smrLabelDragState.reg;
    const newBgOx = _smrLabelDragState.startBgOx + dOx;
    const newBgOy = _smrLabelDragState.startBgOy + dOy;

    const bg = _smrLabelElByReg(sv, 'smr-label-bg', reg);
    const txt = _smrLabelElByReg(sv, 'smr-label-text', reg);

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
    const sv = _smrSvg();
    const bg = sv ? _smrLabelElByReg(sv, 'smr-label-bg', reg) : null;
    if (bg) {
      const finalOx = _attrNum(bg, 'data-base-ox');
      const finalOy = _attrNum(bg, 'data-base-oy');
      // Store offset relative to the hardcoded defaults (BOX_OX=1.8, BOX_OY=-5.0)
      const offset = { ox: finalOx - 1.8, oy: finalOy - -5.0 };
      smrLabelOffsets[reg] = offset;
      setSmrLabelOffset(reg, offset);
    }
    _smrLabelDragState = null;
    if (sv) sv.style.cursor = 'grab';
  });
}

// --- Place aircraft on SMR based on strip phase ---

export function updateSMRAircraft(plans: FlightPlan[]): void {
  const group = document.getElementById('smr-aircraft-group');
  if (!group || !smrGraph || !smrBounds) return;

  group.innerHTML = '';
  if (!plans || plans.length === 0) return;

  // Build zone positions from real data
  const standPositions: Point[] = [];
  const taxiPositions: Point[] = [];
  const runwayPositions: Point[] = [];

  smrGraph.stands.forEach((s) => {
    standPositions.push(toSVG(s.lat, s.lon));
  });

  // Collect unique taxiway node positions
  const seenTaxiNodes: Record<string, boolean> = {};
  smrGraph.edges.forEach((edge) => {
    if (edge.category !== 'runway') {
      if (!seenTaxiNodes[edge.from]) {
        const n = smrGraph!.nodes[edge.from];
        if (n) {
          taxiPositions.push(toSVG(n.lat, n.lon));
          seenTaxiNodes[edge.from] = true;
        }
      }
    }
  });

  // Interpolated positions along runway
  smrGraph.runways.forEach((rwy) => {
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

// ---- RIMCAS (Runway Incursion Alert) ----

function checkRIMCAS(): void {
  let hasIncursion = false;

  flightPlans.forEach((plan) => {
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

// ============================================
// Lighting Controls
// ============================================

function initLightingControls(): void {
  // PAPI slider
  const papiSlider = document.getElementById('papi-slider') as HTMLInputElement | null;
  const papiValue = document.getElementById('papi-value');
  if (papiSlider && papiValue) {
    papiSlider.addEventListener('input', () => {
      papiValue.textContent = papiSlider.value;
    });
  }

  // Toggle buttons
  initToggleButton('stopbar-btn');
  initToggleButton('rwy-lights-btn');
  initToggleButton('approach-lights-btn');

  // LVP toggle
  const lvp = document.getElementById('lvp-indicator');
  if (lvp) {
    lvp.addEventListener('click', () => {
      lvp.classList.toggle('lvp-on');
      lvp.classList.toggle('lvp-off');
    });
  }
}

function initToggleButton(id: string): void {
  const btn = document.getElementById(id);
  if (!btn) return;

  btn.addEventListener('click', () => {
    const isOn = btn.classList.contains('stopbar-on');
    if (isOn) {
      btn.classList.remove('stopbar-on');
      btn.classList.add('stopbar-off');
      btn.textContent = 'OFF';
    } else {
      btn.classList.remove('stopbar-off');
      btn.classList.add('stopbar-on');
      btn.textContent = 'ON';
    }
  });
}

// ============================================
// Dynamic Runway Selector
// ============================================

function updateRunwaySelector(): void {
  if (!smrGraph || !smrGraph.runways) return;

  // Collect all runway designators from the graph data
  const designators: { label: string; hdg: number }[] = [];
  smrGraph.runways.forEach((rwy) => {
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

  // Sort groups by heading
  const groups = Object.values(groupMap).sort((a, b) => a.hdg - b.hdg);

  // Pass to wind module for paired rendering
  setRunwayGroups(groups);
}

// ============================================
// Runway Sequence Monitor
// ============================================

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

function getWTC(acType: string | undefined): string {
  if (!acType) return 'M';
  const code = acType.toUpperCase().replace(/-/g, '');
  const known = WTC_MAP[code];
  if (known) return known;
  // Guess from prefix
  if (code.indexOf('A3') === 0 && parseInt(code.charAt(2)) >= 3) return 'H';
  if (code.indexOf('B7') === 0 && parseInt(code.charAt(2)) >= 4) return 'H';
  return 'M';
}

interface SequenceEntry {
  callsign: string;
  type: string;
  wtc: string;
  phase: string;
  column: StripColumn;
}

function updateRunwaySequence(plans: FlightPlan[]): void {
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
