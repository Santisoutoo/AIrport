// weather.js -- METAR & TAF module rendering + utilities

// ---- METAR ----

function renderWeatherModule(metar) {
    var rawEl = document.getElementById('wx-raw-metar');
    if (rawEl) rawEl.textContent = metar.raw_metar || '--';

    // Flight category badge
    var catBadge = document.getElementById('wx-flight-cat');
    if (catBadge) {
        var cat = metar.flight_category || '--';
        catBadge.textContent = cat;
        catBadge.className = 'flight-cat-badge';
        var catMap = { 'VFR': 'cat-vfr', 'MVFR': 'cat-mvfr', 'IFR': 'cat-ifr', 'LIFR': 'cat-lifr' };
        if (catMap[cat]) catBadge.classList.add(catMap[cat]);
    }

    // QNH / QFE
    renderAltimetry(metar);

    // Decoded METAR
    var decodedEl = document.getElementById('wx-decoded-metar');
    if (!decodedEl) return;

    var windDir = metar.wind_direction === 0
        ? 'VRB'
        : String(metar.wind_direction).padStart(3, '0') + '\u00B0';
    var windGust = metar.wind_gust ? ' G' + metar.wind_gust : '';
    var visKm = (metar.visibility_m / 1000).toFixed(1);

    var cloudsText = 'CAVOK';
    if (metar.clouds && metar.clouds.length > 0) {
        cloudsText = metar.clouds.map(function (c) {
            return c.coverage + ' ' + c.base_ft + 'ft';
        }).join('  ');
    }

    decodedEl.innerHTML =
        wxItem('Wind', windDir + ' / ' + metar.wind_speed + 'kt' + windGust) +
        wxItem('Visibility', visKm + ' km') +
        wxItem('Clouds', cloudsText) +
        wxItem('Wx', metar.weather || '--') +
        wxItem('Temp / Dew', metar.temperature_c + ' / ' + metar.dewpoint_c + ' \u00B0C') +
        wxItem('QNH', '<span class="qnh-value">' + metar.qnh_hpa + ' hPa</span>');
}

// ---- QNH / QFE ----

var AD_ELEVATION_M = 369; // LEST aerodrome elevation

function renderAltimetry(metar) {
    var qnh = metar.qnh_hpa;
    var qnhEl = document.getElementById('qnh-value');
    var qfeEl = document.getElementById('qfe-value');
    if (!qnhEl || !qfeEl) return;

    if (!qnh) {
        qnhEl.textContent = '----';
        qfeEl.textContent = '----';
        return;
    }

    qnhEl.textContent = qnh;

    // QFE from QNH using ICAO standard atmosphere:
    // QFE = QNH * ((T0 - L * h) / T0) ^ (g*M / (R*L))
    // T0=288.15K, L=0.0065K/m, g=9.80665, M=0.0289644, R=8.31447
    var T0 = 288.15;
    var L = 0.0065;
    var exponent = 5.2561; // g*M / (R*L)
    var qfe = qnh * Math.pow((T0 - L * AD_ELEVATION_M) / T0, exponent);
    qfeEl.textContent = Math.round(qfe);
}

// ---- TAF ----

function renderTafModule(rawTaf) {
    // Raw
    var rawEl = document.getElementById('wx-raw-taf');
    if (rawEl) rawEl.textContent = rawTaf || 'No TAF available';

    // Decode
    var decodedEl = document.getElementById('wx-decoded-taf');
    var validityEl = document.getElementById('taf-validity');
    if (!decodedEl || !rawTaf) return;

    var parsed = parseTaf(rawTaf);

    // Validity badge
    if (validityEl && parsed.validity) {
        validityEl.textContent = parsed.validity;
    }

    // Build decoded HTML
    var html = '';

    // Base conditions
    if (parsed.base) {
        html += '<div class="taf-group">';
        html += '<div class="taf-group-label">BASE</div>';
        html += '<div class="wx-decoded">';
        if (parsed.base.wind) html += wxItem('Wind', parsed.base.wind);
        if (parsed.base.vis) html += wxItem('Visibility', parsed.base.vis);
        if (parsed.base.clouds) html += wxItem('Clouds', parsed.base.clouds);
        html += '</div></div>';
    }

    // Temperature
    if (parsed.tempMax || parsed.tempMin) {
        html += '<div class="taf-group">';
        html += '<div class="taf-group-label">TEMP</div>';
        html += '<div class="wx-decoded">';
        if (parsed.tempMax) html += wxItem('Max', parsed.tempMax);
        if (parsed.tempMin) html += wxItem('Min', parsed.tempMin);
        html += '</div></div>';
    }

    // Change groups (TEMPO, BECMG, FM, PROB)
    parsed.changes.forEach(function (chg) {
        html += '<div class="taf-group">';
        html += '<div class="taf-group-label">' + escapeHtml(chg.type) + '</div>';
        html += '<div class="wx-decoded">';
        if (chg.wind) html += wxItem('Wind', chg.wind);
        if (chg.vis) html += wxItem('Visibility', chg.vis);
        if (chg.clouds) html += wxItem('Clouds', chg.clouds);
        if (chg.wx) html += wxItem('Wx', chg.wx);
        html += '</div></div>';
    });

    decodedEl.innerHTML = html || '<div class="wx-decoded-item"><span>No data</span></div>';
}

