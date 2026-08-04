// weather.js -- TWR HMI: METAR & TAF rendering + Dashboard Superior

// ---- METAR ----

var AD_ELEVATION_M = 369; // LEST aerodrome elevation

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

    // QNH / QFE with alerts
    renderAltimetry(metar);

    // Icon-based decoded METAR
    renderMetarIcons(metar);
}

// ---- QNH / QFE with color alerts ----

function renderAltimetry(metar) {
    var qnh = metar.qnh_hpa;
    var qnhEl = document.getElementById('qnh-value');
    var qfeEl = document.getElementById('qfe-value');
    if (!qnhEl || !qfeEl) return;

    if (!qnh) {
        qnhEl.textContent = '----';
        qfeEl.textContent = '----';
        qnhEl.classList.remove('alert-low');
        qfeEl.classList.remove('alert-low');
        return;
    }

    qnhEl.textContent = qnh;

    // QFE calculation (ICAO standard atmosphere)
    var T0 = 288.15;
    var L = 0.0065;
    var exponent = 5.2561;
    var qfe = qnh * Math.pow((T0 - L * AD_ELEVATION_M) / T0, exponent);
    qfeEl.textContent = Math.round(qfe);

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

function renderMetarIcons(metar) {
    // Clouds icon
    var cloudsEl = document.getElementById('metar-clouds-text');
    if (cloudsEl) {
        if (metar.clouds && metar.clouds.length > 0) {
            cloudsEl.textContent = metar.clouds.map(function (c) {
                return c.coverage + ' ' + c.base_ft + 'ft';
            }).join(' | ');
        } else {
            cloudsEl.textContent = 'CAVOK';
        }
    }

    // Visibility icon + bar
    var visEl = document.getElementById('metar-vis-text');
    var visBar = document.getElementById('metar-vis-bar');
    if (visEl && metar.visibility_m !== undefined) {
        var rawHas9999 = metar.raw_metar && /\b9999\b/.test(metar.raw_metar);
        var visKm = metar.visibility_m / 1000;
        visEl.textContent = rawHas9999 ? '+10 km' : visKm.toFixed(1) + ' km';

        if (visBar) {
            var pct = Math.min(100, (visKm / 10) * 100);
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
    var windEl = document.getElementById('metar-wind-text');
    if (windEl) {
        var windDir = metar.wind_direction === 0
            ? 'VRB'
            : String(metar.wind_direction).padStart(3, '0') + '\u00B0';
        var gustText = metar.wind_gust ? ' G' + metar.wind_gust : '';
        windEl.textContent = windDir + '/' + metar.wind_speed + 'kt' + gustText;
    }

    // Weather phenomena
    var wxEl = document.getElementById('metar-wx-text');
    if (wxEl) {
        wxEl.textContent = metar.weather || 'NIL';
    }

    // Temperature
    var tempEl = document.getElementById('metar-temp-text');
    if (tempEl) {
        tempEl.textContent = metar.temperature_c + '/' + metar.dewpoint_c + '\u00B0C';
    }
}

// ---- TAF ----

function renderTafModule(rawTaf) {
    var rawEl = document.getElementById('wx-raw-taf');
    var decodedEl = document.getElementById('wx-decoded-taf');
    var validityEl = document.getElementById('taf-validity');

    // Extract only the TAF portion (discard any METAR lines mixed in)
    if (rawTaf) {
        // Try to find "TAF" or "TAF AMD" at start of line or string
        var tafMatch = rawTaf.match(/(^|\n)(TAF\s)/);
        if (tafMatch) {
            rawTaf = rawTaf.substring(tafMatch.index + (tafMatch[1] ? tafMatch[1].length : 0));
        } else {
            // Fallback: find any occurrence of "TAF "
            var idx = rawTaf.indexOf('TAF ');
            if (idx !== -1) {
                rawTaf = rawTaf.substring(idx);
            }
        }
    }

    if (rawEl) rawEl.textContent = rawTaf || 'No TAF available';
    if (!decodedEl || !rawTaf) return;

    var parsed = parseTaf(rawTaf);

    if (validityEl && parsed.validity) {
        validityEl.textContent = parsed.validity;
    }

    var html = '';

    if (parsed.base) {
        html += '<div class="taf-group">';
        html += '<span class="taf-group-label">BASE</span> ';
        html += tafLine(parsed.base);
        html += '</div>';
    }

    parsed.changes.forEach(function (chg) {
        html += '<div class="taf-group">';
        html += '<span class="taf-group-label">' + escapeHtml(chg.type) + '</span> ';
        html += tafLine(chg);
        html += '</div>';
    });

    decodedEl.innerHTML = html || '<span style="color:var(--text-dim)">No data</span>';
}

function tafLine(grp) {
    var parts = [];
    if (grp.wind) parts.push(grp.wind);
    if (grp.vis) parts.push(grp.vis);
    if (grp.clouds) parts.push(grp.clouds);
    if (grp.wx) parts.push(grp.wx);
    return '<span>' + parts.join(' | ') + '</span>';
}

// ---- TAF Parser ----

function parseTaf(raw) {
    var result = { validity: null, base: null, tempMax: null, tempMin: null, changes: [] };
    if (!raw) return result;

    var text = raw.replace(/\n/g, ' ').replace(/\s+/g, ' ').trim();

    var valMatch = text.match(/\b(\d{4}\/\d{4})\b/);
    if (valMatch) {
        var v = valMatch[1];
        result.validity = v.slice(0, 2) + 'd ' + v.slice(2, 4) + 'Z \u2192 ' +
            v.slice(5, 7) + 'd ' + v.slice(7, 9) + 'Z';
    }

    var txMatch = text.match(/TX(\d{2})\/(\d{4}Z)/);
    if (txMatch) result.tempMax = txMatch[1] + '\u00B0C @ ' + txMatch[2];

    var tnMatch = text.match(/TN(\d{2})\/(\d{4}Z)/);
    if (tnMatch) result.tempMin = tnMatch[1] + '\u00B0C @ ' + tnMatch[2];

    var parts = text.split(/\s+(TEMPO|BECMG|FM\d{6}|PROB\d{2}\s+TEMPO|PROB\d{2})\s+/);

    if (parts[0]) {
        result.base = parseWeatherTokens(parts[0]);
    }

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

    var wm = text.match(/(VRB|\d{3})(\d{2,3})(G(\d{2,3}))?KT/);
    if (wm) {
        var dir = wm[1] === 'VRB' ? 'VRB' : wm[1] + '\u00B0';
        var gust = wm[4] ? ' G' + wm[4] : '';
        r.wind = dir + '/' + wm[2] + 'kt' + gust;
    }

    if (text.indexOf('CAVOK') !== -1) {
        r.vis = 'CAVOK';
    } else {
        var vm = text.match(/\b(\d{4})\b/);
        if (vm && parseInt(vm[1]) <= 9999) {
            var m = parseInt(vm[1]);
            r.vis = (m >= 9999) ? '>10 km' : (m / 1000).toFixed(1) + ' km';
        }
    }

    var cloudMatches = text.match(/(FEW|SCT|BKN|OVC)(\d{3})/g);
    if (cloudMatches) {
        r.clouds = cloudMatches.map(function (c) {
            var cov = c.slice(0, 3);
            var alt = parseInt(c.slice(3)) * 100;
            return cov + ' ' + alt + 'ft';
        }).join(' ');
    }

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
    if (!clockEl) return;

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
    if (!el) return;
    var now = new Date();
    el.textContent = 'Last refresh: ' +
        String(now.getUTCHours()).padStart(2, '0') + ':' +
        String(now.getUTCMinutes()).padStart(2, '0') + ':' +
        String(now.getUTCSeconds()).padStart(2, '0') + 'Z';
}

function setConnectionStatus(connected) {
    var el = document.getElementById('connection-status');
    if (!el) return;
    el.textContent = connected ? 'CONNECTED' : 'DISCONNECTED';
    el.className = 'status-indicator ' + (connected ? 'connected' : 'disconnected');
}

function escapeHtml(text) {
    var div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

export {
    renderWeatherModule,
    renderTafModule,
    startUTCClock,
    updateRefreshTimestamp,
    setConnectionStatus,
    escapeHtml,
};
