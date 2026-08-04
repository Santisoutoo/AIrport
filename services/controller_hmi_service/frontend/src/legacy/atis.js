// atis.js -- ATIS modal controller

import { setILSForArrivalRunway } from './app.js';

var AtisModal = (function () {

    var _manualFields  = {};
    var _serverTimer   = null;
    var _lastData      = null;   // last full ATISResponse from server

    var _EDITABLE_FIELDS = [
        'atis-arrival-rwy', 'atis-dep-rwy', 'atis-atc-pos',
        'atis-qfe', 'atis-remarks', 'atis-metar-station'
    ];

    // ── public ───────────────────────────────────────────────────────────────

    function open() {
        _manualFields = {};
        document.getElementById('atis-overlay').classList.add('active');
        _attachManualTracking();
        _attachPreviewListeners();
        _autoGenerate();
    }

    function close() {
        document.getElementById('atis-overlay').classList.remove('active');
    }

    function onOverlayClick(e) {
        if (e.target === document.getElementById('atis-overlay')) close();
    }

    function send() {
        var btn = document.querySelector('.atis-btn-send');
        btn.disabled = true;
        btn.textContent = 'Sending...';

        fetch('/api/v1/hmi/atis/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(_buildBody(false)),
        })
        .then(function (r) {
            if (!r.ok) throw new Error('HTTP ' + r.status);
            return r.json();
        })
        .then(function (data) {
            _lastData = data;
            _populate(data, false);
            btn.textContent = 'SENT ✓';
            if (typeof setILSForArrivalRunway === 'function') {
                setILSForArrivalRunway(data.arrival_runway);
            }
            setTimeout(function () { btn.disabled = false; btn.textContent = 'SEND'; }, 2000);
        })
        .catch(function (err) {
            console.error('ATIS send error:', err);
            btn.disabled = false;
            btn.textContent = 'ERROR - Retry';
            setTimeout(function () { btn.textContent = 'SEND'; }, 3000);
        });
    }

    // ── private ──────────────────────────────────────────────────────────────

    function _setAuto(id, value) {
        var el = document.getElementById(id);
        if (!el) return;
        el.value = value != null ? String(value) : '';
        el.classList.add('atis-auto');
        el.classList.remove('atis-manual');
    }

    function _setManual(id) {
        var el = document.getElementById(id);
        if (!el) return;
        el.classList.add('atis-manual');
        el.classList.remove('atis-auto');
        _manualFields[id] = true;
    }

    function _attachManualTracking() {
        _EDITABLE_FIELDS.forEach(function (id) {
            var el = document.getElementById(id);
            if (!el || el._atisTracked) return;
            el.addEventListener('input', function () { _setManual(id); });
            el._atisTracked = true;
        });
    }

    function _attachPreviewListeners() {
        // TL / TA checkboxes → instant client-side render (no server call)
        ['atis-tl-chk', 'atis-ta-chk'].forEach(function (id) {
            var el = document.getElementById(id);
            if (!el || el._prevTracked) return;
            el.addEventListener('change', _renderLocal);
            el._prevTracked = true;
        });

        // ATC Position / QFE / Remarks → instant client-side render
        ['atis-atc-pos', 'atis-qfe', 'atis-remarks'].forEach(function (id) {
            var el = document.getElementById(id);
            if (!el || el._prevTracked) return;
            el.addEventListener('input', _renderLocal);
            el._prevTracked = true;
        });

        // Runway / METAR station → instant rough render + debounced server refresh
        ['atis-arrival-rwy', 'atis-dep-rwy', 'atis-metar-station'].forEach(function (id) {
            var el = document.getElementById(id);
            if (!el || el._prevTracked) return;
            el.addEventListener('input', function () {
                _renderLocal();
                _scheduleServerPreview();
            });
            el._prevTracked = true;
        });
    }

    function _scheduleServerPreview() {
        clearTimeout(_serverTimer);
        _serverTimer = setTimeout(function () {
            fetch('/api/v1/hmi/atis/generate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(_buildBody(true)),
            })
            .then(function (r) { return r.ok ? r.json() : null; })
            .then(function (data) {
                if (data) { _lastData = data; _renderLocal(); }
            })
            .catch(function () {});
        }, 700);
    }

    /**
     * Render the ATIS preview entirely client-side.
     * Starts from the last server-returned base text, strips conditional
     * sections (TL / TA / QFE / RMK) and re-injects them based on the
     * current UI state — giving instant feedback for checkbox clicks.
     */
    function _renderLocal() {
        if (!_lastData || !_lastData.atis_text) return;

        var tl      = document.getElementById('atis-tl-chk').checked;
        var ta      = document.getElementById('atis-ta-chk').checked;
        var qfe     = parseInt(document.getElementById('atis-qfe').value.trim()) || 0;
        var remarks = document.getElementById('atis-remarks').value.trim();

        // Strip ALL conditional lines so we can re-insert cleanly.
        // [^.]+ handles both old combined format ("Transition level FL70, transition altitude 6000 feet.")
        // and new separate format ("Transition level FL70.")
        var text = _lastData.atis_text
            .replace(/ Transition level [^.]+\./g, '')
            .replace(/ Transition altitude [^.]+\./g, '')
            .replace(/ QFE [^.]+\./g, '')
            .replace(/ RMK .+$/, '');

        // Build insert block (goes right before "Information X recorded")
        var ins = '';
        if (qfe > 0)
            ins += ' QFE ' + qfe + ' hectopascals.';
        if (tl && _lastData.transition_level)
            ins += ' Transition level ' + _lastData.transition_level + '.';
        if (ta && _lastData.transition_altitude)
            ins += ' Transition altitude ' + _lastData.transition_altitude + ' feet.';

        if (ins) {
            // Insert before the closing "Information X recorded at …" sentence
            text = text.replace(
                /(Information [A-Z]+ recorded)/,
                ins.replace(/^ /, '') + ' $1'
            );
        }

        if (remarks) text += ' RMK ' + remarks;

        // Replace airport name at the start with ATC Position if provided
        var atcPos = document.getElementById('atis-atc-pos').value.trim();
        if (atcPos) {
            text = text.replace(/^.*? information ([A-Z]+)\./, atcPos + ' information $1.');
        }

        document.getElementById('atis-text-output').value = text;
    }

    function _buildBody(isPreview) {
        return {
            arrival_runway:  document.getElementById('atis-arrival-rwy').value.trim() || null,
            departure_runway: document.getElementById('atis-dep-rwy').value.trim() || null,
            approach: null,
            qfe:      parseInt(document.getElementById('atis-qfe').value.trim()) || null,
            include_tl: document.getElementById('atis-tl-chk').checked,
            include_ta: document.getElementById('atis-ta-chk').checked,
            remarks:  document.getElementById('atis-remarks').value.trim() || null,
            metar_station: document.getElementById('atis-metar-station').value.trim() || null,
            preview:  isPreview === true,
        };
    }

    function _autoGenerate() {
        var sendBtn = document.querySelector('.atis-btn-send');
        sendBtn.disabled  = true;
        sendBtn.textContent = 'Loading...';

        fetch('/api/v1/hmi/atis/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ preview: false }),
        })
        .then(function (r) { return r.ok ? r.json() : Promise.reject('HTTP ' + r.status); })
        .then(function (data) {
            _lastData = data;
            _populate(data, true);
            sendBtn.disabled  = false;
            sendBtn.textContent = 'SEND';
        })
        .catch(function (err) {
            console.warn('ATIS auto-generate failed, loading latest stored:', err);
            fetch('/api/v1/hmi/atis')
                .then(function (r) { return r.ok ? r.json() : null; })
                .then(function (data) {
                    if (data) { _lastData = data; _populate(data, true); }
                    sendBtn.disabled  = false;
                    sendBtn.textContent = 'SEND';
                })
                .catch(function () {
                    sendBtn.disabled  = false;
                    sendBtn.textContent = 'SEND';
                });
        });
    }

    function _populate(data, isAuto) {
        var mark = isAuto ? _setAuto : function (id, val) {
            var el = document.getElementById(id);
            if (el) el.value = val != null ? String(val) : '';
        };

        if (data.atis_letter) mark('atis-letter-field', data.atis_letter);

        if (!_manualFields['atis-arrival-rwy'])
            mark('atis-arrival-rwy', data.arrival_runway || '');
        if (!_manualFields['atis-dep-rwy'])
            mark('atis-dep-rwy', data.departure_runway || '');
        if (!_manualFields['atis-metar-station'])
            mark('atis-metar-station', data.icao_code || '');

        var fl = data.transition_level ? data.transition_level.replace('FL', '') : '';
        _setAuto('atis-fl-val', fl);
        _setAuto('atis-alt-val', data.transition_altitude || '');

        // Default both checked on first load
        if (isAuto) {
            document.getElementById('atis-tl-chk').checked = true;
            document.getElementById('atis-ta-chk').checked = true;
        }

        document.getElementById('atis-active-chk').checked = true;

        // Render preview with current UI overrides applied
        _renderLocal();
    }

    return { open: open, close: close, onOverlayClick: onOverlayClick, send: send };
})();

// Bridge for the inline on*= handlers in index.html (removed in Phase 3).
window.AtisModal = AtisModal;
export { AtisModal };