// ---- TAF Parser ----

function parseTaf(raw) {
    var result = { validity: null, base: null, tempMax: null, tempMin: null, changes: [] };
    if (!raw) return result;

    // Normalize: join lines, collapse spaces
    var text = raw.replace(/\n/g, ' ').replace(/\s+/g, ' ').trim();

    // Extract validity (e.g. 1012/1112)
    var valMatch = text.match(/\b(\d{4}\/\d{4})\b/);
    if (valMatch) {
        var v = valMatch[1];
        result.validity = v.slice(0, 2) + 'd ' + v.slice(2, 4) + 'Z \u2192 ' +
            v.slice(5, 7) + 'd ' + v.slice(7, 9) + 'Z';
    }

    // Extract TX/TN temperatures
    var txMatch = text.match(/TX(\d{2})\/(\d{4}Z)/);
    if (txMatch) result.tempMax = txMatch[1] + '\u00B0C @ ' + txMatch[2];

    var tnMatch = text.match(/TN(\d{2})\/(\d{4}Z)/);
    if (tnMatch) result.tempMin = tnMatch[1] + '\u00B0C @ ' + tnMatch[2];

    // Split into groups by TEMPO, BECMG, FM, PROB
    var parts = text.split(/\s+(TEMPO|BECMG|FM\d{6}|PROB\d{2}\s+TEMPO|PROB\d{2})\s+/);

    // First part is base (after TAF header + validity)
    if (parts[0]) {
        result.base = parseWeatherTokens(parts[0]);
    }

    // Subsequent pairs: [type, content, type, content, ...]
    for (var i = 1; i < parts.length; i += 2) {
        var type = parts[i];
        var content = parts[i + 1] || '';
        var chg = parseWeatherTokens(content);
        chg.type = type;
        if (chg.wind || chg.vis || chg.clouds || chg.wx) {
            result.changes.push(chg);
        }
    }

    return result;
}

function parseWeatherTokens(text) {
    var r = { wind: null, vis: null, clouds: null, wx: null };

    // Wind: 24009KT or 24009G18KT or VRB03KT
    var wm = text.match(/(VRB|\d{3})(\d{2,3})(G(\d{2,3}))?KT/);
    if (wm) {
        var dir = wm[1] === 'VRB' ? 'VRB' : wm[1] + '\u00B0';
        var gust = wm[4] ? ' G' + wm[4] : '';
        r.wind = dir + ' / ' + wm[2] + 'kt' + gust;
    }

    // Visibility: 4-digit meters (e.g. 8000, 9999) or CAVOK
    if (text.indexOf('CAVOK') !== -1) {
        r.vis = 'CAVOK';
    } else {
        var vm = text.match(/\b(\d{4})\b/);
        if (vm && parseInt(vm[1]) <= 9999) {
            var m = parseInt(vm[1]);
            r.vis = (m >= 9999) ? '>10 km' : (m / 1000).toFixed(1) + ' km';
        }
    }

    // Clouds: FEW/SCT/BKN/OVC + altitude
    var cloudMatches = text.match(/(FEW|SCT|BKN|OVC)(\d{3})/g);
    if (cloudMatches) {
        r.clouds = cloudMatches.map(function (c) {
            var cov = c.slice(0, 3);
            var alt = parseInt(c.slice(3)) * 100;
            return cov + ' ' + alt + 'ft';
        }).join('  ');
    }

    // Weather phenomena
    var wxPatterns = text.match(/[-+]?(RA|SN|DZ|FG|BR|HZ|TS|SH|GR|SQ|FC|SS|DS|FZ|MI|PR|BC|BL|DR|VC)+/g);
    if (wxPatterns) {
        r.wx = wxPatterns.join(' ');
    }

    return r;
}

// ---- Helpers ----

function wxItem(label, value) {
    return '<div class="wx-decoded-item"><label>' + escapeHtml(label) +
        '</label><span>' + value + '</span></div>';
}

function startUTCClock() {
    var clockEl = document.getElementById('utc-clock');
    function update() {
        var now = new Date();
        clockEl.textContent =
            String(now.getUTCHours()).padStart(2, '0') + ':' +
            String(now.getUTCMinutes()).padStart(2, '0') + ':' +
            String(now.getUTCSeconds()).padStart(2, '0') + 'Z';
    }
    update();
    setInterval(update, 1000);
}

function updateRefreshTimestamp() {
    var el = document.getElementById('last-refresh');
    var now = new Date();
    el.textContent = 'Last refresh: ' +
        String(now.getUTCHours()).padStart(2, '0') + ':' +
        String(now.getUTCMinutes()).padStart(2, '0') + ':' +
        String(now.getUTCSeconds()).padStart(2, '0') + 'Z';
}

function setConnectionStatus(connected) {
    var el = document.getElementById('connection-status');
    el.textContent = connected ? 'CONNECTED' : 'DISCONNECTED';
    el.className = 'status-indicator ' + (connected ? 'connected' : 'disconnected');
}

function escapeHtml(text) {
    var div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
