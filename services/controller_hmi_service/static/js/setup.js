const API = '/api/v1/plugin';
const HMI_URL = '/';

const App = (() => {

    let _statusPollTimer = null;

    // --- Screen navigation ---

    function showScreen(id) {
        document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
        document.getElementById('screen-' + id).classList.add('active');
    }

    function showWelcome() {
        stopStatusPoll();
        showScreen('welcome');
        refreshStatus();
    }

    function showLogin() {
        clearError('login-error');
        document.getElementById('login-form').reset();
        showScreen('login');
    }

    function showRegister() {
        clearError('register-error');
        document.getElementById('register-form').reset();
        showScreen('register');
    }

    function showSession() {
        clearError('session-error');
        const icao = document.getElementById('welcome-icao').textContent;
        document.getElementById('session-icao-label').textContent = icao;
        resetStartBtn();
        showScreen('session');
    }

    // --- Helpers ---

    function showError(id, msg) {
        const el = document.getElementById(id);
        el.textContent = msg;
        el.classList.remove('hidden');
    }

    function clearError(id) {
        const el = document.getElementById(id);
        el.textContent = '';
        el.classList.add('hidden');
    }

    function setLoading(btnId, loading) {
        const btn = document.getElementById(btnId);
        if (!btn) return;
        btn.disabled = loading;
        btn.textContent = loading ? 'Please wait...' : (btn.dataset.label || btn.textContent);
    }

    function resetStartBtn() {
        const btn = document.getElementById('start-btn');
        if (btn) { btn.disabled = false; btn.textContent = btn.dataset.label || 'Start Session'; }
    }

    // --- Status polling ---

    async function refreshStatus() {
        try {
            const res = await fetch(`${API}/session/status`);
            const data = await res.json();
            const icao = data.icao || '----';

            document.getElementById('welcome-icao').textContent = icao;
            document.getElementById('welcome-airport-name').textContent =
                icao !== '----' ? icao : 'No airport detected';

            const dot = document.getElementById('welcome-status-dot');
            const txt = document.getElementById('welcome-status-text');

            if (icao !== '----') {
                dot.classList.add('online');
                txt.textContent = data.status === 'active' ? 'Session active' : 'X-Plane connected';
            } else {
                dot.classList.remove('online');
                txt.textContent = 'Waiting for X-Plane...';
            }
        } catch {
            document.getElementById('welcome-icao').textContent = '----';
            document.getElementById('welcome-status-dot').classList.remove('online');
            document.getElementById('welcome-status-text').textContent = 'Service unreachable';
        }
    }

    function startStatusPoll(onActive) {
        stopStatusPoll();
        _statusPollTimer = setInterval(async () => {
            try {
                const res = await fetch(`${API}/session/status`);
                const data = await res.json();
                if (data.status === 'active') {
                    stopStatusPoll();
                    onActive();
                }
            } catch { /* ignore */ }
        }, 1500);
    }

    function stopStatusPoll() {
        if (_statusPollTimer) { clearInterval(_statusPollTimer); _statusPollTimer = null; }
    }

    // --- Login ---

    async function submitLogin(e) {
        e.preventDefault();
        clearError('login-error');
        setLoading('login-btn', true);

        const username = document.getElementById('login-username').value.trim();
        const password = document.getElementById('login-password').value;

        try {
            const res = await fetch(`${API}/login`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, password }),
            });
            const data = await res.json();
            if (data.success) {
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

    async function submitRegister(e) {
        e.preventDefault();
        clearError('register-error');

        const username = document.getElementById('register-username').value.trim();
        const password = document.getElementById('register-password').value;
        const confirm  = document.getElementById('register-confirm').value;

        if (password !== confirm) { showError('register-error', 'Passwords do not match'); return; }
        if (password.length < 6)  { showError('register-error', 'Password must be at least 6 characters'); return; }

        setLoading('register-btn', true);

        try {
            const res = await fetch(`${API}/register`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, password }),
            });
            const data = await res.json();
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

    async function submitStartSession() {
        clearError('session-error');

        const aircraft_count = parseInt(document.getElementById('session-aircraft').value, 10);
        if (isNaN(aircraft_count) || aircraft_count < 1 || aircraft_count > 50) {
            showError('session-error', 'Aircraft count must be between 1 and 50');
            return;
        }

        setLoading('start-btn', true);

        const payload = {
            session_type: document.getElementById('session-type').value,
            weather:      document.getElementById('session-weather').value,
            aircraft_count,
            complexity:   document.getElementById('session-complexity').value,
        };

        try {
            const res = await fetch(`${API}/session/start`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            const data = await res.json();

            if (data.success) {
                document.getElementById('start-btn').textContent = 'Waiting for X-Plane...';
                // Poll until X-Plane confirms session is active, then go to HMI
                startStatusPoll(() => { window.location.href = HMI_URL; });
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

    return { showWelcome, showLogin, showRegister, showSession, submitLogin, submitRegister, submitStartSession };

})();
