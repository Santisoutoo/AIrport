// atis.js -- ATIS modal controller

var AtisModal = (function () {

    // Track which fields were manually overridden by the controller
    var _manualFields = {};

    var _EDITABLE_FIELDS = ['atis-arrival-rwy', 'atis-dep-rwy', 'atis-atc-pos', 'atis-qfe', 'atis-remarks'];

    function open() {
        _manualFields = {};
        document.getElementById('atis-overlay').classList.add('active');
        _attachManualTracking();
        _autoGenerate();
    }

    function close() {
        document.getElementById('atis-overlay').classList.remove('active');
    }

    function onOverlayClick(e) {
        if (e.target === document.getElementById('atis-overlay')) {
            close();
        }
    }

    // Mark a field as "auto" (suggested by the system)
    function _setAuto(id, value) {
        var el = document.getElementById(id);
        if (!el) return;
        el.value = value != null ? String(value) : '';
        el.classList.add('atis-auto');
        el.classList.remove('atis-manual');
    }

    // Mark a field as "manual" (set by the controller)
    function _setManual(id) {
        var el = document.getElementById(id);
        if (!el) return;
        el.classList.add('atis-manual');
        el.classList.remove('atis-auto');
        _manualFields[id] = true;
    }

    // Attach change listeners once so edits are tracked
    function _attachManualTracking() {
        _EDITABLE_FIELDS.forEach(function (id) {
            var el = document.getElementById(id);
            if (!el || el._atisTracked) return;
            el.addEventListener('input', function () { _setManual(id); });
            el._atisTracked = true;
        });
    }

    // Call the generate endpoint with no params → weather service auto-selects runways/approach
    function _autoGenerate() {
        var sendBtn = document.querySelector('.atis-btn-send');
        sendBtn.disabled = true;
        sendBtn.textContent = 'Loading...';

        fetch('/api/v1/hmi/atis/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({}),
        })
            .then(function (r) { return r.ok ? r.json() : Promise.reject('HTTP ' + r.status); })
            .then(function (data) {
                _populate(data, true);
                sendBtn.disabled = false;
                sendBtn.textContent = 'SEND';
            })
            .catch(function (err) {
                console.warn('ATIS auto-generate failed, loading latest stored:', err);
                // Fallback: load the last stored ATIS
                fetch('/api/v1/hmi/atis')
                    .then(function (r) { return r.ok ? r.json() : null; })
                    .then(function (data) {
                        if (data) _populate(data, true);
                        sendBtn.disabled = false;
                        sendBtn.textContent = 'SEND';
                    })
                    .catch(function () {
                        sendBtn.disabled = false;
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

        // Only auto-fill fields not already manually overridden
        if (!_manualFields['atis-arrival-rwy'])
            mark('atis-arrival-rwy', data.arrival_runway || '');
        if (!_manualFields['atis-dep-rwy'])
            mark('atis-dep-rwy', data.departure_runway || '');
        if (!_manualFields['atis-qfe'])
            mark('atis-qfe', data.qnh_hpa || '');

        // FL and altitude are always auto (read-only display)
        var fl = data.transition_level ? data.transition_level.replace('FL', '') : '';
        _setAuto('atis-fl-val', fl);
        _setAuto('atis-alt-val', data.transition_altitude || '');

        // ATIS text output
        var textEl = document.getElementById('atis-text-output');
        if (textEl && data.atis_text) textEl.value = data.atis_text;

        document.getElementById('atis-active-chk').checked = true;
    }

    function send() {
        var btn = document.querySelector('.atis-btn-send');
        btn.disabled = true;
        btn.textContent = 'Sending...';

        // Build body: use current field values (manual or auto)
        var body = {
            arrival_runway: document.getElementById('atis-arrival-rwy').value.trim() || null,
            departure_runway: document.getElementById('atis-dep-rwy').value.trim() || null,
            approach: null,
        };

        fetch('/api/v1/hmi/atis/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        })
            .then(function (r) {
                if (!r.ok) throw new Error('HTTP ' + r.status);
                return r.json();
            })
            .then(function (data) {
                _populate(data, false);
                btn.textContent = 'SENT';
                setTimeout(function () {
                    btn.disabled = false;
                    btn.textContent = 'SEND';
                }, 2000);
            })
            .catch(function (err) {
                console.error('ATIS send error:', err);
                btn.disabled = false;
                btn.textContent = 'ERROR - Retry';
                setTimeout(function () { btn.textContent = 'SEND'; }, 3000);
            });
    }

    return { open: open, close: close, onOverlayClick: onOverlayClick, send: send };
})();
