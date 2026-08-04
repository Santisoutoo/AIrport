// wind.ts — paired runway wind widget with safety alerts.

import type { Metar } from '../types/api';
import { checkWindLimits, computeWindComponents } from '../wind/calc';

export interface RunwayGroup {
  hdg: number;
  labels: string[];
}

interface WindState {
  direction: number;
  speed: number;
  gust: number;
  maxSpeed: number;
  minSpeed: number;
  runwayGroups: RunwayGroup[];
  XW_LIMIT: number;
  TW_LIMIT: number;
  HW_LIMIT: number;
  hasData: boolean;
}

const windState: WindState = {
  direction: 0,
  speed: 0,
  gust: 0,
  maxSpeed: 0,
  minSpeed: 0,
  runwayGroups: [],
  XW_LIMIT: 20,
  TW_LIMIT: 5,
  HW_LIMIT: 40,
  hasData: false,
};

// ---- Initialization ----

export function initWindInstruments(): void {
  renderAllWindGroups();
}

export function setRunwayGroups(groups: RunwayGroup[]): void {
  windState.runwayGroups = groups;
  renderAllWindGroups();
}

function renderAllWindGroups(): void {
  const container = document.getElementById('wind-pairs-container');
  if (!container) return;

  container.innerHTML = '';

  if (windState.runwayGroups.length === 0) return;

  windState.runwayGroups.forEach((group) => {
    const card = createWindPairCard(group);
    container.appendChild(card);
    renderWindDial(card.querySelector('.wind-dial'), group.hdg);
  });

  updateWindDisplay();
}

function createWindPairCard(group: RunwayGroup): HTMLDivElement {
  const card = document.createElement('div');
  card.className = 'wind-pair-card';
  card.dataset.rwyHdg = String(group.hdg);

  const header = document.createElement('div');
  header.className = 'wind-pair-header';
  header.textContent = group.labels.join(' / ');
  card.appendChild(header);

  const body = document.createElement('div');
  body.className = 'wind-pair-body';

  const dialContainer = document.createElement('div');
  dialContainer.className = 'wind-dial-container';
  const dial = document.createElement('div');
  dial.className = 'wind-dial';
  dialContainer.appendChild(dial);
  body.appendChild(dialContainer);

  const limits = document.createElement('div');
  limits.className = 'wind-limits-container';
  limits.appendChild(createLimitRow('XW', 'xw-' + group.hdg, false));
  limits.appendChild(createLimitRow('TW', 'tw-' + group.hdg, false));
  limits.appendChild(createLimitRow('HW', 'hw-' + group.hdg, true));
  body.appendChild(limits);

  card.appendChild(body);

  const alert = document.createElement('div');
  alert.className = 'rwy-change-alert hidden';
  alert.id = 'rwy-alert-' + group.hdg;
  card.appendChild(alert);

  return card;
}

function createLimitRow(label: string, idPrefix: string, isHw: boolean): HTMLDivElement {
  const row = document.createElement('div');
  row.className = 'wind-limit-row';

  const lbl = document.createElement('label');
  lbl.textContent = label;
  row.appendChild(lbl);

  const wrapper = document.createElement('div');
  wrapper.className = 'limit-bar-wrapper';

  const bar = document.createElement('div');
  bar.className = 'limit-bar' + (isHw ? ' limit-bar-hw' : '');
  bar.id = idPrefix + '-bar';
  const fill = document.createElement('div');
  fill.className = 'limit-bar-fill';
  bar.appendChild(fill);
  wrapper.appendChild(bar);

  const val = document.createElement('span');
  val.className = 'limit-value';
  val.id = idPrefix + '-value';
  val.textContent = '-- kt';
  wrapper.appendChild(val);

  row.appendChild(wrapper);
  return row;
}

// ---- SVG Wind Dial ----

