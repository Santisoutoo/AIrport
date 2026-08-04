// atis.ts — ATIS modal controller.

import { generateAtis, getAtis } from '../api/client';
import type { AtisRequest, AtisResponse } from '../types/api';
import { setILSForArrivalRunway } from './app.js';

type TrackedElement = HTMLElement & { _atisTracked?: boolean; _prevTracked?: boolean };

const AtisModal = (() => {
  let _manualFields: Record<string, boolean> = {};
  let _serverTimer: ReturnType<typeof setTimeout> | undefined;
  let _lastData: AtisResponse | null = null; // last full ATISResponse from server

  const _EDITABLE_FIELDS = [
    'atis-arrival-rwy',
    'atis-dep-rwy',
    'atis-atc-pos',
    'atis-qfe',
    'atis-remarks',
    'atis-metar-station',
  ];

  function _el(id: string): HTMLInputElement | null {
    return document.getElementById(id) as HTMLInputElement | null;
  }

  function _value(id: string): string {
    return _el(id)?.value.trim() ?? '';
  }

  function _checked(id: string): boolean {
    return _el(id)?.checked ?? false;
  }

  // ── public ───────────────────────────────────────────────────────────────

  function open(): void {
    _manualFields = {};
    document.getElementById('atis-overlay')?.classList.add('active');
    _attachManualTracking();
    _attachPreviewListeners();
    _autoGenerate();
  }

  function close(): void {
    document.getElementById('atis-overlay')?.classList.remove('active');
  }

  function onOverlayClick(e: MouseEvent): void {
    if (e.target === document.getElementById('atis-overlay')) close();
  }

  function send(): void {
    const btn = document.querySelector<HTMLButtonElement>('.atis-btn-send');
    if (!btn) return;
    btn.disabled = true;
    btn.textContent = 'Sending...';

    generateAtis(_buildBody(false))
      .then((data) => {
        _lastData = data;
        _populate(data, false);
        btn.textContent = 'SENT ✓';
        setILSForArrivalRunway(data.arrival_runway ?? null);
        setTimeout(() => {
          btn.disabled = false;
          btn.textContent = 'SEND';
        }, 2000);
      })
      .catch((err: unknown) => {
        console.error('ATIS send error:', err);
        btn.disabled = false;
        btn.textContent = 'ERROR - Retry';
        setTimeout(() => {
          btn.textContent = 'SEND';
        }, 3000);
      });
  }

  // ── private ──────────────────────────────────────────────────────────────

  function _setAuto(id: string, value: unknown): void {
    const el = _el(id);
    if (!el) return;
    el.value = value != null ? String(value) : '';
    el.classList.add('atis-auto');
    el.classList.remove('atis-manual');
  }

  function _setManual(id: string): void {
    const el = _el(id);
    if (!el) return;
    el.classList.add('atis-manual');
    el.classList.remove('atis-auto');
    _manualFields[id] = true;
  }

  function _attachManualTracking(): void {
    _EDITABLE_FIELDS.forEach((id) => {
      const el = _el(id) as TrackedElement | null;
      if (!el || el._atisTracked) return;
      el.addEventListener('input', () => _setManual(id));
      el._atisTracked = true;
    });
  }

  function _attachPreviewListeners(): void {
    // TL / TA checkboxes → instant client-side render (no server call)
    ['atis-tl-chk', 'atis-ta-chk'].forEach((id) => {
      const el = _el(id) as TrackedElement | null;
      if (!el || el._prevTracked) return;
      el.addEventListener('change', _renderLocal);
      el._prevTracked = true;
    });

    // ATC Position / QFE / Remarks → instant client-side render
    ['atis-atc-pos', 'atis-qfe', 'atis-remarks'].forEach((id) => {
      const el = _el(id) as TrackedElement | null;
      if (!el || el._prevTracked) return;
      el.addEventListener('input', _renderLocal);
      el._prevTracked = true;
    });

    // Runway / METAR station → instant rough render + debounced server refresh
    ['atis-arrival-rwy', 'atis-dep-rwy', 'atis-metar-station'].forEach((id) => {
      const el = _el(id) as TrackedElement | null;
      if (!el || el._prevTracked) return;
      el.addEventListener('input', () => {
        _renderLocal();
        _scheduleServerPreview();
      });
      el._prevTracked = true;
    });
  }

  function _scheduleServerPreview(): void {
    clearTimeout(_serverTimer);
    _serverTimer = setTimeout(() => {
      generateAtis(_buildBody(true))
        .then((data) => {
          if (data) {
            _lastData = data;
            _renderLocal();
          }
        })
        .catch(() => {});
    }, 700);
  }

  /**
   * Render the ATIS preview entirely client-side.
   * Starts from the last server-returned base text, strips conditional
   * sections (TL / TA / QFE / RMK) and re-injects them based on the
   * current UI state — giving instant feedback for checkbox clicks.
   */
  function _renderLocal(): void {
    if (!_lastData || !_lastData.atis_text) return;

    const tl = _checked('atis-tl-chk');
    const ta = _checked('atis-ta-chk');
    const qfe = parseInt(_value('atis-qfe')) || 0;
    const remarks = _value('atis-remarks');

    // Strip ALL conditional lines so we can re-insert cleanly.
    // [^.]+ handles both old combined format ("Transition level FL70, transition altitude 6000 feet.")
    // and new separate format ("Transition level FL70.")
    let text = _lastData.atis_text
      .replace(/ Transition level [^.]+\./g, '')
      .replace(/ Transition altitude [^.]+\./g, '')
      .replace(/ QFE [^.]+\./g, '')
      .replace(/ RMK .+$/, '');

    // Build insert block (goes right before "Information X recorded")
    let ins = '';
    if (qfe > 0) ins += ' QFE ' + qfe + ' hectopascals.';
    if (tl && _lastData.transition_level) ins += ' Transition level ' + _lastData.transition_level + '.';
    if (ta && _lastData.transition_altitude)
      ins += ' Transition altitude ' + _lastData.transition_altitude + ' feet.';

    if (ins) {
      // Insert before the closing "Information X recorded at …" sentence
      text = text.replace(/(Information [A-Z]+ recorded)/, ins.replace(/^ /, '') + ' $1');
    }

    if (remarks) text += ' RMK ' + remarks;

    // Replace airport name at the start with ATC Position if provided
    const atcPos = _value('atis-atc-pos');
    if (atcPos) {
      text = text.replace(/^.*? information ([A-Z]+)\./, atcPos + ' information $1.');
    }

    const output = _el('atis-text-output');
    if (output) output.value = text;
  }

  function _buildBody(isPreview: boolean): Partial<AtisRequest> {
    return {
      arrival_runway: _value('atis-arrival-rwy') || null,
      departure_runway: _value('atis-dep-rwy') || null,
      approach: null,
      qfe: parseInt(_value('atis-qfe')) || null,
      include_tl: _checked('atis-tl-chk'),
      include_ta: _checked('atis-ta-chk'),
      remarks: _value('atis-remarks') || null,
      metar_station: _value('atis-metar-station') || null,
      preview: isPreview,
    };
  }

  function _autoGenerate(): void {
    const sendBtn = document.querySelector<HTMLButtonElement>('.atis-btn-send');
    if (!sendBtn) return;
    sendBtn.disabled = true;
    sendBtn.textContent = 'Loading...';

    const done = (): void => {
      sendBtn.disabled = false;
      sendBtn.textContent = 'SEND';
    };

    generateAtis({ preview: false })
      .then((data) => {
        _lastData = data;
        _populate(data, true);
        done();
      })
      .catch((err: unknown) => {
        console.warn('ATIS auto-generate failed, loading latest stored:', err);
        getAtis()
          .then((data) => {
            if (data) {
              _lastData = data;
              _populate(data, true);
            }
            done();
          })
          .catch(done);
      });
  }

  function _populate(data: AtisResponse, isAuto: boolean): void {
    const mark = isAuto
      ? _setAuto
      : (id: string, val: unknown): void => {
          const el = _el(id);
          if (el) el.value = val != null ? String(val) : '';
        };

    if (data.atis_letter) mark('atis-letter-field', data.atis_letter);

    if (!_manualFields['atis-arrival-rwy']) mark('atis-arrival-rwy', data.arrival_runway || '');
    if (!_manualFields['atis-dep-rwy']) mark('atis-dep-rwy', data.departure_runway || '');
    if (!_manualFields['atis-metar-station']) mark('atis-metar-station', data.icao_code || '');

    const fl = data.transition_level ? String(data.transition_level).replace('FL', '') : '';
    _setAuto('atis-fl-val', fl);
    _setAuto('atis-alt-val', data.transition_altitude || '');

    // Default both checked on first load
    if (isAuto) {
      const tlChk = _el('atis-tl-chk');
      const taChk = _el('atis-ta-chk');
      if (tlChk) tlChk.checked = true;
      if (taChk) taChk.checked = true;
    }

    const activeChk = _el('atis-active-chk');
    if (activeChk) activeChk.checked = true;

    // Render preview with current UI overrides applied
    _renderLocal();
  }

  return { open, close, onOverlayClick, send };
})();

// Bridge for the inline on*= handlers in index.html (removed in Phase 3).
window.AtisModal = AtisModal;
export { AtisModal };
