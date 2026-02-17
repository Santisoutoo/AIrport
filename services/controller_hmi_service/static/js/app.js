// app.js -- TWR HMI: Main application controller & SMR Map

var STRIP_REFRESH_MS = 15000;
var WEATHER_REFRESH_MS = 60000;
var AIRPORT_REFRESH_MS = 30000;

var flightPlans = [];

// ---- Initialization ----

document.addEventListener('DOMContentLoaded', function () {
    startUTCClock();
    initWindInstruments();
    initLightingControls();
    initSMRMap();

    loadAirport();
    loadStripStates(function () {
        loadFlightStrips();
    });
    loadWeather();
    loadTaf();

    // Auto-refresh
    setInterval(loadAirport, AIRPORT_REFRESH_MS);
    setInterval(function () {
        loadStripStates(function () { loadFlightStrips(); });
    }, STRIP_REFRESH_MS);
    setInterval(loadWeather, WEATHER_REFRESH_MS);
    setInterval(loadTaf, WEATHER_REFRESH_MS);
});

// ---- Data Loading ----

function loadFlightStrips() {
    fetch('/api/v1/hmi/strips')
        .then(function (resp) {
            if (!resp.ok) throw new Error('HTTP ' + resp.status);
            return resp.json();
        })
        .then(function (data) {
            flightPlans = data;
            rerenderStrips();
            updateRefreshTimestamp();
            setConnectionStatus(true);
        })
        .catch(function (err) {
            console.error('Failed to load strips:', err);
            setConnectionStatus(false);
        });
}

function rerenderStrips() {
    renderFlightStrips(flightPlans);
    updateSMRAircraft(flightPlans);
    checkRIMCAS();
}

function loadWeather() {
    fetch('/api/v1/hmi/weather')
        .then(function (resp) {
            if (!resp.ok) throw new Error('HTTP ' + resp.status);
            return resp.json();
        })
        .then(function (data) {
            renderWeatherModule(data);
            updateWindInstruments(data);
        })
        .catch(function (err) {
            console.error('Failed to load weather:', err);
        });
}

function loadAirport() {
    fetch('/api/v1/hmi/airport')
        .then(function (resp) {
            if (!resp.ok) throw new Error('HTTP ' + resp.status);
            return resp.json();
        })
        .then(function (data) {
            var badge = document.getElementById('airport-badge');
            if (badge) badge.textContent = data.icao || '----';
            var smrLabel = document.getElementById('smr-airport');
            if (smrLabel) smrLabel.textContent = data.icao || '----';
        })
        .catch(function (err) {
            console.error('Failed to load airport:', err);
        });
}

