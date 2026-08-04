// weather.ts — METAR & TAF rendering + Dashboard Superior.

import type { Metar } from '../types/api';

// ---- METAR ----

const AD_ELEVATION_M = 369; // LEST aerodrome elevation

export function renderWeatherModule(metar: Metar): void {
  const rawEl = document.getElementById('wx-raw-metar');
  if (rawEl) rawEl.textContent = metar.raw_metar || '--';

  // Flight category badge
  const catBadge = document.getElementById('wx-flight-cat');
  if (catBadge) {
    const cat = metar.flight_category || '--';
    catBadge.textContent = cat;
    catBadge.className = 'flight-cat-badge';
    const catMap: Record<string, string> = {
      VFR: 'cat-vfr',
      MVFR: 'cat-mvfr',
      IFR: 'cat-ifr',
      LIFR: 'cat-lifr',
    };
    const cls = catMap[cat];
    if (cls) catBadge.classList.add(cls);
  }

  // QNH / QFE with alerts
  renderAltimetry(metar);

  // Icon-based decoded METAR
  renderMetarIcons(metar);
}

// ---- QNH / QFE with color alerts ----

function renderAltimetry(metar: Metar): void {
  const qnh = metar.qnh_hpa;
  const qnhEl = document.getElementById('qnh-value');
  const qfeEl = document.getElementById('qfe-value');
  if (!qnhEl || !qfeEl) return;

  if (!qnh) {
    qnhEl.textContent = '----';
    qfeEl.textContent = '----';
    qnhEl.classList.remove('alert-low');
    qfeEl.classList.remove('alert-low');
    return;
  }

  qnhEl.textContent = String(qnh);

  // QFE calculation (ICAO standard atmosphere)
  const T0 = 288.15;
  const L = 0.0065;
  const exponent = 5.2561;
  const qfe = qnh * Math.pow((T0 - L * AD_ELEVATION_M) / T0, exponent);
  qfeEl.textContent = String(Math.round(qfe));

  // Alert: QNH < 1000 hPa = low pressure / storm
  if (qnh < 1000) {
    qnhEl.classList.add('alert-low');
    qfeEl.classList.add('alert-low');
  } else {
    qnhEl.classList.remove('alert-low');
    qfeEl.classList.remove('alert-low');
  }
}

// ---- METAR Icon Display ----

function renderMetarIcons(metar: Metar): void {
  // Clouds icon
  const cloudsEl = document.getElementById('metar-clouds-text');
  if (cloudsEl) {
    if (metar.clouds && metar.clouds.length > 0) {
      cloudsEl.textContent = metar.clouds.map((c) => c.coverage + ' ' + c.base_ft + 'ft').join(' | ');
    } else {
      cloudsEl.textContent = 'CAVOK';
    }
  }

  // Visibility icon + bar
  const visEl = document.getElementById('metar-vis-text');
  const visBar = document.getElementById('metar-vis-bar');
  if (visEl && metar.visibility_m !== undefined) {
    const rawHas9999 = !!metar.raw_metar && /\b9999\b/.test(metar.raw_metar);
    const visKm = metar.visibility_m / 1000;
    visEl.textContent = rawHas9999 ? '+10 km' : visKm.toFixed(1) + ' km';

    if (visBar) {
      const pct = Math.min(100, (visKm / 10) * 100);
      visBar.style.width = pct + '%';
      // Color: green > 5km, orange 1-5km, red < 1km
      if (visKm >= 5) {
        visBar.style.backgroundColor = 'var(--hmi-green)';
      } else if (visKm >= 1) {
        visBar.style.backgroundColor = 'var(--hmi-orange)';
      } else {
        visBar.style.backgroundColor = 'var(--hmi-red)';
      }
    }
  }

  // Wind icon
  const windEl = document.getElementById('metar-wind-text');
  if (windEl) {
    const windDir =
      metar.wind_direction === 0 ? 'VRB' : String(metar.wind_direction).padStart(3, '0') + '°';
    const gustText = metar.wind_gust ? ' G' + metar.wind_gust : '';
    windEl.textContent = windDir + '/' + metar.wind_speed + 'kt' + gustText;
  }

  // Weather phenomena
  const wxEl = document.getElementById('metar-wx-text');
  if (wxEl) {
    wxEl.textContent = metar.weather || 'NIL';
  }

  // Temperature
  const tempEl = document.getElementById('metar-temp-text');
  if (tempEl) {
    tempEl.textContent = metar.temperature_c + '/' + metar.dewpoint_c + '°C';
  }
}

// ---- TAF ----

interface TafGroup {
  wind: string | null;
  vis: string | null;
  clouds: string | null;
  wx: string | null;
  type?: string;
}

interface ParsedTaf {
  validity: string | null;
  base: TafGroup | null;
  tempMax: string | null;
  tempMin: string | null;
  changes: TafGroup[];
}

export function renderTafModule(rawTaf: string | null): void {
  const rawEl = document.getElementById('wx-raw-taf');
  const decodedEl = document.getElementById('wx-decoded-taf');
  const validityEl = document.getElementById('taf-validity');

  // Extract only the TAF portion (discard any METAR lines mixed in)
  if (rawTaf) {
    // Try to find "TAF" or "TAF AMD" at start of line or string
    const tafMatch = rawTaf.match(/(^|\n)(TAF\s)/);
    if (tafMatch && tafMatch.index !== undefined) {
      rawTaf = rawTaf.substring(tafMatch.index + (tafMatch[1] ? tafMatch[1].length : 0));
    } else {
      // Fallback: find any occurrence of "TAF "
      const idx = rawTaf.indexOf('TAF ');
      if (idx !== -1) {
        rawTaf = rawTaf.substring(idx);
      }
    }
  }

  if (rawEl) rawEl.textContent = rawTaf || 'No TAF available';
  if (!decodedEl || !rawTaf) return;

  const parsed = parseTaf(rawTaf);

  if (validityEl && parsed.validity) {
    validityEl.textContent = parsed.validity;
  }

  let html = '';

  if (parsed.base) {
    html += '<div class="taf-group">';
    html += '<span class="taf-group-label">BASE</span> ';
    html += tafLine(parsed.base);
    html += '</div>';
  }

  parsed.changes.forEach((chg) => {
    html += '<div class="taf-group">';
    html += '<span class="taf-group-label">' + escapeHtml(chg.type || '') + '</span> ';
    html += tafLine(chg);
    html += '</div>';
  });

  decodedEl.innerHTML = html || '<span style="color:var(--text-dim)">No data</span>';
}

