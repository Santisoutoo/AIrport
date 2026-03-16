// efs.js -- TWR HMI: 3-Column Electronic Flight Strips with Action Buttons

var API_BASE = '/api/v1/hmi';

// Client-side strip states: { "registration": { phase, column } }
var stripStates = {};

// Phase -> Column mapping
var PHASE_COLUMN = {
    'PRE_TAXI': 'PRE_TAXI',
    'PUSHBACK': 'PRE_TAXI',
    'TAXI': 'TAXI',
    'LINEUP': 'RUNWAY',
    'CLEARED': 'RUNWAY'
};

// Column body ID -> default phase when a strip is dropped there
var COLUMN_DEFAULT_PHASE = {
    'strips-pretaxi': 'PRE_TAXI',
    'strips-taxi':    'TAXI',
    'strips-runway':  'LINEUP'
};

var _dropZonesInited = false;

// ---- Load strip states from server ----

function loadStripStates(callback) {
    fetch(API_BASE + '/strips/states')
        .then(function (resp) {
            if (!resp.ok) throw new Error('HTTP ' + resp.status);
            return resp.json();
        })
        .then(function (data) {
            stripStates = data || {};
            if (callback) callback();
        })
        .catch(function () {
            if (callback) callback();
        });
}

// ---- Get/Set strip phase ----

function getStripPhase(reg) {
    if (stripStates[reg]) return stripStates[reg].phase;
    return 'PRE_TAXI';
}

function getStripColumn(reg) {
    var phase = getStripPhase(reg);
    return PHASE_COLUMN[phase] || 'PRE_TAXI';
}

function setStripPhase(reg, phase) {
    var column = PHASE_COLUMN[phase] || 'PRE_TAXI';
    stripStates[reg] = { phase: phase, column: column };

    // Persist to server
    fetch(API_BASE + '/strips/' + encodeURIComponent(reg) + '/state', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phase: phase })
    }).catch(function (err) {
        console.error('Failed to save strip state:', err);
    });
}

// ---- Render strips into 3 columns ----

function renderFlightStrips(plans) {
    var preTaxiContainer = document.getElementById('strips-pretaxi');
    var taxiContainer = document.getElementById('strips-taxi');
    var runwayContainer = document.getElementById('strips-runway');

    if (!preTaxiContainer || !taxiContainer || !runwayContainer) return;

    preTaxiContainer.innerHTML = '';
    taxiContainer.innerHTML = '';
    runwayContainer.innerHTML = '';

    var counts = { PRE_TAXI: 0, TAXI: 0, RUNWAY: 0 };

    if (!plans || plans.length === 0) {
        preTaxiContainer.innerHTML = emptyState();
        updateColumnCounts(counts);
        return;
    }

    plans.forEach(function (plan) {
        var reg = plan.aircraft_registration;
        var column = getStripColumn(reg);
        var phase = getStripPhase(reg);
        var strip = createStripElement(plan, phase);

        if (column === 'TAXI') {
            taxiContainer.appendChild(strip);
            counts.TAXI++;
        } else if (column === 'RUNWAY') {
            runwayContainer.appendChild(strip);
            counts.RUNWAY++;
        } else {
            preTaxiContainer.appendChild(strip);
            counts.PRE_TAXI++;
        }
    });

    if (counts.PRE_TAXI === 0) preTaxiContainer.innerHTML = emptyState();
    if (counts.TAXI === 0) taxiContainer.innerHTML = emptyState();
    if (counts.RUNWAY === 0) runwayContainer.innerHTML = emptyState();

    updateColumnCounts(counts);

    if (!_dropZonesInited) {
        _initDropZones();
        _dropZonesInited = true;
    }
}

function updateColumnCounts(counts) {
    var el;
    el = document.getElementById('count-pretaxi');
    if (el) el.textContent = counts.PRE_TAXI;
    el = document.getElementById('count-taxi');
    if (el) el.textContent = counts.TAXI;
    el = document.getElementById('count-runway');
    if (el) el.textContent = counts.RUNWAY;
}

function emptyState() {
    return '<div class="strips-empty">' +
        '<div class="strips-empty-icon">&#9992;</div>' +
        '<div>Empty</div></div>';
}

// ---- Create Strip Card ----