function loadTaf() {
    fetch('/api/v1/hmi/taf')
        .then(function (resp) {
            if (!resp.ok) throw new Error('HTTP ' + resp.status);
            return resp.json();
        })
        .then(function (data) {
            // Handle various response structures from the weather service
            var rawTaf = null;
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
        .catch(function (err) {
            console.error('Failed to load TAF:', err);
            renderTafModule('TAF unavailable');
        });
}

// ============================================
// SMR Map (Surface Movement Radar) - LEST
// ============================================

// LEST airport schematic positions (normalized 0-100 coordinate system)
var SMR_CONFIG = {
    // Runway 17/35 (roughly north-south)
    runway: { x1: 50, y1: 8, x2: 50, y2: 88, width: 6 },
    // Taxiways
    taxiways: [
        { id: 'A', points: '30,30 40,30 50,30', label: { x: 28, y: 30 } },
        { id: 'B', points: '30,55 40,55 50,55', label: { x: 28, y: 55 } },
        { id: 'C', points: '30,75 40,75 50,75', label: { x: 28, y: 75 } },
        { id: 'D', points: '50,30 60,30 65,35', label: { x: 67, y: 35 } }
    ],
    // Apron / Gate areas
    aprons: [
        { id: 'APRON', x: 15, y: 38, w: 20, h: 30, label: 'APRON' }
    ],
    // Holding points
    holdingPoints: [
        { id: 'A1', x: 48, y: 30 },
        { id: 'B1', x: 48, y: 55 },
        { id: 'C1', x: 48, y: 75 }
    ],
    // Aircraft placement zones per column
    zones: {
        PRE_TAXI: { x: 22, y: 42, spread: 16 },
        TAXI: { x: 38, y: 45, spread: 20 },
        RUNWAY: { x: 50, y: 48, spread: 16 }
    }
};

function initSMRMap() {
    var container = document.getElementById('smr-map');
    if (!container) return;

    var svg = '<svg viewBox="0 0 100 100" preserveAspectRatio="xMidYMid meet">';

    // Background grid
    for (var gx = 0; gx <= 100; gx += 10) {
        svg += '<line x1="' + gx + '" y1="0" x2="' + gx + '" y2="100" stroke="#0d1520" stroke-width="0.2"/>';
    }
    for (var gy = 0; gy <= 100; gy += 10) {
        svg += '<line x1="0" y1="' + gy + '" x2="100" y2="' + gy + '" stroke="#0d1520" stroke-width="0.2"/>';
    }

    // Runway
    var rwy = SMR_CONFIG.runway;
    svg += '<rect id="smr-runway-rect" x="' + (rwy.x1 - rwy.width / 2) + '" y="' + rwy.y1 +
        '" width="' + rwy.width + '" height="' + (rwy.y2 - rwy.y1) +
        '" fill="#0d1a0d" stroke="#1a3a1a" stroke-width="0.3" rx="0.5"/>';

    // Runway centerline dashes
    for (var ry = rwy.y1 + 3; ry < rwy.y2 - 3; ry += 5) {
        svg += '<line x1="' + rwy.x1 + '" y1="' + ry + '" x2="' + rwy.x1 + '" y2="' + (ry + 2.5) +
            '" stroke="#2a4a2a" stroke-width="0.3"/>';
    }

    // Runway designators
    svg += '<text x="' + rwy.x1 + '" y="' + (rwy.y1 + 4) +
        '" text-anchor="middle" fill="#3a6a3a" font-size="3" font-family="monospace" font-weight="700">17</text>';
    svg += '<text x="' + rwy.x1 + '" y="' + (rwy.y2 - 2) +
        '" text-anchor="middle" fill="#3a6a3a" font-size="3" font-family="monospace" font-weight="700">35</text>';

    // Taxiways
    SMR_CONFIG.taxiways.forEach(function (tw) {
        svg += '<polyline points="' + tw.points + '" fill="none" stroke="#1a2a3a" stroke-width="1.5" stroke-linecap="round"/>';
        svg += '<text x="' + tw.label.x + '" y="' + tw.label.y +
            '" text-anchor="middle" dominant-baseline="central" fill="#2a5a8a" font-size="2.5" font-family="monospace" font-weight="700">' +
            tw.id + '</text>';
    });

    // Aprons
    SMR_CONFIG.aprons.forEach(function (ap) {
        svg += '<rect x="' + ap.x + '" y="' + ap.y + '" width="' + ap.w + '" height="' + ap.h +
            '" fill="#0d1117" stroke="#1a2535" stroke-width="0.3" rx="1"/>';
        svg += '<text x="' + (ap.x + ap.w / 2) + '" y="' + (ap.y + ap.h / 2) +
            '" text-anchor="middle" dominant-baseline="central" fill="#2a3a4a" font-size="2.5" font-family="monospace" font-weight="700">' +
            ap.label + '</text>';

        // Gate marks
        for (var g = 0; g < 5; g++) {
            var gateY = ap.y + 4 + g * (ap.h - 8) / 4;
            svg += '<rect x="' + (ap.x + ap.w - 2) + '" y="' + gateY +
                '" width="2" height="1.5" fill="none" stroke="#1a3040" stroke-width="0.2" rx="0.3"/>';
        }
    });

    // Holding points
    SMR_CONFIG.holdingPoints.forEach(function (hp) {
        svg += '<line x1="' + (hp.x - 1) + '" y1="' + hp.y + '" x2="' + (hp.x + 1) + '" y2="' + hp.y +
            '" stroke="#8b0000" stroke-width="0.4"/>';
        svg += '<text x="' + (hp.x - 2.5) + '" y="' + (hp.y + 0.3) +
            '" text-anchor="middle" fill="#8b0000" font-size="1.8" font-family="monospace">' + hp.id + '</text>';
    });

    // Aircraft container group
    svg += '<g id="smr-aircraft-group"></g>';

    svg += '</svg>';
    container.innerHTML = svg;
}

function updateSMRAircraft(plans) {
    var group = document.getElementById('smr-aircraft-group');
    if (!group) return;

    group.innerHTML = '';

    if (!plans || plans.length === 0) return;

    var columnCounters = { PRE_TAXI: 0, TAXI: 0, RUNWAY: 0 };

    plans.forEach(function (plan) {
        var reg = plan.aircraft_registration;
        var column = getStripColumn(reg);
        var phase = getStripPhase(reg);
        var zone = SMR_CONFIG.zones[column];
        if (!zone) return;

        var idx = columnCounters[column]++;
        var x, y;

        if (column === 'PRE_TAXI') {
            // Spread vertically in apron area
            x = zone.x + (idx % 3) * 4;
            y = zone.y + idx * 3;
        } else if (column === 'TAXI') {
            // Spread along taxiway
            x = zone.x + idx * 3;
            y = zone.y + (idx % 2) * 4;
        } else {
            // On or near runway
            x = zone.x;
            y = zone.y + idx * 5;
        }

        // Determine dot class
        var dotClass = 'smr-aircraft-dot';
        if (column === 'RUNWAY' && phase !== 'CLEARED') {
            dotClass += ' incursion';
        } else if (column === 'RUNWAY') {
            dotClass += ' cleared';
        } else if (column === 'TAXI') {
            dotClass += ' on-runway';
        }

        // Aircraft dot
        group.innerHTML +=
            '<circle class="' + dotClass + '" cx="' + x + '" cy="' + y + '" r="1.2"/>' +
            '<text class="smr-aircraft" x="' + (x + 2) + '" y="' + (y + 0.5) +
            '" dominant-baseline="central">' + escapeHtml(reg.slice(-4)) + '</text>';
    });
}

// ---- RIMCAS (Runway Incursion Alert) ----

function checkRIMCAS() {
    var hasIncursion = false;

    flightPlans.forEach(function (plan) {
        var reg = plan.aircraft_registration;
        var column = getStripColumn(reg);
        var phase = getStripPhase(reg);

        // Incursion: aircraft in RUNWAY column but only at LINEUP phase (not yet CLEARED)
        if (column === 'RUNWAY' && phase === 'LINEUP') {
            hasIncursion = true;
        }
    });

    var alertEl = document.getElementById('rimcas-alert');
    var rwyRect = document.getElementById('smr-runway-rect');

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

function initLightingControls() {
    // PAPI slider
    var papiSlider = document.getElementById('papi-slider');
    var papiValue = document.getElementById('papi-value');
    if (papiSlider && papiValue) {
        papiSlider.addEventListener('input', function () {
            papiValue.textContent = papiSlider.value;
        });
    }

    // Toggle buttons
    initToggleButton('stopbar-btn');
    initToggleButton('rwy-lights-btn');
    initToggleButton('approach-lights-btn');
}

function initToggleButton(id) {
    var btn = document.getElementById(id);
    if (!btn) return;

    btn.addEventListener('click', function () {
        var isOn = btn.classList.contains('stopbar-on');
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
