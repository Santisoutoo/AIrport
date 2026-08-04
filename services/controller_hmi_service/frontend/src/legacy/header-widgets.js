// header-widgets.js -- Stopwatch and end-session controls in the HMI header.
// Recreated from the lost inline script (issue #59, Phase 0); split into
// proper modules during Phase 3.

import { Debrief } from './debrief';
import { Ptt } from './ptt.js';

document.addEventListener('DOMContentLoaded', function () {
    // --- Stopwatch ---
    var swSeconds = 0;
    var swTimer = null;
    var swDisplay = document.getElementById('sw-display');
    var swWidget = document.getElementById('stopwatch-widget');
    var swToggle = document.getElementById('sw-toggle');
    var swReset = document.getElementById('sw-reset');
    if (!swDisplay || !swWidget || !swToggle || !swReset) return;
    var swDot = swWidget.querySelector('.sw-dot');

    function swRender() {
        var m = String(Math.floor(swSeconds / 60)).padStart(2, '0');
        var s = String(swSeconds % 60).padStart(2, '0');
        swDisplay.textContent = m + ':' + s;
    }

    swToggle.addEventListener('click', function () {
        if (swTimer) {
            clearInterval(swTimer);
            swTimer = null;
            swWidget.classList.remove('sw-active');
            swDot.classList.remove('sw-running');
            swToggle.innerHTML = '&#9654;';
        } else {
            swTimer = setInterval(function () { swSeconds++; swRender(); }, 1000);
            swWidget.classList.add('sw-active');
            swDot.classList.add('sw-running');
            swToggle.innerHTML = '&#10074;&#10074;';
        }
    });

    swReset.addEventListener('click', function () {
        swSeconds = 0;
        swRender();
    });

    // --- End session: stop backend session, then instructor debrief ---
    var endBtn = document.getElementById('end-session-btn');
    if (!endBtn) return;
    endBtn.addEventListener('click', function () {
        endBtn.disabled = true;
        fetch('/api/v1/plugin/session/stop', { method: 'POST' })
            .catch(function () { /* stop is best-effort */ })
            .then(function () {
                var icao = document.getElementById('airport-badge').textContent.trim();
                return Debrief.openAndGenerate(Ptt.getSessionId(), icao === '----' ? '' : icao);
            })
            .then(function () { return Debrief.waitClose(); })
            .then(function () { window.location.href = '/setup'; })
            .catch(function () { endBtn.disabled = false; });
    });
});