function createStripElement(plan, phase) {
    var strip = document.createElement('div');
    strip.className = 'flight-strip phase-' + phase.toLowerCase();
    strip.dataset.registration = plan.aircraft_registration;
    strip.draggable = true;
    strip.addEventListener('dragstart', function (e) {
        e.dataTransfer.setData('text/plain', plan.aircraft_registration);
        e.dataTransfer.effectAllowed = 'move';
        setTimeout(function () { strip.classList.add('dragging'); }, 0);
    });
    strip.addEventListener('dragend', function () {
        strip.classList.remove('dragging');
    });

    var isIFR = plan.flight_rules === 'I';
    var rulesClass = isIFR ? 'ifr' : 'vfr';
    var rulesText = isIFR ? 'IFR' : 'VFR';

    // WTC
    var wtcClasses = { 'H': 'wtc-heavy', 'M': 'wtc-medium', 'L': 'wtc-light', 'J': 'wtc-super' };
    var wtcClass = wtcClasses[plan.wake_turbulence_category] || 'wtc-medium';

    // Altitude display
    var altDisplay;
    if (plan.cruising_altitude >= 10000) {
        altDisplay = 'FL' + Math.round(plan.cruising_altitude / 100);
    } else {
        altDisplay = plan.cruising_altitude + 'ft';
    }

    // Squawk (generate from registration if not available)
    var squawk = plan.squawk || generateSquawk(plan.aircraft_registration);

    // SID (extract first waypoint from route or use route)
    var sid = plan.route ? truncateRoute(plan.route, 12) : 'DCT';

    // Build strip HTML
    strip.innerHTML =
        // Top row: rules, callsign, type, WTC
        '<div class="strip-info-row">' +
            '<span class="strip-rules ' + rulesClass + '">' + rulesText + '</span>' +
            '<span class="strip-callsign">' + escapeHtml(plan.aircraft_registration) + '</span>' +
            '<span class="strip-type">' + escapeHtml(plan.aircraft_type) + '</span>' +
            '<span class="strip-wtc ' + wtcClass + '">' + escapeHtml(plan.wake_turbulence_category) + '</span>' +
        '</div>' +
        // Detail row: SID, SQ, Alt, Dest
        '<div class="strip-details-row">' +
            '<span><span class="strip-detail-label">SID:</span> <span class="strip-sid">' + escapeHtml(sid) + '</span></span>' +
            '<span><span class="strip-detail-label">SQ:</span> <span class="strip-sq">' + squawk + '</span></span>' +
            '<span class="strip-alt">' + altDisplay + '</span>' +
            '<span class="strip-dest">' + escapeHtml(plan.destination_ICAO) + '</span>' +
        '</div>' +
        // Action buttons
        '<div class="strip-actions">' +
            actionBtn('PUSH', 'btn-push', plan.aircraft_registration, phase, 'PUSHBACK') +
            actionBtn('TAXI', 'btn-taxi', plan.aircraft_registration, phase, 'TAXI') +
            actionBtn('LINE-UP', 'btn-lineup', plan.aircraft_registration, phase, 'LINEUP') +
            actionBtn('CLEARED', 'btn-cleared', plan.aircraft_registration, phase, 'CLEARED') +
        '</div>';

    // Attach button event listeners
    strip.querySelectorAll('.strip-action-btn').forEach(function (btn) {
        btn.addEventListener('click', function (e) {
            e.stopPropagation();
            var targetPhase = btn.dataset.phase;
            var reg = btn.dataset.reg;
            // PUSH toggles: click again while already in PUSHBACK → revert to PRE_TAXI
            if (targetPhase === 'PUSHBACK' && getStripPhase(reg) === 'PUSHBACK') {
                targetPhase = 'PRE_TAXI';
            }
            setStripPhase(reg, targetPhase);
            // Re-render all strips
            if (typeof rerenderStrips === 'function') rerenderStrips();
        });
    });

    return strip;
}

function actionBtn(label, cssClass, reg, currentPhase, targetPhase) {
    var activeClass = currentPhase === targetPhase ? ' active-phase' : '';
    return '<button class="strip-action-btn ' + cssClass + activeClass +
        '" data-phase="' + targetPhase +
        '" data-reg="' + escapeHtml(reg) + '">' + label + '</button>';
}

function generateSquawk(reg) {
    // Simple hash-based squawk code from registration
    var hash = 0;
    for (var i = 0; i < reg.length; i++) {
        hash = ((hash << 5) - hash) + reg.charCodeAt(i);
        hash |= 0;
    }
    var code = Math.abs(hash) % 7000 + 1000;
    // Ensure valid squawk (digits 0-7 only)
    var str = String(code);
    var result = '';
    for (var j = 0; j < 4; j++) {
        var d = parseInt(str[j]) || 0;
        result += Math.min(d, 7);
    }
    return result;
}

function truncateRoute(route, maxLen) {
    if (!route) return 'DCT';
    if (route.length <= maxLen) return route;
    return route.substring(0, maxLen) + '...';
}

function _initDropZones() {
    Object.keys(COLUMN_DEFAULT_PHASE).forEach(function (colId) {
        var col = document.getElementById(colId);
        if (!col) return;

        col.addEventListener('dragover', function (e) {
            e.preventDefault();
            e.dataTransfer.dropEffect = 'move';
            col.classList.add('drag-over');
        });

        col.addEventListener('dragleave', function (e) {
            // Only remove if leaving the column itself, not entering a child
            if (!col.contains(e.relatedTarget)) {
                col.classList.remove('drag-over');
            }
        });

        col.addEventListener('drop', function (e) {
            e.preventDefault();
            col.classList.remove('drag-over');
            var reg = e.dataTransfer.getData('text/plain');
            if (!reg) return;
            var newPhase = COLUMN_DEFAULT_PHASE[colId];
            if (newPhase && getStripPhase(reg) !== newPhase) {
                setStripPhase(reg, newPhase);
                if (typeof rerenderStrips === 'function') rerenderStrips();
            }
        });
    });
}

function sortFlightPlans(plans, sortBy) {
    return plans.slice().sort(function (a, b) {
        switch (sortBy) {
            case 'departure_time':
                return a.departure_time - b.departure_time;
            case 'callsign':
                return a.aircraft_registration.localeCompare(b.aircraft_registration);
            case 'destination':
                return a.destination_ICAO.localeCompare(b.destination_ICAO);
            default:
                return 0;
        }
    });
}
