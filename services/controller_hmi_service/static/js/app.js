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

var currentICAO = '';

function loadAirport() {
    fetch('/api/v1/hmi/airport')
        .then(function (resp) {
            if (!resp.ok) throw new Error('HTTP ' + resp.status);
            return resp.json();
        })
        .then(function (data) {
            var icao = data.icao || '----';
            var badge = document.getElementById('airport-badge');
            if (badge) badge.textContent = icao;
            var smrLabel = document.getElementById('smr-airport');
            if (smrLabel) smrLabel.textContent = icao;

            // Reload map, weather & TAF when airport changes
            if (icao !== currentICAO && icao !== '----') {
                currentICAO = icao;
                initSMRMap();
                loadWeather();
                loadTaf();
            }
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
// SMR Map (Surface Movement Radar) - Real Data
// ============================================

var smrGraph = null;   // Airport graph data from API
var smrBounds = null;  // { minLat, maxLat, minLon, maxLon }
var SMR_PADDING = 5;
var SMR_SIZE = 100;

// Pan & Zoom state
var smrViewBox = { x: 0, y: 0, w: 100, h: 100 };
var smrDrag = null; // { startX, startY, startVBx, startVBy }

function initSMRMap() {
    var container = document.getElementById('smr-map');
    if (!container) return;

    container.innerHTML = '<svg viewBox="0 0 100 100"><text x="50" y="50" text-anchor="middle" fill="#5a6672" font-size="3.5" font-family="monospace">Loading airport data...</text></svg>';

    fetch('/api/v1/hmi/airport/graph')
        .then(function (resp) {
            if (!resp.ok) throw new Error('HTTP ' + resp.status);
            return resp.json();
        })
        .then(function (data) {
            smrGraph = data;
            computeSMRBounds();
            renderSMRFromData();
        })
        .catch(function (err) {
            console.error('Failed to load airport graph:', err);
            container.innerHTML = '<svg viewBox="0 0 100 100"><text x="50" y="50" text-anchor="middle" fill="#ff1744" font-size="3" font-family="monospace">No airport data</text></svg>';
        });
}

function computeSMRBounds() {
    if (!smrGraph) return;
    var lats = [], lons = [];

    // Nodes (keyed by id)
    var nodeIds = Object.keys(smrGraph.nodes);
    nodeIds.forEach(function (id) {
        var n = smrGraph.nodes[id];
        lats.push(n.lat); lons.push(n.lon);
    });

    // Stands
    smrGraph.stands.forEach(function (s) { lats.push(s.lat); lons.push(s.lon); });

    // Runway endpoints
    smrGraph.runways.forEach(function (r) {
        lats.push(r.end1.lat, r.end2.lat);
        lons.push(r.end1.lon, r.end2.lon);
    });

    if (lats.length === 0) return;

    var minLat = Math.min.apply(null, lats);
    var maxLat = Math.max.apply(null, lats);
    var minLon = Math.min.apply(null, lons);
    var maxLon = Math.max.apply(null, lons);

    // Add margin
    var latMargin = (maxLat - minLat) * 0.08;
    var lonMargin = (maxLon - minLon) * 0.08;

    // Cosine correction: at this latitude, 1° lon is shorter than 1° lat
    var centerLat = (minLat + maxLat) / 2;
    var cosLat = Math.cos(centerLat * Math.PI / 180);

    smrBounds = {
        minLat: minLat - latMargin, maxLat: maxLat + latMargin,
        minLon: minLon - lonMargin, maxLon: maxLon + lonMargin,
        cosLat: cosLat
    };
}

// Convert GPS lat/lon to SVG x/y (0-100 viewBox) with correct 2D projection
function geoToSVG(lat, lon) {
    if (!smrBounds) return { x: 50, y: 50 };

    var dLat = smrBounds.maxLat - smrBounds.minLat;
    var dLon = (smrBounds.maxLon - smrBounds.minLon) * smrBounds.cosLat;

    // Fit proportionally inside the viewBox (preserve aspect ratio)
    var usable = SMR_SIZE - 2 * SMR_PADDING;
    var scale = usable / Math.max(dLat, dLon);

    var mapW = dLon * scale;
    var mapH = dLat * scale;
    var offX = SMR_PADDING + (usable - mapW) / 2;
    var offY = SMR_PADDING + (usable - mapH) / 2;

    var x = offX + (lon - smrBounds.minLon) * smrBounds.cosLat * scale;
    // Invert Y: north (high lat) = top
    var y = offY + (smrBounds.maxLat - lat) * scale;
    return { x: x, y: y };
}

function renderSMRFromData() {
    var container = document.getElementById('smr-map');
    if (!container || !smrGraph || !smrBounds) return;

    smrViewBox = { x: 0, y: 0, w: 100, h: 100 };

    var svg = '<svg id="smr-svg" viewBox="0 0 100 100" preserveAspectRatio="xMidYMid meet" style="cursor:grab">';

    // Background grid
    for (var gx = 0; gx <= 100; gx += 10) {
        svg += '<line x1="' + gx + '" y1="0" x2="' + gx + '" y2="100" stroke="#0d1520" stroke-width="0.15" vector-effect="non-scaling-stroke"/>';
    }
    for (var gy = 0; gy <= 100; gy += 10) {
        svg += '<line x1="0" y1="' + gy + '" x2="100" y2="' + gy + '" stroke="#0d1520" stroke-width="0.15" vector-effect="non-scaling-stroke"/>';
    }

    // --- Runways ---
    smrGraph.runways.forEach(function (rwy) {
        var p1 = geoToSVG(rwy.end1.lat, rwy.end1.lon);
        var p2 = geoToSVG(rwy.end2.lat, rwy.end2.lon);

        // Thick runway strip
        svg += '<line id="smr-runway-rect" x1="' + p1.x + '" y1="' + p1.y +
            '" x2="' + p2.x + '" y2="' + p2.y +
            '" stroke="#1a3a1a" stroke-width="3" stroke-linecap="round"/>';

        // Centerline dashes
        svg += '<line x1="' + p1.x + '" y1="' + p1.y +
            '" x2="' + p2.x + '" y2="' + p2.y +
            '" stroke="#2a4a2a" stroke-width="0.3" stroke-dasharray="1.5,1.5"/>';

        // Designators
        svg += '<text x="' + p1.x + '" y="' + (p1.y - 1.5) +
            '" text-anchor="middle" fill="#3a6a3a" data-base-fs="2.5" font-size="2.5" font-family="monospace" font-weight="700">' +
            rwy.end1.designator + '</text>';
        svg += '<text x="' + p2.x + '" y="' + (p2.y + 3) +
            '" text-anchor="middle" fill="#3a6a3a" data-base-fs="2.5" font-size="2.5" font-family="monospace" font-weight="700">' +
            rwy.end2.designator + '</text>';
    });

    // --- Taxiway edges ---
    var taxiwayLabels = {};

    smrGraph.edges.forEach(function (edge) {
        var n1 = smrGraph.nodes[edge.from];
        var n2 = smrGraph.nodes[edge.to];
        if (!n1 || !n2) return;

        var p1 = geoToSVG(n1.lat, n1.lon);
        var p2 = geoToSVG(n2.lat, n2.lon);

        var isRunway = edge.category === 'runway';
        var color = isRunway ? '#1a3a1a' : '#1a2a3a';
        var width = isRunway ? '1.5' : '1.2';

        svg += '<line x1="' + p1.x + '" y1="' + p1.y +
            '" x2="' + p2.x + '" y2="' + p2.y +
            '" stroke="' + color + '" stroke-width="' + width + '" stroke-linecap="round"/>';

        // Collect label position per taxiway category
        if (!isRunway && edge.category) {
            var twyName = edge.category.replace('taxiway_', '');
            if (!taxiwayLabels[twyName]) {
                taxiwayLabels[twyName] = {
                    x: (p1.x + p2.x) / 2,
                    y: (p1.y + p2.y) / 2
                };
            }
        }
    });

    // --- Taxiway labels ---
    Object.keys(taxiwayLabels).forEach(function (name) {
        var pos = taxiwayLabels[name];
        svg += '<text x="' + (pos.x - 2) + '" y="' + pos.y +
            '" text-anchor="middle" dominant-baseline="central" fill="#2a5a8a" data-base-fs="2" font-size="2" font-family="monospace" font-weight="700">' +
            name + '</text>';
    });

    // --- Stands / Gates ---
    smrGraph.stands.forEach(function (stand) {
        var p = geoToSVG(stand.lat, stand.lon);

        var isMil = stand.name.indexOf('Mil') !== -1;
        var isGA = stand.size_cats && (stand.size_cats.indexOf('helos') !== -1 || stand.size_cats.indexOf('props') !== -1);
        var dotColor = isMil ? '#4a5568' : isGA ? '#2a5a8a' : '#00e5ff';

        svg += '<rect class="smr-stand" data-cx="' + p.x + '" data-cy="' + p.y +
            '" x="' + (p.x - 0.6) + '" y="' + (p.y - 0.6) +
            '" width="1.2" height="1.2" data-base-size="1.2" fill="' + dotColor + '" opacity="0.5" rx="0.2"/>';

        svg += '<text x="' + p.x + '" y="' + (p.y + 1.8) +
            '" text-anchor="middle" fill="' + dotColor + '" data-base-fs="2" data-base-dy="2.2" font-size="2" font-family="monospace" opacity="0.8">' +
            stand.name + '</text>';
    });

    // --- Taxi nodes (dim dots) ---
    Object.keys(smrGraph.nodes).forEach(function (id) {
        var n = smrGraph.nodes[id];
        var p = geoToSVG(n.lat, n.lon);
        svg += '<circle cx="' + p.x + '" cy="' + p.y + '" r="0.3" data-base-r="0.3" fill="#1a2a3a" opacity="0.4"/>';
    });

    // Aircraft overlay group (on top)
    svg += '<g id="smr-aircraft-group"></g>';

    svg += '</svg>';
    container.innerHTML = svg;

    initSMRInteraction();
}

// --- Rescale elements to keep constant visual size at any zoom level ---

function rescaleSMRElements() {
    var svgEl = document.getElementById('smr-svg');
    if (!svgEl) return;

    var s = smrViewBox.w / 100; // zoom scale: 1 = no zoom, 0.1 = zoomed 10x

    // Rescale all text with data-base-fs
    var texts = svgEl.querySelectorAll('text[data-base-fs]');
    for (var i = 0; i < texts.length; i++) {
        var base = parseFloat(texts[i].getAttribute('data-base-fs'));
        texts[i].setAttribute('font-size', base * s);
        // Adjust stand label Y offset
        var baseDy = texts[i].getAttribute('data-base-dy');
        if (baseDy) {
            var cx = parseFloat(texts[i].getAttribute('x'));
            texts[i].setAttribute('y', cx ? parseFloat(texts[i].getAttribute('y')) : 0);
        }
    }

    // Rescale stand rects
    var rects = svgEl.querySelectorAll('rect.smr-stand');
    for (var j = 0; j < rects.length; j++) {
        var cx = parseFloat(rects[j].getAttribute('data-cx'));
        var cy = parseFloat(rects[j].getAttribute('data-cy'));
        var baseSize = parseFloat(rects[j].getAttribute('data-base-size'));
        var sz = baseSize * s;
        rects[j].setAttribute('x', cx - sz / 2);
        rects[j].setAttribute('y', cy - sz / 2);
        rects[j].setAttribute('width', sz);
        rects[j].setAttribute('height', sz);
        rects[j].setAttribute('rx', 0.2 * s);
    }

    // Rescale node circles
    var circles = svgEl.querySelectorAll('circle[data-base-r]');
    for (var k = 0; k < circles.length; k++) {
        var baseR = parseFloat(circles[k].getAttribute('data-base-r'));
        circles[k].setAttribute('r', baseR * s);
    }

    // Rescale aircraft dots and labels
    var acDots = svgEl.querySelectorAll('.smr-aircraft-dot');
    for (var m = 0; m < acDots.length; m++) {
        acDots[m].setAttribute('r', 0.6 * s);
    }
    var acLabels = svgEl.querySelectorAll('.smr-aircraft');
    for (var n = 0; n < acLabels.length; n++) {
        acLabels[n].setAttribute('font-size', 1 * s);
    }
}

// --- Pan & Zoom interaction ---

function initSMRInteraction() {
    var svgEl = document.getElementById('smr-svg');
    if (!svgEl) return;

    // Zoom with mouse wheel
    svgEl.addEventListener('wheel', function (e) {
        e.preventDefault();
        var zoomFactor = e.deltaY > 0 ? 1.15 : 0.87; // scroll down = zoom out

        // Mouse position in SVG coords
        var rect = svgEl.getBoundingClientRect();
        var mx = (e.clientX - rect.left) / rect.width;
        var my = (e.clientY - rect.top) / rect.height;

        // Point in viewBox under mouse
        var px = smrViewBox.x + mx * smrViewBox.w;
        var py = smrViewBox.y + my * smrViewBox.h;

        // New size
        var nw = smrViewBox.w * zoomFactor;
        var nh = smrViewBox.h * zoomFactor;

        // Clamp: don't zoom out beyond initial 100x100
        if (nw > 100) { nw = 100; nh = 100; }
        // Don't zoom in too far
        if (nw < 5) { nw = 5; nh = 5; }

        // Keep point under mouse fixed
        smrViewBox.x = px - mx * nw;
        smrViewBox.y = py - my * nh;
        smrViewBox.w = nw;
        smrViewBox.h = nh;

        clampViewBox();
        applySMRViewBox();
    }, { passive: false });

    // Pan with mouse drag
    svgEl.addEventListener('mousedown', function (e) {
        if (e.button !== 0) return; // left button only
        smrDrag = {
            startX: e.clientX,
            startY: e.clientY,
            startVBx: smrViewBox.x,
            startVBy: smrViewBox.y
        };
        svgEl.style.cursor = 'grabbing';
        e.preventDefault();
    });

    window.addEventListener('mousemove', function (e) {
        if (!smrDrag) return;
        var svgEl = document.getElementById('smr-svg');
        if (!svgEl) return;

        var rect = svgEl.getBoundingClientRect();
        // Convert pixel delta to viewBox units
        var dx = (e.clientX - smrDrag.startX) / rect.width * smrViewBox.w;
        var dy = (e.clientY - smrDrag.startY) / rect.height * smrViewBox.h;

        smrViewBox.x = smrDrag.startVBx - dx;
        smrViewBox.y = smrDrag.startVBy - dy;

        clampViewBox();
        applySMRViewBox();
    });

    window.addEventListener('mouseup', function () {
        if (smrDrag) {
            smrDrag = null;
            var svgEl = document.getElementById('smr-svg');
            if (svgEl) svgEl.style.cursor = 'grab';
        }
    });

    // Double-click to reset view
    svgEl.addEventListener('dblclick', function (e) {
        e.preventDefault();
        smrViewBox = { x: 0, y: 0, w: 100, h: 100 };
        applySMRViewBox();
    });
}

function clampViewBox() {
    if (smrViewBox.x < 0) smrViewBox.x = 0;
    if (smrViewBox.y < 0) smrViewBox.y = 0;
    if (smrViewBox.x + smrViewBox.w > 100) smrViewBox.x = 100 - smrViewBox.w;
    if (smrViewBox.y + smrViewBox.h > 100) smrViewBox.y = 100 - smrViewBox.h;
}

function applySMRViewBox() {
    var svgEl = document.getElementById('smr-svg');
    if (!svgEl) return;
    svgEl.setAttribute('viewBox',
        smrViewBox.x + ' ' + smrViewBox.y + ' ' + smrViewBox.w + ' ' + smrViewBox.h);
    rescaleSMRElements();
}

// --- Place aircraft on SMR based on strip phase ---

function updateSMRAircraft(plans) {
    var group = document.getElementById('smr-aircraft-group');
    if (!group || !smrGraph || !smrBounds) return;

    group.innerHTML = '';
    if (!plans || plans.length === 0) return;

    // Build zone positions from real data
    var standPositions = [];
    var taxiPositions = [];
    var runwayPositions = [];

    smrGraph.stands.forEach(function (s) {
        standPositions.push(geoToSVG(s.lat, s.lon));
    });

    // Collect unique taxiway node positions
    var seenTaxiNodes = {};
    smrGraph.edges.forEach(function (edge) {
        if (edge.category !== 'runway') {
            if (!seenTaxiNodes[edge.from]) {
                var n = smrGraph.nodes[edge.from];
                if (n) { taxiPositions.push(geoToSVG(n.lat, n.lon)); seenTaxiNodes[edge.from] = true; }
            }
        }
    });

    // Interpolated positions along runway
    smrGraph.runways.forEach(function (rwy) {
        var p1 = geoToSVG(rwy.end1.lat, rwy.end1.lon);
        var p2 = geoToSVG(rwy.end2.lat, rwy.end2.lon);
        for (var t = 0.2; t <= 0.8; t += 0.1) {
            runwayPositions.push({
                x: p1.x + (p2.x - p1.x) * t,
                y: p1.y + (p2.y - p1.y) * t
            });
        }
    });

    var counters = { PRE_TAXI: 0, TAXI: 0, RUNWAY: 0 };

    plans.forEach(function (plan) {
        var reg = plan.aircraft_registration;
        var column = getStripColumn(reg);
        var phase = getStripPhase(reg);
        var idx = counters[column]++;
        var pos;

        if (column === 'PRE_TAXI' && standPositions.length > 0) {
            pos = standPositions[idx % standPositions.length];
        } else if (column === 'TAXI' && taxiPositions.length > 0) {
            pos = taxiPositions[idx % taxiPositions.length];
        } else if (column === 'RUNWAY' && runwayPositions.length > 0) {
            pos = runwayPositions[idx % runwayPositions.length];
        } else {
            pos = { x: 50, y: 50 };
        }

        var dotClass = 'smr-aircraft-dot';
        if (column === 'RUNWAY' && phase !== 'CLEARED') {
            dotClass += ' incursion';
        } else if (column === 'RUNWAY') {
            dotClass += ' cleared';
        } else if (column === 'TAXI') {
            dotClass += ' on-runway';
        }

        group.innerHTML +=
            '<circle class="' + dotClass + '" cx="' + pos.x + '" cy="' + pos.y + '" r="0.6"/>' +
            '<text class="smr-aircraft" x="' + (pos.x + 2) + '" y="' + (pos.y + 0.5) +
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
