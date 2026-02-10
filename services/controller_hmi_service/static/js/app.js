// app.js -- Main application controller

var API_BASE = '/api/v1/hmi';
var STRIP_REFRESH_MS = 15000;   // 15 seconds
var WEATHER_REFRESH_MS = 60000; // 60 seconds

var flightPlans = [];
var currentFilter = 'all';
var currentSort = 'departure_time';

// ---- Initialization ----
document.addEventListener('DOMContentLoaded', function() {
    startUTCClock();
    loadFlightStrips();
    loadWeather();

    // Auto-refresh
    setInterval(loadFlightStrips, STRIP_REFRESH_MS);
    setInterval(loadWeather, WEATHER_REFRESH_MS);

    // Filter buttons
    document.querySelectorAll('.filter-btn').forEach(function(btn) {
        btn.addEventListener('click', function(e) {
            document.querySelectorAll('.filter-btn').forEach(function(b) {
                b.classList.remove('active');
            });
            e.target.classList.add('active');
            currentFilter = e.target.dataset.filter;
            renderStrips();
        });
    });

    // Sort select
    document.getElementById('sort-select').addEventListener('change', function(e) {
        currentSort = e.target.value;
        renderStrips();
    });
});

// ---- Data Loading ----
function loadFlightStrips() {
    fetch(API_BASE + '/strips')
        .then(function(resp) {
            if (!resp.ok) throw new Error('HTTP ' + resp.status);
            return resp.json();
        })
        .then(function(data) {
            flightPlans = data;
            renderStrips();
            updateRefreshTimestamp();
            setConnectionStatus(true);
        })
        .catch(function(err) {
            console.error('Failed to load strips:', err);
            setConnectionStatus(false);
        });
}

function loadWeather() {
    fetch(API_BASE + '/weather')
        .then(function(resp) {
            if (!resp.ok) throw new Error('HTTP ' + resp.status);
            return resp.json();
        })
        .then(function(data) {
            renderWeatherPanel(data);
        })
        .catch(function(err) {
            console.error('Failed to load weather:', err);
            document.getElementById('metar-display').innerHTML =
                '<div class="wx-loading">Weather unavailable</div>';
        });
}

// ---- Rendering ----
function renderStrips() {
    var filtered = flightPlans;
    if (currentFilter !== 'all') {
        filtered = flightPlans.filter(function(fp) {
            return fp.flight_rules === currentFilter;
        });
    }
    filtered = sortFlightPlans(filtered, currentSort);
    renderFlightStrips(filtered, document.getElementById('strips-container'));
    document.getElementById('strip-count').textContent = filtered.length + ' strips';
}