function renderWindDial(container: Element | null, rwyHdg: number): void {
  if (!container) return;

  const size = 120;
  const cx = size / 2;
  const cy = size / 2;
  const r = 40;

  let svg = '<svg width="' + size + '" height="' + size + '" viewBox="0 0 ' + size + ' ' + size + '">';

  // Outer ring
  svg += '<circle cx="' + cx + '" cy="' + cy + '" r="' + r + '" fill="none" stroke="#334" stroke-width="2"/>';

  // Runway strip
  const rwyLen = 40;
  const rwyW = 5;
  const rwyRad = ((rwyHdg - 90) * Math.PI) / 180;
  const perpRad = rwyRad + Math.PI / 2;

  const dx = rwyLen * Math.cos(rwyRad);
  const dy = rwyLen * Math.sin(rwyRad);
  const px = rwyW * Math.cos(perpRad);
  const py = rwyW * Math.sin(perpRad);

  svg +=
    '<polygon points="' +
    (cx + dx + px) + ',' + (cy + dy + py) + ' ' +
    (cx + dx - px) + ',' + (cy + dy - py) + ' ' +
    (cx - dx - px) + ',' + (cy - dy - py) + ' ' +
    (cx - dx + px) + ',' + (cy - dy + py) +
    '" fill="rgba(0,229,255,0.2)" stroke="rgba(0,229,255,0.5)" stroke-width="1"/>';

  // Dashed centerline
  for (let d = 0; d < 4; d++) {
    const t = -rwyLen + ((d * rwyLen * 2) / 7) * 2;
    const dsx = cx + t * Math.cos(rwyRad);
    const dsy = cy + t * Math.sin(rwyRad);
    const dex = cx + (t + (rwyLen * 2) / 7) * Math.cos(rwyRad);
    const dey = cy + (t + (rwyLen * 2) / 7) * Math.sin(rwyRad);
    svg +=
      '<line x1="' + dsx + '" y1="' + dsy + '" x2="' + dex + '" y2="' + dey +
      '" stroke="rgba(255,255,255,0.3)" stroke-width="1"/>';
  }

  // Tick marks
  for (let deg = 0; deg < 360; deg += 10) {
    const rad = ((deg - 90) * Math.PI) / 180;
    const isMajor = deg % 30 === 0;
    const innerR = isMajor ? r - 8 : r - 4;

    const x1 = cx + innerR * Math.cos(rad);
    const y1 = cy + innerR * Math.sin(rad);
    const x2 = cx + r * Math.cos(rad);
    const y2 = cy + r * Math.sin(rad);

    svg +=
      '<line x1="' + x1 + '" y1="' + y1 + '" x2="' + x2 + '" y2="' + y2 +
      '" stroke="' + (isMajor ? '#889' : '#445') + '" stroke-width="' + (isMajor ? 1.5 : 0.8) + '"/>';
  }

  // Cardinal labels
  const cardinals = [
    { deg: 0, label: 'N' },
    { deg: 90, label: 'E' },
    { deg: 180, label: 'S' },
    { deg: 270, label: 'W' },
  ];
  cardinals.forEach((c) => {
    const cRad = ((c.deg - 90) * Math.PI) / 180;
    const lx = cx + (r + 8) * Math.cos(cRad);
    const ly = cy + (r + 8) * Math.sin(cRad);
    svg +=
      '<text x="' + lx + '" y="' + ly +
      '" text-anchor="middle" dominant-baseline="central" ' +
      'fill="#99a" font-size="9" font-weight="700" font-family="monospace">' +
      c.label +
      '</text>';
  });

  // Gust arc
  svg +=
    '<path class="wind-gust-arc" d="" fill="rgba(255,145,0,0.15)" stroke="rgba(255,145,0,0.5)" stroke-width="1"/>';

  // Wind direction arrow
  svg +=
    '<line class="wind-arrow" x1="' + cx + '" y1="' + cy + '" x2="' + cx + '" y2="' + (cy - r + 6) +
    '" stroke="#00e676" stroke-width="2.5" stroke-linecap="round"/>';
  svg += '<circle class="wind-arrow-tip" cx="' + cx + '" cy="' + (cy - r + 6) + '" r="3.5" fill="#00e676"/>';

  // Center speed display
  svg +=
    '<rect x="' + (cx - 18) + '" y="' + (cy - 9) +
    '" width="36" height="18" rx="3" fill="#0a0e14" stroke="#334" stroke-width="1"/>';
  svg +=
    '<text class="wind-speed-svg" x="' + cx + '" y="' + (cy + 2) +
    '" text-anchor="middle" dominant-baseline="central" ' +
    'fill="#00e676" font-size="14" font-weight="700" font-family="monospace">--</text>';

  svg += '</svg>';
  container.innerHTML = svg;
}

// ---- Update from METAR ----

export function updateWindInstruments(metar: Metar): void {
  if (!metar) return;

  windState.hasData = true;
  windState.direction = metar.wind_direction || 0;
  windState.speed = metar.wind_speed || 0;
  windState.gust = metar.wind_gust || 0;

  if (windState.speed > windState.maxSpeed) windState.maxSpeed = windState.speed;
  if (windState.minSpeed === 0 || windState.speed < windState.minSpeed)
    windState.minSpeed = windState.speed;

  updateWindDisplay();
}

function updateWindDisplay(): void {
  const container = document.getElementById('wind-pairs-container');
  if (!container) return;

  const cards = container.querySelectorAll<HTMLElement>('.wind-pair-card');
  cards.forEach((card) => {
    const rwyHdg = parseInt(card.dataset.rwyHdg ?? '0');
    updateCardWind(card, rwyHdg);
  });
}

