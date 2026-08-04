// Pure TAF parsing (no DOM).

export interface TafGroup {
  wind: string | null;
  vis: string | null;
  clouds: string | null;
  wx: string | null;
  type?: string;
}

export interface ParsedTaf {
  validity: string | null;
  base: TafGroup | null;
  tempMax: string | null;
  tempMin: string | null;
  changes: TafGroup[];
}

/** Trim leading METAR noise: keep everything from the first "TAF " token. */
export function extractTafPortion(rawTaf: string): string {
  const tafMatch = rawTaf.match(/(^|\n)(TAF\s)/);
  if (tafMatch && tafMatch.index !== undefined) {
    return rawTaf.substring(tafMatch.index + (tafMatch[1] ? tafMatch[1].length : 0));
  }
  const idx = rawTaf.indexOf('TAF ');
  if (idx !== -1) return rawTaf.substring(idx);
  return rawTaf;
}

export function parseTaf(raw: string | null): ParsedTaf {
  const result: ParsedTaf = {
    validity: null,
    base: null,
    tempMax: null,
    tempMin: null,
    changes: [],
  };
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

export function parseWeatherTokens(text: string): TafGroup {
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
