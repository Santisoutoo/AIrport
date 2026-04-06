(function () {
    'use strict';

    var STORAGE_KEY = 'hmi-panel-sizes';
    var HANDLE_PX   = 5;
    var MINS = { leftW: 500, dashH: 60, bottomH: 80, commsH: 120 };
    var STRIPS_MIN  = 100;

    var twrLayout, leftPanel, rightPanel, dashEl, bottomEl, commsEl;
    var STATE = { leftW: 0, dashH: 0, bottomH: 0, commsH: 0 };

    function clamp(v, lo, hi) { return Math.min(Math.max(v, lo), hi); }

    function maxLeftW()   { return twrLayout.offsetWidth - 280 - HANDLE_PX; }
    function maxDashH()   { return twrLayout.offsetHeight - STATE.bottomH - STRIPS_MIN - HANDLE_PX * 2; }
    function maxBottomH() { return twrLayout.offsetHeight - STATE.dashH - STRIPS_MIN - HANDLE_PX * 2; }
    function maxCommsH()  { return twrLayout.offsetHeight - 80; }

    function clampState() {
        STATE.leftW   = clamp(STATE.leftW,   MINS.leftW,   maxLeftW());
        STATE.dashH   = clamp(STATE.dashH,   MINS.dashH,   maxDashH());
        STATE.bottomH = clamp(STATE.bottomH, MINS.bottomH, maxBottomH());
        STATE.commsH  = clamp(STATE.commsH,  MINS.commsH,  maxCommsH());
    }

    function applyLayout() {
        leftPanel.style.flex     = '0 0 ' + STATE.leftW + 'px';
        rightPanel.style.flex    = '1 1 0';
        rightPanel.style.minWidth = '280px';

        dashEl.style.height     = STATE.dashH + 'px';
        dashEl.style.flexShrink = '0';
        dashEl.style.flexGrow   = '0';
        dashEl.style.overflow   = 'hidden';

        bottomEl.style.height     = STATE.bottomH + 'px';
        bottomEl.style.flexShrink = '0';
        bottomEl.style.flexGrow   = '0';
        bottomEl.style.overflow   = 'hidden';

        commsEl.style.height = STATE.commsH + 'px';
    }

    function save() {
        try { localStorage.setItem(STORAGE_KEY, JSON.stringify(STATE)); } catch (e) {}
    }

    function load() {
        try {
            var p = JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null');
            if (p && ['leftW', 'dashH', 'bottomH', 'commsH'].every(function (k) {
                return typeof p[k] === 'number' && isFinite(p[k]);
            })) {
                STATE = p;
                return true;
            }
        } catch (e) {}
        return false;
    }

    function wireHandle(id, vertical, getSnap, onDelta) {
        var el = document.getElementById(id);
        if (!el) return;
        el.addEventListener('mousedown', function (e) {
            if (e.button !== 0) return;
            e.preventDefault();
            var x0 = e.clientX, y0 = e.clientY, snap = getSnap();
            el.classList.add('resize-handle--dragging');
            document.body.style.cursor = vertical ? 'col-resize' : 'row-resize';
            document.body.style.userSelect = 'none';

            function onMove(ev) {
                onDelta(snap, ev.clientX - x0, ev.clientY - y0);
                applyLayout();
            }
            function onUp() {
                el.classList.remove('resize-handle--dragging');
                document.body.style.cursor = '';
                document.body.style.userSelect = '';
                window.removeEventListener('mousemove', onMove);
                window.removeEventListener('mouseup', onUp);
                clampState();
                applyLayout();
                save();
            }
            window.addEventListener('mousemove', onMove);
            window.addEventListener('mouseup', onUp);
        });
    }

    function wireHandles() {
        // Vertical splitter: left vs right panel (drag right = left panel wider)
        wireHandle('rh-lr', true,
            function () { return STATE.leftW; },
            function (s, dx) {
                STATE.leftW = clamp(s + dx, MINS.leftW, maxLeftW());
            });

        // Horizontal splitter: below dashboard (drag down = dashboard taller)
        wireHandle('rh-dash', false,
            function () { return STATE.dashH; },
            function (s, _dx, dy) {
                STATE.dashH = clamp(s + dy, MINS.dashH, maxDashH());
            });

        // Horizontal splitter: above bottom-bar (drag up = bottom-bar taller)
        wireHandle('rh-wind', false,
            function () { return STATE.bottomH; },
            function (s, _dx, dy) {
                STATE.bottomH = clamp(s - dy, MINS.bottomH, maxBottomH());
            });

        // Horizontal splitter: above comms panel (drag up = comms taller)
        wireHandle('rh-comms', false,
            function () { return STATE.commsH; },
            function (s, _dx, dy) {
                STATE.commsH = clamp(s - dy, MINS.commsH, maxCommsH());
            });
    }

    function init() {
        twrLayout  = document.getElementById('twr-layout');
        leftPanel  = document.getElementById('left-panel');
        rightPanel = document.getElementById('right-panel');
        dashEl     = document.getElementById('dashboard-superior');
        bottomEl   = document.getElementById('bottom-bar');
        commsEl    = document.getElementById('comms-panel');

        if (!twrLayout || !leftPanel || !rightPanel) return;

        if (!load()) {
            STATE.leftW   = leftPanel.offsetWidth;
            STATE.dashH   = dashEl.offsetHeight;
            STATE.bottomH = bottomEl.offsetHeight;
            STATE.commsH  = commsEl.offsetHeight;
        }

        clampState();
        applyLayout();
        wireHandles();

        window.addEventListener('resize', function () {
            clampState();
            applyLayout();
        });
    }

    document.addEventListener('DOMContentLoaded', init);
})();