function tafLine(grp: TafGroup): string {
  const parts: string[] = [];
  if (grp.wind) parts.push(grp.wind);
  if (grp.vis) parts.push(grp.vis);
  if (grp.clouds) parts.push(grp.clouds);
  if (grp.wx) parts.push(grp.wx);
  return '<span>' + parts.join(' | ') + '</span>';
}

// ---- TAF Parser ----

export function parseTaf(raw: string | null): ParsedTaf {
  const result: ParsedTaf = { validity: null, base: null, tempMax: null, tempMin: null, changes: [] };
  if (!raw) return result;

  const text = raw.replace(/\n/g, ' ').replace(/\s+/g, ' ').trim();

  const valMatch = text.match(/\b(\d{4}\/\d{4})\b/);
  if (valMatch && valMatch[1]) {
    const v = valMatch[1];
    result.validity =
      v.slice(0, 2) + 'd ' + v.slice(2, 4) + 'Z → ' + v.slice(5, 7) + 'd ' + v.slice(7, 9) + 'Z';
  }

  const txMatch = text.match(/TX(\d{2})\/(\d{4}Z)/);
  if (txMatch) result.tempMax = txMatch[1] + '°C @ ' + txMatch[2];

  const tnMatch = text.match(/TN(\d{2})\/(\d{4}Z)/);
  if (tnMatch) result.tempMin = tnMatch[1] + '°C @ ' + tnMatch[2];

  const parts = text.split(/\s+(TEMPO|BECMG|FM\d{6}|PROB\d{2}\s+TEMPO|PROB\d{2})\s+/);

  if (parts[0]) {
    result.base = parseWeatherTokens(parts[0]);
  }

  for (let i = 1; i < parts.length; i += 2) {
    const type = parts[i];
    const content = parts[i + 1] || '';
    const chg = parseWeatherTokens(content);
    chg.type = type;
    if (chg.wind || chg.vis || chg.clouds || chg.wx) {
      result.changes.push(chg);
    }
  }

  return result;
}

function parseWeatherTokens(text: string): TafGroup {
  const r: TafGroup = { wind: null, vis: null, clouds: null, wx: null };

  const wm = text.match(/(VRB|\d{3})(\d{2,3})(G(\d{2,3}))?KT/);
  if (wm) {
    const dir = wm[1] === 'VRB' ? 'VRB' : wm[1] + '°';
    const gust = wm[4] ? ' G' + wm[4] : '';
    r.wind = dir + '/' + wm[2] + 'kt' + gust;
  }

  if (text.indexOf('CAVOK') !== -1) {
    r.vis = 'CAVOK';
  } else {
    const vm = text.match(/\b(\d{4})\b/);
    if (vm && vm[1] && parseInt(vm[1]) <= 9999) {
      const m = parseInt(vm[1]);
      r.vis = m >= 9999 ? '>10 km' : (m / 1000).toFixed(1) + ' km';
    }
  }

  const cloudMatches = text.match(/(FEW|SCT|BKN|OVC)(\d{3})/g);
  if (cloudMatches) {
    r.clouds = cloudMatches
      .map((c) => {
        const cov = c.slice(0, 3);
        const alt = parseInt(c.slice(3)) * 100;
        return cov + ' ' + alt + 'ft';
      })
      .join(' ');
  }

  const wxPatterns = text.match(/[-+]?(RA|SN|DZ|FG|BR|HZ|TS|SH|GR|SQ|FC|SS|DS|FZ|MI|PR|BC|BL|DR|VC)+/g);
  if (wxPatterns) {
    r.wx = wxPatterns.join(' ');
  }

  return r;
}

// ---- Helpers ----

export function startUTCClock(): void {
  const clockEl = document.getElementById('utc-clock');
  if (!clockEl) return;

  function update(): void {
    const now = new Date();
    clockEl!.textContent =
      String(now.getUTCHours()).padStart(2, '0') +
      ':' +
      String(now.getUTCMinutes()).padStart(2, '0') +
      ':' +
      String(now.getUTCSeconds()).padStart(2, '0') +
      'Z';
  }
  update();
  setInterval(update, 1000);
}

export function updateRefreshTimestamp(): void {
  const el = document.getElementById('last-refresh');
  if (!el) return;
  const now = new Date();
  el.textContent =
    'Last refresh: ' +
    String(now.getUTCHours()).padStart(2, '0') +
    ':' +
    String(now.getUTCMinutes()).padStart(2, '0') +
    ':' +
    String(now.getUTCSeconds()).padStart(2, '0') +
    'Z';
}

export function setConnectionStatus(connected: boolean): void {
  const el = document.getElementById('connection-status');
  if (!el) return;
  el.textContent = connected ? 'CONNECTED' : 'DISCONNECTED';
  el.className = 'status-indicator ' + (connected ? 'connected' : 'disconnected');
}

export function escapeHtml(text: unknown): string {
  const div = document.createElement('div');
  div.textContent = String(text ?? '');
  return div.innerHTML;
}