function updateCardWind(card: HTMLElement, rwyHdg: number): void {
  const svgEl = card.querySelector('svg');
  if (!svgEl) return;

  const cx = 60,
    cy = 60,
    r = 40;

  const dir = windState.direction;
  const speed = windState.speed;
  const gust = windState.gust;

  // Update arrow position
  const arrow = svgEl.querySelector('.wind-arrow');
  const tip = svgEl.querySelector('.wind-arrow-tip');
  if (arrow && tip) {
    const rad = ((dir - 90) * Math.PI) / 180;
    const x2 = cx + (r - 6) * Math.cos(rad);
    const y2 = cy + (r - 6) * Math.sin(rad);
    const x1 = cx - 14 * Math.cos(rad);
    const y1 = cy - 14 * Math.sin(rad);

    arrow.setAttribute('x1', String(x1));
    arrow.setAttribute('y1', String(y1));
    arrow.setAttribute('x2', String(x2));
    arrow.setAttribute('y2', String(y2));
    tip.setAttribute('cx', String(x2));
    tip.setAttribute('cy', String(y2));

    let color = '#00e676';
    if (speed > 25) color = '#ff1744';
    else if (speed > 15) color = '#ff9100';
    arrow.setAttribute('stroke', color);
    tip.setAttribute('fill', color);
  }

  // Gust arc
  const gustArc = svgEl.querySelector('.wind-gust-arc');
  if (gustArc && gust > 0) {
    const spread = Math.min(30, (gust - speed) * 3);
    const startDeg = dir - spread;
    const endDeg = dir + spread;
    const arcR = r - 4;
    const startRad = ((startDeg - 90) * Math.PI) / 180;
    const endRad = ((endDeg - 90) * Math.PI) / 180;

    const sx = cx + arcR * Math.cos(startRad);
    const sy = cy + arcR * Math.sin(startRad);
    const ex = cx + arcR * Math.cos(endRad);
    const ey = cy + arcR * Math.sin(endRad);
    const largeArc = endDeg - startDeg > 180 ? 1 : 0;

    gustArc.setAttribute(
      'd',
      'M ' + cx + ' ' + cy +
        ' L ' + sx + ' ' + sy +
        ' A ' + arcR + ' ' + arcR + ' 0 ' + largeArc + ' 1 ' + ex + ' ' + ey +
        ' Z',
    );
  } else if (gustArc) {
    gustArc.setAttribute('d', '');
  }

  // Speed display
  const speedSvg = svgEl.querySelector('.wind-speed-svg');
  if (speedSvg) speedSvg.textContent = windState.hasData ? String(speed) : '--';

  // Wind components for this runway heading
  const { crosswind, tailwind, hwDisplay } = computeWindComponents(dir, speed, rwyHdg);

  // Update XW bar
  updateLimitBar('xw-' + rwyHdg, crosswind, windState.XW_LIMIT);
  const xwVal = document.getElementById('xw-' + rwyHdg + '-value');
  if (xwVal) xwVal.textContent = crosswind + ' kt';

  // Update TW bar
  updateLimitBar('tw-' + rwyHdg, tailwind, windState.TW_LIMIT);
  const twVal = document.getElementById('tw-' + rwyHdg + '-value');
  if (twVal) twVal.textContent = tailwind + ' kt';

  // Update HW bar
  updateLimitBar('hw-' + rwyHdg, hwDisplay, windState.HW_LIMIT);
  const hwVal = document.getElementById('hw-' + rwyHdg + '-value');
  if (hwVal) hwVal.textContent = hwDisplay + ' kt';

  const alertEl = document.getElementById('rwy-alert-' + rwyHdg);
  if (alertEl) {
    const limits = checkWindLimits(crosswind, tailwind, windState.XW_LIMIT, windState.TW_LIMIT);
    if (limits.exceeded) {
      alertEl.textContent = limits.message ?? '';
      alertEl.classList.remove('hidden');
    } else {
      alertEl.classList.add('hidden');
      alertEl.textContent = '';
    }
  }
}

function updateLimitBar(prefix: string, value: number, limit: number): void {
  const bar = document.getElementById(prefix + '-bar');
  if (!bar) return;
  const fill = bar.querySelector<HTMLElement>('.limit-bar-fill');
  if (!fill) return;

  const pct = Math.min(100, (value / (limit * 1.5)) * 100);
  fill.style.width = pct + '%';

  if (value > limit) {
    fill.style.backgroundColor = 'var(--hmi-red)';
  } else if (value > limit * 0.7) {
    fill.style.backgroundColor = 'var(--hmi-orange)';
  } else {
    fill.style.backgroundColor = 'var(--hmi-green)';
  }
}
