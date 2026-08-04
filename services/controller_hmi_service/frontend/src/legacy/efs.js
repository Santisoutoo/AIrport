// efs.js -- TWR HMI: 3-Column Electronic Flight Strips with Action Buttons

import { currentICAO, flightPlans, rerenderStrips, updateSMRAircraft } from './app.js';
import { escapeHtml } from './weather';

var API_BASE = '/api/v1/hmi';

// Client-side strip states: { "registration": { phase, column } }
var stripStates = {};

// Phase -> Column mapping
var PHASE_COLUMN = {
    'PRE_TAXI': 'PRE_TAXI',
    'PUSHBACK': 'PRE_TAXI',
    'TAXI': 'TAXI',
    'LINEUP': 'RUNWAY',
    'CLEARED': 'RUNWAY',
    'APPROACH': 'ARRIVALS',
    'LANDED':   'ARRIVALS',
    'VACATING': 'ARRIVALS'
};

// Column body ID -> default phase when a strip is dropped there
var COLUMN_DEFAULT_PHASE = {
    'strips-pretaxi':  'PRE_TAXI',
    'strips-taxi':     'TAXI',
    'strips-runway':   'LINEUP',
    'strips-arrivals': 'APPROACH'
};

var _dropZonesInited = false;

// User-defined strip order within each column: { 'PRE_TAXI': ['REG1','REG2',...], ... }
var stripOrder = {};

// Column name -> column body element ID (reverse of COLUMN_DEFAULT_PHASE)
var COLUMN_BODY_ID = {
    'PRE_TAXI':  'strips-pretaxi',
    'TAXI':      'strips-taxi',
    'RUNWAY':    'strips-runway',
    'ARRIVALS':  'strips-arrivals'
};

// ---- Strip order helpers ----

function _ensureOrder(reg, column) {
    if (!stripOrder[column]) stripOrder[column] = [];
    if (stripOrder[column].indexOf(reg) === -1) stripOrder[column].push(reg);
}

function _moveOrder(dragReg, targetReg, insertBefore, targetColumn) {
    // Remove from all columns first
    Object.keys(stripOrder).forEach(function (col) {
        stripOrder[col] = stripOrder[col].filter(function (r) { return r !== dragReg; });
    });
    if (!stripOrder[targetColumn]) stripOrder[targetColumn] = [];
    var order = stripOrder[targetColumn];
    var idx = order.indexOf(targetReg);
    if (idx === -1) {
        order.push(dragReg);
    } else if (insertBefore) {
        order.splice(idx, 0, dragReg);
    } else {
        order.splice(idx + 1, 0, dragReg);
    }
}

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

// ---- Render strips into 4 columns ----

function renderFlightStrips(plans) {
    var containers = {
        PRE_TAXI:  document.getElementById('strips-pretaxi'),
        TAXI:      document.getElementById('strips-taxi'),
        RUNWAY:    document.getElementById('strips-runway'),
        ARRIVALS:  document.getElementById('strips-arrivals')
    };

    if (!containers.PRE_TAXI || !containers.TAXI || !containers.RUNWAY || !containers.ARRIVALS) return;

    containers.PRE_TAXI.innerHTML  = '';
    containers.TAXI.innerHTML      = '';
    containers.RUNWAY.innerHTML    = '';
    containers.ARRIVALS.innerHTML  = '';

    var counts = { PRE_TAXI: 0, TAXI: 0, RUNWAY: 0, ARRIVALS: 0 };

    if (!plans || plans.length === 0) {
        containers.PRE_TAXI.innerHTML  = emptyState();
        containers.ARRIVALS.innerHTML  = emptyState();
        updateColumnCounts(counts);
        return;
    }

    // Group plans by column and register in stripOrder
    var byColumn = { PRE_TAXI: [], TAXI: [], RUNWAY: [], ARRIVALS: [] };
    plans.forEach(function (plan) {
        var reg = plan.aircraft_registration;
        var isArrival = plan.destination_ICAO === currentICAO;
        if (!stripStates[reg]) {
            var defaultPhase = isArrival ? 'APPROACH' : 'PRE_TAXI';
            stripStates[reg] = { phase: defaultPhase, column: PHASE_COLUMN[defaultPhase] };
        }
        var column = getStripColumn(reg);
        _ensureOrder(reg, column);
        byColumn[column].push(plan);
    });

    // Sort each column by user-defined order, new arrivals go to the end
    ['PRE_TAXI', 'TAXI', 'RUNWAY', 'ARRIVALS'].forEach(function (col) {
        var order = stripOrder[col] || [];
        byColumn[col].sort(function (a, b) {
            var ai = order.indexOf(a.aircraft_registration);
            var bi = order.indexOf(b.aircraft_registration);
            if (ai === -1) ai = Infinity;
            if (bi === -1) bi = Infinity;
            return ai - bi;
        });
    });

    // Render each column in order
    ['PRE_TAXI', 'TAXI', 'RUNWAY', 'ARRIVALS'].forEach(function (col) {
        byColumn[col].forEach(function (plan) {
            var reg = plan.aircraft_registration;
            var isArrival = plan.destination_ICAO === currentICAO;
            var strip = createStripElement(plan, getStripPhase(reg), isArrival);
            containers[col].appendChild(strip);
            counts[col]++;
        });
    });

    if (counts.PRE_TAXI === 0) containers.PRE_TAXI.innerHTML = emptyState();
    if (counts.TAXI === 0)     containers.TAXI.innerHTML     = emptyState();
    if (counts.RUNWAY === 0)   containers.RUNWAY.innerHTML   = emptyState();
    if (counts.ARRIVALS === 0) containers.ARRIVALS.innerHTML = emptyState();

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
    el = document.getElementById('count-arrivals');
    if (el) el.textContent = counts.ARRIVALS;
}

