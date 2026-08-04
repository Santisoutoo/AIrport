// setup.ts — login / register / session-setup screen flow.

import { getSessionStatus, login, register, startSession } from '../api/client';
import { setUsername } from '../lib/storage';
import { Asr } from './asr.js';

const HMI_URL = '/';

const App = (() => {
  let _statusPollTimer: ReturnType<typeof setInterval> | null = null;

  // --- Screen navigation ---

  function showScreen(id: string): void {
    document.querySelectorAll('.screen').forEach((s) => s.classList.remove('active'));
    document.getElementById('screen-' + id)?.classList.add('active');
  }

  function showWelcome(): void {
    stopStatusPoll();
    showScreen('welcome');
    refreshStatus();
  }

  function showLogin(): void {
    clearError('login-error');
    (document.getElementById('login-form') as HTMLFormElement | null)?.reset();
    showScreen('login');
  }

  function showRegister(): void {
    clearError('register-error');
    (document.getElementById('register-form') as HTMLFormElement | null)?.reset();
    showScreen('register');
  }

  function showSession(): void {
    clearError('session-error');
    const icao = document.getElementById('welcome-icao')?.textContent ?? '----';
    const label = document.getElementById('session-icao-label');
    if (label) label.textContent = icao;
    resetStartBtn();
    showScreen('session');
  }

  async function showAsr(): Promise<void> {
    showScreen('asr');
    await Asr.initScreen();
  }

  // --- Helpers ---

  function _input(id: string): HTMLInputElement | null {
    return document.getElementById(id) as HTMLInputElement | null;
  }

  function showError(id: string, msg: string): void {
    const el = document.getElementById(id);
    if (!el) return;
    el.textContent = msg;
    el.classList.remove('hidden');
  }

  function clearError(id: string): void {
    const el = document.getElementById(id);
    if (!el) return;
    el.textContent = '';
    el.classList.add('hidden');
  }

  function setLoading(btnId: string, loading: boolean): void {
    const btn = document.getElementById(btnId) as HTMLButtonElement | null;
    if (!btn) return;
    btn.disabled = loading;
    btn.textContent = loading ? 'Please wait...' : btn.dataset.label || btn.textContent;
  }

  function resetStartBtn(): void {
    const btn = document.getElementById('start-btn') as HTMLButtonElement | null;
    if (btn) {
      btn.disabled = false;
      btn.textContent = btn.dataset.label || 'Start Session';
    }
  }

  // --- Status polling ---

  async function refreshStatus(): Promise<void> {
    const icaoEl = document.getElementById('welcome-icao');
    const nameEl = document.getElementById('welcome-airport-name');
    const dot = document.getElementById('welcome-status-dot');
    const txt = document.getElementById('welcome-status-text');
    try {
      const data = await getSessionStatus();
      const icao = data.icao || '----';

      if (icaoEl) icaoEl.textContent = icao;
      if (nameEl) nameEl.textContent = icao !== '----' ? icao : 'No airport detected';

      if (icao !== '----') {
        dot?.classList.add('online');
        if (txt)
          txt.textContent = data.status === 'active' ? 'Session active' : 'X-Plane connected';
      } else {
        dot?.classList.remove('online');
        if (txt) txt.textContent = 'Waiting for X-Plane...';
      }
    } catch {
      if (icaoEl) icaoEl.textContent = '----';
      dot?.classList.remove('online');
      if (txt) txt.textContent = 'Service unreachable';
    }
  }

  function startStatusPoll(onActive: () => void): void {
    stopStatusPoll();
    _statusPollTimer = setInterval(async () => {
      try {
        const data = await getSessionStatus();
        if (data.status === 'active') {
          stopStatusPoll();
          onActive();
        }
      } catch {
        /* ignore */
      }
    }, 1500);
  }

  function stopStatusPoll(): void {
    if (_statusPollTimer) {
      clearInterval(_statusPollTimer);
      _statusPollTimer = null;
    }
  }

  // --- Login ---

  async function submitLogin(e: Event): Promise<void> {
    e.preventDefault();
    clearError('login-error');
    setLoading('login-btn', true);

    const username = _input('login-username')?.value.trim() ?? '';
    const password = _input('login-password')?.value ?? '';

    try {
      const data = await login(username, password);
      if (data.success) {
        setUsername(data.username ?? username);
        showSession();
      } else {
        showError('login-error', data.message || 'Login failed');
      }
    } catch {
      showError('login-error', 'Could not connect to server');
    } finally {
      setLoading('login-btn', false);
    }
  }

  // --- Register ---

  async function submitRegister(e: Event): Promise<void> {
    e.preventDefault();
    clearError('register-error');

    const username = _input('register-username')?.value.trim() ?? '';
    const password = _input('register-password')?.value ?? '';
    const confirm = _input('register-confirm')?.value ?? '';

    if (password !== confirm) {
      showError('register-error', 'Passwords do not match');
      return;
    }
    if (password.length < 6) {
      showError('register-error', 'Password must be at least 6 characters');
      return;
    }

    setLoading('register-btn', true);

    try {
      const data = await register(username, password);
      if (data.success) {
        showLogin();
      } else {
        showError('register-error', data.message || 'Registration failed');
      }
    } catch {
      showError('register-error', 'Could not connect to server');
    } finally {
      setLoading('register-btn', false);
    }
  }

  // --- Start Session ---

  async function submitStartSession(): Promise<void> {
    clearError('session-error');

    const aircraft_count = parseInt(_input('session-aircraft')?.value ?? '', 10);
    if (isNaN(aircraft_count) || aircraft_count < 1 || aircraft_count > 50) {
      showError('session-error', 'Aircraft count must be between 1 and 50');
      return;
    }

    setLoading('start-btn', true);

    const payload = {
      session_type: _input('session-type')?.value ?? '',
      weather: _input('session-weather')?.value ?? '',
      aircraft_count,
      complexity: _input('session-complexity')?.value ?? '',
    };

    try {
      const data = await startSession(payload);

      if (data.success) {
        const btn = document.getElementById('start-btn');
        if (btn) btn.textContent = 'Waiting for X-Plane...';
        // Poll until X-Plane confirms session is active, then go to HMI
        startStatusPoll(() => {
          window.location.href = HMI_URL;
        });
      } else {
        showError('session-error', data.message || 'Failed to start session');
        resetStartBtn();
      }
    } catch {
      showError('session-error', 'Could not connect to server');
      resetStartBtn();
    }
  }

  // --- Init ---

  document.addEventListener('DOMContentLoaded', () => {
    showWelcome();
    setInterval(refreshStatus, 30000);
  });

  return {
    showWelcome,
    showLogin,
    showRegister,
    showSession,
    showAsr,
    submitLogin,
    submitRegister,
    submitStartSession,
  };
})();

// Bridge for the inline on*= handlers in setup.html (removed in Phase 3).
window.App = App;
export { App };
