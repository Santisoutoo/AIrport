/* ============================================
   AIrport TWR — PTT + ASR Transcription
   Chat-style comms log + inline quick config
   ============================================ */

import { dispatchOrchestrator, transcribe } from '../api/client';
import { getAsrSettings, setAsrSettings } from '../lib/storage';

const CHAT_MAX_MSG = 200;

const ROBOT_SVG = `<svg viewBox="0 0 18 18" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
  <rect x="3" y="6" width="12" height="9" rx="2"/>
  <circle cx="6.5" cy="10.5" r="1" fill="currentColor" stroke="none"/>
  <circle cx="11.5" cy="10.5" r="1" fill="currentColor" stroke="none"/>
  <path d="M6.5 13h5"/>
  <path d="M9 6V3.5"/>
  <circle cx="9" cy="2.5" r="1" fill="currentColor" stroke="none"/>
  <path d="M3 9.5H1.5M16.5 9.5H15"/>
</svg>`;

interface ChatMessage {
  type: 'controller' | 'agent';
  text: string;
  callsign?: string;
  dep?: string | null;
  time?: string;
}

type PttState = 'idle' | 'recording' | 'processing' | 'error';

const Ptt = (() => {
  let _pttKey = 'Space';
  let _deviceId = 'default';
  let _outputId = 'default';
  let _recording = false;
  const _sessionId = crypto.randomUUID();
  let _recorder: MediaRecorder | null = null;
  let _stream: MediaStream | null = null;
  let _chunks: Blob[] = [];
  const _messages: ChatMessage[] = [];
  let _lastDep: string | null = null;
  let _activeFilter = 'all';
  let _configOpen = false;
  let _capturingKey = false;
  let _captureHandler: ((e: KeyboardEvent) => void) | null = null;

  // ------------------------------------------------------------------
  // Init
  // ------------------------------------------------------------------

  async function init(): Promise<void> {
    const cfg = getAsrSettings();
    _pttKey = cfg.ptt_key || 'Space';
    _deviceId = cfg.input_device || 'default';
    _outputId = cfg.output_device || 'default';

    _renderKeyBadge();
    _setState('idle');

    window.addEventListener('keydown', _onKeyDown);
    window.addEventListener('keyup', _onKeyUp);
    window.addEventListener('blur', _abortRecording);

    document.querySelectorAll<HTMLElement>('.chat-filter-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        _activeFilter = btn.dataset.filter ?? 'all';
        document
          .querySelectorAll('.chat-filter-btn')
          .forEach((b) => b.classList.remove('active'));
        btn.classList.add('active');
        _renderMessages();
      });
    });
  }

  // ------------------------------------------------------------------
  // PTT key handlers  (disabled while config is open or capturing)
  // ------------------------------------------------------------------

  function _onKeyDown(e: KeyboardEvent): void {
    if (_configOpen || _capturingKey) return;
    if (e.repeat || e.code !== _pttKey || _recording) return;
    e.preventDefault();
    _startRecording();
  }

  function _onKeyUp(e: KeyboardEvent): void {
    if (_configOpen || _capturingKey) return;
    if (e.code !== _pttKey || !_recording) return;
    e.preventDefault();
    _stopRecording();
  }

  // ------------------------------------------------------------------
  // Recording
  // ------------------------------------------------------------------

  async function _startRecording(): Promise<void> {
    _recording = true;
    _chunks = [];
    _setState('recording');
    _showTyping('ctrl');

    const constraints: MediaStreamConstraints = {
      audio: _deviceId && _deviceId !== 'default' ? { deviceId: { ideal: _deviceId } } : true,
    };

    try {
      _stream = await navigator.mediaDevices.getUserMedia(constraints);
      const mime = _pickMime();
      _recorder = new MediaRecorder(_stream, mime ? { mimeType: mime } : {});
      _recorder.ondataavailable = (e: BlobEvent) => {
        if (e.data.size > 0) _chunks.push(e.data);
      };
      _recorder.onstop = _onRecordingDone;
      _recorder.start();
    } catch (err) {
      _recording = false;
      _hideTyping();
      _setState('error');
      _setStatusText('Mic error: ' + (err instanceof Error ? err.message : String(err)));
    }
  }

  function _stopRecording(): void {
    _recording = false;
    if (_recorder && _recorder.state !== 'inactive') {
      _setState('processing');
      _recorder.stop();
      _stream?.getTracks().forEach((t) => t.stop());
    }
  }

  function _abortRecording(): void {
    if (!_recording) return;
    _recording = false;
    if (_recorder && _recorder.state !== 'inactive') _recorder.stop();
    if (_stream) _stream.getTracks().forEach((t) => t.stop());
    _hideTyping();
    _setState('idle');
    _setStatusText('Presiona PTT para transmitir...');
  }

  function _pickMime(): string {
    const candidates = [
      'audio/webm;codecs=opus',
      'audio/webm',
      'audio/ogg;codecs=opus',
      'audio/ogg',
    ];
    return candidates.find((m) => MediaRecorder.isTypeSupported(m)) || '';
  }

  // ------------------------------------------------------------------
  // Send to ASR
  // ------------------------------------------------------------------

  async function _onRecordingDone(): Promise<void> {
    _hideTyping();

    if (_chunks.length === 0) {
      _setState('idle');
      _setStatusText('Presiona PTT para transmitir...');
      return;
    }

    const mime = _recorder?.mimeType || 'audio/webm';
    const ext = mime.includes('ogg') ? 'ogg' : 'webm';
    const blob = new Blob(_chunks, { type: mime });

    try {
      const data = await transcribe(blob, `ptt.${ext}`, _sessionId);
      const text = (data.text || '').trim();
      if (text) {
        _pushMessage({ type: 'controller', text });
        const ctrlIdx = _messages.length - 1;
        _setStatusText('Esperando respuesta ATC...');

        // Dispatch to local orchestrator → agent reply
        _showTyping('agent', _lastDep);
        try {
          const orch = await dispatchOrchestrator(_sessionId, text);
          const reply = (orch.reply || '').trim();
          const callsign = orch.callsign || orch.aircraft_registration || orch.agent || 'ATC';
          const dep = orch.agent || null;
          if (dep && ctrlIdx >= 0 && _messages[ctrlIdx]) _messages[ctrlIdx].dep = dep;
          if (reply) _pushMessage({ type: 'agent', callsign, dep, text: reply });
        } catch (orchErr) {
          const msg = orchErr instanceof Error ? orchErr.message : String(orchErr);
          _setStatusText('Error ATC: ' + msg);
          console.error('[PTT] orchestrator error:', msg);
        } finally {
          _hideTyping();
          _setStatusText('Presiona PTT para transmitir...');
        }
      } else {
        _setStatusText('(sin audio detectado)');
      }
    } catch (err) {
      _setStatusText('Error: ' + (err instanceof Error ? err.message : String(err)));
    }

    _setState('idle');
  }

  // ------------------------------------------------------------------
  // Public: agent message
  // ------------------------------------------------------------------

  function addAgentMessage(callsign: string, text: string): void {
    _pushMessage({ type: 'agent', callsign: callsign.toUpperCase(), text });
  }

  // ------------------------------------------------------------------
  // Inline quick config
  // ------------------------------------------------------------------

  async function toggleConfig(): Promise<void> {
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

  async function _populateDevices(): Promise<void> {
    // Request mic permission so labels are available
    try {
      const s = await navigator.mediaDevices.getUserMedia({ audio: true });
      s.getTracks().forEach((t) => t.stop());
    } catch {
      /* no mic permission */
    }

    const devices = await navigator.mediaDevices.enumerateDevices().catch(() => []);
    const micSel = document.getElementById('cc-mic') as HTMLSelectElement | null;
    const outSel = document.getElementById('cc-out') as HTMLSelectElement | null;
    if (!micSel || !outSel) return;

    micSel.innerHTML = '<option value="default">Default</option>';
    outSel.innerHTML = '<option value="default">Default</option>';

    devices.forEach((d) => {
      const opt = document.createElement('option');
      opt.value = d.deviceId;
      opt.textContent = d.label || d.deviceId.slice(0, 28);
      if (d.kind === 'audioinput') micSel.appendChild(opt.cloneNode(true));
      if (d.kind === 'audiooutput') outSel.appendChild(opt);
    });
  }

  function _syncConfigUI(): void {
    const micSel = document.getElementById('cc-mic') as HTMLSelectElement | null;
    const outSel = document.getElementById('cc-out') as HTMLSelectElement | null;
    const keyEl = document.getElementById('cc-ptt-key');

    if (micSel && [...micSel.options].some((o) => o.value === _deviceId)) micSel.value = _deviceId;
    if (outSel && [...outSel.options].some((o) => o.value === _outputId)) outSel.value = _outputId;
    if (keyEl) keyEl.textContent = _pttKey;
  }

  // PTT key capture inside the config panel
  function capturePttKey(): void {
    if (_capturingKey) return;
    _capturingKey = true;

    const btn = document.getElementById('cc-ptt-key');
    if (btn) {
      btn.textContent = 'Pulsa tecla...';
      btn.classList.add('capturing');
    }

    _captureHandler = (e: KeyboardEvent) => {
      e.preventDefault();
      e.stopPropagation();
      const key = e.code || e.key;
      if (btn) {
        btn.textContent = key;
        btn.classList.remove('capturing');
      }
      _stopPttCapture();
    };

    window.addEventListener('keydown', _captureHandler, { capture: true, once: true });
  }

  function _stopPttCapture(): void {
    if (_captureHandler) {
      window.removeEventListener('keydown', _captureHandler, { capture: true });
      _captureHandler = null;
    }
    _capturingKey = false;
    const btn = document.getElementById('cc-ptt-key');
    if (btn) btn.classList.remove('capturing');
  }

  function saveQuickConfig(): void {
    const micVal = (document.getElementById('cc-mic') as HTMLSelectElement | null)?.value || 'default';
    const outVal = (document.getElementById('cc-out') as HTMLSelectElement | null)?.value || 'default';
    const keyVal = document.getElementById('cc-ptt-key')?.textContent || _pttKey;

    _pttKey = keyVal;
    _deviceId = micVal;
    _outputId = outVal;

    setAsrSettings({
      ...getAsrSettings(),
      ptt_key: _pttKey,
      input_device: _deviceId,
      output_device: _outputId,
    });

    _renderKeyBadge();
    _setStatusText('Configuracion guardada');
    setTimeout(() => _setStatusText('Presiona PTT para transmitir...'), 2000);

    toggleConfig();
  }

  // ------------------------------------------------------------------
  // Message store & render
  // ------------------------------------------------------------------

  function _pushMessage(msg: ChatMessage): void {
    const now = new Date();
    msg.time = _utcTime(now);
    _messages.push(msg);
    if (msg.type === 'agent' && msg.dep) _lastDep = msg.dep;
    if (_messages.length > CHAT_MAX_MSG) _messages.shift();
    _renderMessages();
  }

  function _renderMessages(): void {
    const log = document.getElementById('chat-log');
    if (!log) return;
    const visible =
      _activeFilter === 'all' ? _messages : _messages.filter((m) => m.dep === _activeFilter);
    log.innerHTML = visible.map((m) => _buildBubble(m)).join('');
    log.scrollTop = log.scrollHeight;
  }

  function _buildBubble(m: ChatMessage): string {
    const safe = _esc(m.text);
    if (m.type === 'controller') {
      return (
        `<div class="chat-msg chat-ctrl">` +
        `<div class="chat-bubble chat-bubble-ctrl">${safe}</div>` +
        `<div class="chat-meta"><span class="chat-sender">TWR</span><span class="chat-time">${m.time}</span></div>` +
        `</div>`
      );
    }
    const cs = _esc(m.callsign || '???');
    const depCls = m.dep ? ` chat-dep-${m.dep.toLowerCase()}` : '';
    return (
      `<div class="chat-msg chat-agent${depCls}">` +
      `<div class="chat-agent-header">${ROBOT_SVG}<span class="chat-callsign">${cs}</span></div>` +
      `<div class="chat-bubble chat-bubble-agent">${safe}</div>` +
      `<div class="chat-meta"><span class="chat-time">${m.time}</span></div>` +
      `</div>`
    );
  }

  // ------------------------------------------------------------------
  // Typing indicator
  // ------------------------------------------------------------------

  function _showTyping(side: 'ctrl' | 'agent', dep?: string | null): void {
    const log = document.getElementById('chat-log');
    if (!log || document.getElementById('chat-typing')) return;
    const div = document.createElement('div');
    div.id = 'chat-typing';
    const isAgent = side === 'agent';
    const depCls = isAgent && dep ? ` chat-dep-${dep.toLowerCase()}` : '';
    div.className = 'chat-msg ' + (isAgent ? 'chat-agent' : 'chat-ctrl') + depCls;
    const bubbleClass = isAgent ? 'chat-bubble-agent' : 'chat-bubble-ctrl';
    div.innerHTML =
      `<div class="chat-bubble ${bubbleClass} chat-typing-bubble">` +
      `<span class="typing-dot"></span>` +
      `<span class="typing-dot"></span>` +
      `<span class="typing-dot"></span>` +
      `</div>`;
    log.appendChild(div);
    log.scrollTop = log.scrollHeight;
  }

  function _hideTyping(): void {
    const el = document.getElementById('chat-typing');
    if (el) el.remove();
  }

  // ------------------------------------------------------------------
  // UI helpers
  // ------------------------------------------------------------------

  function _setState(state: PttState): void {
    const led = document.getElementById('ptt-led');
    const label = document.getElementById('ptt-state-label');
    if (!led || !label) return;
    led.className = 'ptt-led ptt-' + state;
    label.className = 'ptt-state-label ptt-label-' + state;
    const text: Record<PttState, string> = {
      idle: 'IDLE',
      recording: 'REC',
      processing: 'PROC',
      error: 'ERR',
    };
    label.textContent = text[state] || state.toUpperCase();
  }

  function _setStatusText(text: string): void {
    const el = document.getElementById('ptt-status-text');
    if (el) el.textContent = text;
  }

  function _renderKeyBadge(): void {
    const el = document.getElementById('ptt-key-badge');
    if (el) el.textContent = _pttKey;
  }

  function _utcTime(d: Date): string {
    return (
      String(d.getUTCHours()).padStart(2, '0') +
      ':' +
      String(d.getUTCMinutes()).padStart(2, '0') +
      ':' +
      String(d.getUTCSeconds()).padStart(2, '0') +
      'Z'
    );
  }

  function _esc(s: string): string {
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function getSessionId(): string {
    return _sessionId;
  }

  return { init, addAgentMessage, toggleConfig, capturePttKey, saveQuickConfig, getSessionId };
})();

document.addEventListener('DOMContentLoaded', () => Ptt.init());

// Bridge for the inline on*= handlers in index.html (removed in Phase 3).
window.Ptt = Ptt;
export { Ptt };
