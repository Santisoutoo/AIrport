/* ============================================
   AIrport TWR — PTT + ASR Transcription
   Chat-style comms log + inline quick config
   ============================================ */

const ASR_URL = (window.HMI_CONFIG || {}).ASR_URL || '';
const ORCHESTRATOR_URL = (window.HMI_CONFIG || {}).ORCHESTRATOR_URL || '';
const CHAT_MAX_MSG = 50;

const ROBOT_SVG = `<svg viewBox="0 0 18 18" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
  <rect x="3" y="6" width="12" height="9" rx="2"/>
  <circle cx="6.5" cy="10.5" r="1" fill="currentColor" stroke="none"/>
  <circle cx="11.5" cy="10.5" r="1" fill="currentColor" stroke="none"/>
  <path d="M6.5 13h5"/>
  <path d="M9 6V3.5"/>
  <circle cx="9" cy="2.5" r="1" fill="currentColor" stroke="none"/>
  <path d="M3 9.5H1.5M16.5 9.5H15"/>
</svg>`;

const Ptt = (() => {

    let _pttKey = 'Space';
    let _deviceId = 'default';
    let _outputId = 'default';
    let _recording = false;
    const _sessionId = crypto.randomUUID();
    let _recorder = null;
    let _stream = null;
    let _chunks = [];
    let _messages = [];
    let _configOpen = false;
    let _capturingKey = false;
    let _captureHandler = null;

    // ------------------------------------------------------------------
    // Init
    // ------------------------------------------------------------------

    async function init() {
        try {
            const saved = localStorage.getItem('airport_asr_settings');
            if (saved) {
                const cfg = JSON.parse(saved);
                _pttKey = cfg.ptt_key || 'Space';
                _deviceId = cfg.input_device || 'default';
                _outputId = cfg.output_device || 'default';
            }
        } catch (_) { }

        _renderKeyBadge();
        _setState('idle');

        window.addEventListener('keydown', _onKeyDown);
        window.addEventListener('keyup', _onKeyUp);
        window.addEventListener('blur', _abortRecording);
    }

    // ------------------------------------------------------------------
    // PTT key handlers  (disabled while config is open or capturing)
    // ------------------------------------------------------------------

    function _onKeyDown(e) {
        if (_configOpen || _capturingKey) return;
        if (e.repeat || e.code !== _pttKey || _recording) return;
        e.preventDefault();
        _startRecording();
    }

    function _onKeyUp(e) {
        if (_configOpen || _capturingKey) return;
        if (e.code !== _pttKey || !_recording) return;
        e.preventDefault();
        _stopRecording();
    }

    // ------------------------------------------------------------------
    // Recording
    // ------------------------------------------------------------------

    async function _startRecording() {
        _recording = true;
        _chunks = [];
        _setState('recording');
        _showTyping();

        const constraints = {
            audio: (_deviceId && _deviceId !== 'default')
                ? { deviceId: { ideal: _deviceId } }
                : true,
        };

        try {
            _stream = await navigator.mediaDevices.getUserMedia(constraints);
            const mime = _pickMime();
            _recorder = new MediaRecorder(_stream, mime ? { mimeType: mime } : {});
            _recorder.ondataavailable = e => { if (e.data.size > 0) _chunks.push(e.data); };
            _recorder.onstop = _onRecordingDone;
            _recorder.start();
        } catch (err) {
            _recording = false;
            _hideTyping();
            _setState('error');
            _setStatusText('Mic error: ' + err.message);
        }
    }

    function _stopRecording() {
        _recording = false;
        if (_recorder && _recorder.state !== 'inactive') {
            _setState('processing');
            _recorder.stop();
            _stream.getTracks().forEach(t => t.stop());
        }
    }

    function _abortRecording() {
        if (!_recording) return;
        _recording = false;
        if (_recorder && _recorder.state !== 'inactive') _recorder.stop();
        if (_stream) _stream.getTracks().forEach(t => t.stop());
        _hideTyping();
        _setState('idle');
        _setStatusText('Presiona PTT para transmitir...');
    }

    function _pickMime() {
        const candidates = [
            'audio/webm;codecs=opus',
            'audio/webm',
            'audio/ogg;codecs=opus',
            'audio/ogg',
        ];
        return candidates.find(m => MediaRecorder.isTypeSupported(m)) || '';
    }

    // ------------------------------------------------------------------
    // Send to ASR
    // ------------------------------------------------------------------

    async function _onRecordingDone() {
        _hideTyping();

        if (_chunks.length === 0) {
            _setState('idle');
            _setStatusText('Presiona PTT para transmitir...');
            return;
        }

        const mime = _recorder.mimeType || 'audio/webm';
        const ext = mime.includes('ogg') ? 'ogg' : 'webm';
        const blob = new Blob(_chunks, { type: mime });
        const fd = new FormData();
        fd.append('audio', blob, `ptt.${ext}`);
        fd.append('session_id', _sessionId);

        try {
            const res = await fetch(`${getAsrUrl()}/transcribe`, { method: 'POST', body: fd });
            if (!res.ok) {
                let detail = 'HTTP ' + res.status;
                try { detail = (await res.json()).detail || detail; } catch (_) { }
                throw new Error(detail);
            }

            const data = await res.json();
            const text = (data.text || '').trim();
            if (text) {
                _pushMessage({ type: 'controller', text });
                _setStatusText('Esperando respuesta ATC...');

                // Dispatch to local orchestrator → agent reply
                _showTyping();
                try {
                    const orchRes = await fetch(`${ORCHESTRATOR_URL}/dispatch`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ session_id: _sessionId, message: text }),
                    });
                    if (orchRes.ok) {
                        const orch = await orchRes.json();
                        const reply = (orch.reply || '').trim();
                        const callsign = orch.aircraft_registration || orch.agent || 'ATC';
                        if (reply) _pushMessage({ type: 'agent', callsign, text: reply });
                    }
                } catch (orchErr) {
                    console.warn('[PTT] orchestrator unreachable:', orchErr.message);
                } finally {
                    _hideTyping();
                    _setStatusText('Presiona PTT para transmitir...');
                }
            } else {
                _setStatusText('(sin audio detectado)');
            }
        } catch (err) {
            _setStatusText('Error: ' + err.message);
        }

        _setState('idle');
    }

    // ------------------------------------------------------------------
    // Public: agent message
    // ------------------------------------------------------------------

    function addAgentMessage(callsign, text) {
        _pushMessage({ type: 'agent', callsign: callsign.toUpperCase(), text });
    }

    // ------------------------------------------------------------------
    // Inline quick config
    // ------------------------------------------------------------------

    async function toggleConfig() {
        _configOpen = !_configOpen;
        const panel = document.getElementById('comms-config');
        const gear = document.getElementById('comms-gear-btn');
        if (!panel) return;

        if (_configOpen) {
            // Abort any ongoing recording first
            _abortRecording();
            _stopPttCapture();

            panel.classList.remove('hidden');
            if (gear) gear.classList.add('active');

            // Populate selects with current values
            await _populateDevices();
            _syncConfigUI();
        } else {
            _stopPttCapture();
            panel.classList.add('hidden');
            if (gear) gear.classList.remove('active');
        }
    }

    async function _populateDevices() {
        // Request mic permission so labels are available
        try {
            const s = await navigator.mediaDevices.getUserMedia({ audio: true });
            s.getTracks().forEach(t => t.stop());
        } catch (_) { }

        const devices = await navigator.mediaDevices.enumerateDevices().catch(() => []);
        const micSel = document.getElementById('cc-mic');
        const outSel = document.getElementById('cc-out');
        if (!micSel || !outSel) return;

        micSel.innerHTML = '<option value="default">Default</option>';
        outSel.innerHTML = '<option value="default">Default</option>';

        devices.forEach(d => {
            const opt = document.createElement('option');
            opt.value = d.deviceId;
            opt.textContent = d.label || d.deviceId.slice(0, 28);
            if (d.kind === 'audioinput') micSel.appendChild(opt.cloneNode(true));
            if (d.kind === 'audiooutput') outSel.appendChild(opt);
        });
    }

    function _syncConfigUI() {
        const micSel = document.getElementById('cc-mic');
        const outSel = document.getElementById('cc-out');
        const keyEl = document.getElementById('cc-ptt-key');

        if (micSel && [...micSel.options].some(o => o.value === _deviceId))
            micSel.value = _deviceId;
        if (outSel && [...outSel.options].some(o => o.value === _outputId))
            outSel.value = _outputId;
        if (keyEl) keyEl.textContent = _pttKey;
    }

    // PTT key capture inside the config panel
    function capturePttKey() {
        if (_capturingKey) return;
        _capturingKey = true;

        const btn = document.getElementById('cc-ptt-key');
        if (btn) { btn.textContent = 'Pulsa tecla...'; btn.classList.add('capturing'); }

        _captureHandler = (e) => {
            e.preventDefault();
            e.stopPropagation();
            const key = e.code || e.key;
            if (btn) { btn.textContent = key; btn.classList.remove('capturing'); }
            _stopPttCapture();
        };

        window.addEventListener('keydown', _captureHandler, { capture: true, once: true });
    }

    function _stopPttCapture() {
        if (_captureHandler) {
            window.removeEventListener('keydown', _captureHandler, { capture: true });
            _captureHandler = null;
        }
        _capturingKey = false;
        const btn = document.getElementById('cc-ptt-key');
        if (btn) btn.classList.remove('capturing');
    }

    async function saveQuickConfig() {
        const micVal = document.getElementById('cc-mic')?.value || 'default';
        const outVal = document.getElementById('cc-out')?.value || 'default';
        const keyVal = document.getElementById('cc-ptt-key')?.textContent || _pttKey;

        // Fetch current full config to preserve AI fields
        let full = {};
        try {
            const r = await fetch(`${getAsrUrl()}/config`);
            if (r.ok) full = await r.json();
        } catch (_) { }

        const payload = Object.assign({}, full, {
            input_device: micVal,
            output_device: outVal,
            ptt_key: keyVal,
        });

        try {
            const res = await fetch(`${getAsrUrl()}/config`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });

            if (res.ok) {
                _pttKey = keyVal;
                _deviceId = micVal;
                _outputId = outVal;
                _renderKeyBadge();
                _setStatusText('Configuracion guardada');
                setTimeout(() => _setStatusText('Presiona PTT para transmitir...'), 2000);
            } else {
                _setStatusText('Error al guardar');
            }
        } catch (_) {
            _setStatusText('No se pudo conectar con el servicio ASR');
        }

        toggleConfig();
    }

    // ------------------------------------------------------------------
    // Message store & render
    // ------------------------------------------------------------------

    function _pushMessage(msg) {
        const now = new Date();
        msg.time = _utcTime(now);
        _messages.push(msg);
        if (_messages.length > CHAT_MAX_MSG) _messages.shift();
        _renderMessages();
    }

    function _renderMessages() {
        const log = document.getElementById('chat-log');
        if (!log) return;
        log.innerHTML = _messages.map(m => _buildBubble(m)).join('');
        log.scrollTop = log.scrollHeight;
    }

    function _buildBubble(m) {
        const safe = _esc(m.text);
        if (m.type === 'controller') {
            return `<div class="chat-msg chat-ctrl">` +
                `<div class="chat-bubble chat-bubble-ctrl">${safe}</div>` +
                `<div class="chat-meta"><span class="chat-sender">TWR</span><span class="chat-time">${m.time}</span></div>` +
                `</div>`;
        }
        const cs = _esc(m.callsign || '???');
        return `<div class="chat-msg chat-agent">` +
            `<div class="chat-agent-header">${ROBOT_SVG}<span class="chat-callsign">${cs}</span></div>` +
            `<div class="chat-bubble chat-bubble-agent">${safe}</div>` +
            `<div class="chat-meta"><span class="chat-time">${m.time}</span></div>` +
            `</div>`;
    }

    // ------------------------------------------------------------------
    // Typing indicator
    // ------------------------------------------------------------------

    function _showTyping() {
        const log = document.getElementById('chat-log');
        if (!log || document.getElementById('chat-typing')) return;
        const div = document.createElement('div');
        div.id = 'chat-typing';
        div.className = 'chat-msg chat-ctrl';
        div.innerHTML = `<div class="chat-bubble chat-bubble-ctrl chat-typing-bubble">` +
            `<span class="typing-dot"></span>` +
            `<span class="typing-dot"></span>` +
            `<span class="typing-dot"></span>` +
            `</div>`;
        log.appendChild(div);
        log.scrollTop = log.scrollHeight;
    }

    function _hideTyping() {
        const el = document.getElementById('chat-typing');
        if (el) el.remove();
    }

    // ------------------------------------------------------------------
    // UI helpers
    // ------------------------------------------------------------------

    function _setState(state) {
        const led = document.getElementById('ptt-led');
        const label = document.getElementById('ptt-state-label');
        if (!led || !label) return;
        led.className = 'ptt-led ptt-' + state;
        label.className = 'ptt-state-label ptt-label-' + state;
        const text = { idle: 'IDLE', recording: 'REC', processing: 'PROC', error: 'ERR' };
        label.textContent = text[state] || state.toUpperCase();
    }

    function _setStatusText(text) {
        const el = document.getElementById('ptt-status-text');
        if (el) el.textContent = text;
    }

    function _renderKeyBadge() {
        const el = document.getElementById('ptt-key-badge');
        if (el) el.textContent = _pttKey;
    }

    function _utcTime(d) {
        return String(d.getUTCHours()).padStart(2, '0') + ':' +
            String(d.getUTCMinutes()).padStart(2, '0') + ':' +
            String(d.getUTCSeconds()).padStart(2, '0') + 'Z';
    }

    function _esc(s) {
        return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    return { init, addAgentMessage, toggleConfig, capturePttKey, saveQuickConfig };

})();

document.addEventListener('DOMContentLoaded', () => Ptt.init());