function emptyState() {
    return '<div class="strips-empty">' +
        '<div class="strips-empty-icon">&#9992;</div>' +
        '<div>Empty</div></div>';
}

// ---- Format helpers ----

function formatFL(feet) {
    if (!feet) return '----';
    if (feet >= 10000) return 'F' + Math.round(feet / 100);
    return 'A' + String(Math.round(feet / 100)).padStart(3, '0');
}

function formatSpeed(knots) {
    if (!knots) return '-----';
    return 'N' + String(knots).padStart(4, '0');
}

function formatTime(hhmm) {
    if (!hhmm && hhmm !== 0) return '--:--';
    var s = String(Math.floor(hhmm)).padStart(4, '0');
    return s.slice(0, 2) + ':' + s.slice(2, 4);
}

// ---- Create Strip Card (IVAO paper-strip grid) ----

function createStripElement(plan, phase, isArrival) {
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

    var reg      = plan.aircraft_registration;
    var callsign = plan.callsign || reg;
    var isIFR    = plan.flight_rules !== 'V';
    var cfl      = formatFL(plan.cruising_altitude);
    var spd      = formatSpeed(plan.cruising_speed);
    var depTime  = formatTime(plan.departure_time);
    var acType   = escapeHtml(plan.aircraft_type || '----');
    var wtc      = escapeHtml(plan.wake_turbulence_category || '-');
    var squawk   = plan.squawk || generateSquawk(reg);
    var depIcao  = escapeHtml(plan.departure_ICAO || '----');
    var destIcao = escapeHtml(plan.destination_ICAO || '----');
    var route    = escapeHtml(plan.route || 'DCT');
    var remarks  = escapeHtml(plan.other_info || plan.remarks || '');

    function lbl(key) {
        return '<div class="fs-cell fs-label" data-key="' + key + '"></div>';
    }

    // Grid layout (4 rows × 5 cols, route spans rows 1-3 in col 5):
    // Row 1: dep | cfl  | callsign | dest    | route (span 3)
    // Row 2: I/V | type | label-1  | empty   |
    // Row 3: --- | spd  | label-2  | depTime |
    // Row 4: sqk | lbl3 | label-4  | label-5 | remarks
    strip.innerHTML =
        '<div class="fs-grid">' +
            // Row 1
            '<div class="fs-cell fs-dep">' + depIcao + '</div>' +
            '<div class="fs-cell fs-cfl">' + cfl + '</div>' +
            '<div class="fs-cell fs-call">' + escapeHtml(callsign) + '</div>' +
            '<div class="fs-cell fs-dest' + (isArrival ? ' fs-arr-dest' : '') + '">' + destIcao + '</div>' +
            '<div class="fs-cell fs-route">' + route + '</div>' +
            // Row 2
            '<div class="fs-cell fs-rules ' + (isIFR ? 'fs-ifr' : 'fs-vfr') + '">' + (isIFR ? 'I' : 'V') + '</div>' +
            '<div class="fs-cell fs-type">' + acType + '/' + wtc + '</div>' +
            lbl('lb1') +
            '<div class="fs-cell fs-emp"></div>' +
            // Row 3
            '<div class="fs-cell fs-emp"></div>' +
            '<div class="fs-cell fs-speed">' + spd + '</div>' +
            lbl('lb2') +
            '<div class="fs-cell fs-time">' + depTime + '</div>' +
            // Row 4
            '<div class="fs-cell fs-squawk">' + squawk + '</div>' +
            lbl('lb3') +
            lbl('lb4') +
            lbl('lb5') +
            '<div class="fs-cell fs-rmk">' + remarks + '</div>' +
        '</div>';

    // Load saved label content from localStorage
    strip.querySelectorAll('.fs-label').forEach(function (label) {
        var saved = localStorage.getItem('strip_lbl_' + reg + '_' + label.dataset.key);
        if (saved) label.textContent = saved;
        label.contentEditable = 'true';
    });

    // Labels: pause dragging while editing, save on blur
    strip.querySelectorAll('.fs-label').forEach(function (label) {
        label.addEventListener('mousedown', function (e) {
            strip.draggable = false;
            e.stopPropagation();
        });
        label.addEventListener('blur', function () {
            strip.draggable = true;
            localStorage.setItem('strip_lbl_' + reg + '_' + label.dataset.key, label.textContent.trim());
            // Reflect updated annotation on the SMR label immediately
            if (typeof updateSMRAircraft === 'function' && typeof flightPlans !== 'undefined') {
                updateSMRAircraft(flightPlans);
            }
        });
        label.addEventListener('keydown', function (e) {
            if (e.key === 'Enter') { e.preventDefault(); label.blur(); }
        });
    });

    // Intra-column reordering (and cross-column drop at specific position)
    strip.addEventListener('dragover', function (e) {
        e.preventDefault();
        e.stopPropagation();
        var rect = strip.getBoundingClientRect();
        var before = e.clientY < (rect.top + rect.height / 2);
        strip.dataset.dropInsert = before ? 'before' : 'after';
        strip.classList.toggle('drop-before', before);
        strip.classList.toggle('drop-after', !before);
    });

    strip.addEventListener('dragleave', function (e) {
        if (!strip.contains(e.relatedTarget)) {
            strip.classList.remove('drop-before', 'drop-after');
            delete strip.dataset.dropInsert;
        }
    });

    strip.addEventListener('drop', function (e) {
        e.preventDefault();
        e.stopPropagation();
        var insertBefore = strip.dataset.dropInsert !== 'after';
        strip.classList.remove('drop-before', 'drop-after');
        delete strip.dataset.dropInsert;

        var dragReg = e.dataTransfer.getData('text/plain');
        if (!dragReg || dragReg === reg) return;

        var dragColumn   = getStripColumn(dragReg);
        var targetColumn = getStripColumn(reg);

        _moveOrder(dragReg, reg, insertBefore, targetColumn);

        if (dragColumn === targetColumn) {
            // Same bay: move the DOM element directly, no full rerender
            var dragEl = null;
            document.querySelectorAll('.flight-strip').forEach(function (el) {
                if (el.dataset.registration === dragReg) dragEl = el;
            });
            if (dragEl) {
                strip.parentNode.insertBefore(dragEl, insertBefore ? strip : strip.nextSibling);
            }
        } else {
            // Different column: change phase then rerender
            var newPhase = COLUMN_DEFAULT_PHASE[COLUMN_BODY_ID[targetColumn]];
            if (newPhase) {
                setStripPhase(dragReg, newPhase);
                if (typeof rerenderStrips === 'function') rerenderStrips();
            }
        }
    });

    return strip;
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
            if (newPhase) {
                var targetColumn = PHASE_COLUMN[newPhase] || 'PRE_TAXI';
                // Remove from old column order and append to end of target column
                Object.keys(stripOrder).forEach(function (c) {
                    stripOrder[c] = stripOrder[c].filter(function (r) { return r !== reg; });
                });
                _ensureOrder(reg, targetColumn);
                if (getStripPhase(reg) !== newPhase) {
                    setStripPhase(reg, newPhase);
                    if (typeof rerenderStrips === 'function') rerenderStrips();
                }
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

export {
    loadStripStates,
    getStripPhase,
    getStripColumn,
    setStripPhase,
    renderFlightStrips,
    formatFL,
    formatSpeed,
    formatTime,
    generateSquawk,
    truncateRoute,
    sortFlightPlans,
};
