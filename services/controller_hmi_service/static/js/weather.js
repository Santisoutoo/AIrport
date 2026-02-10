// weather.js -- Weather panel rendering & utilities

function renderWeatherPanel(metar) {
    var panel = document.getElementById('metar-display');

    var windGust = metar.wind_gust ? ' G' + metar.wind_gust : '';
    var windDir = metar.wind_direction === 0
        ? 'VRB'
        : String(metar.wind_direction).padStart(3, '0');
    var visKm = (metar.visibility_m / 1000).toFixed(1);

    var cloudsHtml = '';
    if (metar.clouds && metar.clouds.length > 0) {
        cloudsHtml = metar.clouds.map(function(c) {
            return '<span class="cloud-layer">' + c.coverage + ' ' + c.base_ft + 'ft</span>';
        }).join(' ');
    } else {
        cloudsHtml = 'CAVOK';
    }

    var catClass = {
        'VFR': 'cat-vfr',
        'MVFR': 'cat-mvfr',
        'IFR': 'cat-ifr',
        'LIFR': 'cat-lifr'
    }[metar.flight_category] || 'cat-vfr';

    var wxSection = '';
    if (metar.weather) {
        wxSection = '<div class="wx-section"><label>WX</label><span>' +
            metar.weather + '</span></div>';
    }

    panel.innerHTML =
        '<div class="wx-section raw-metar">' +
            '<label>METAR</label>' +
            '<code>' + escapeHtml(metar.raw_metar) + '</code>' +
        '</div>' +
        '<div class="wx-section">' +
            '<label>WIND</label>' +
            '<span>' + windDir + '/' + metar.wind_speed + 'kt' + windGust + '</span>' +
        '</div>' +
        '<div class="wx-section">' +
            '<label>VISIBILITY</label>' +
            '<span>' + visKm + ' km (' + metar.visibility_m + 'm)</span>' +
        '</div>' +
        '<div class="wx-section">' +
            '<label>CLOUDS</label>' +
            '<span>' + cloudsHtml + '</span>' +
        '</div>' +
        '<div class="wx-section">' +
            '<label>TEMP / DEWPOINT</label>' +
            '<span>' + metar.temperature_c + ' / ' + metar.dewpoint_c + ' &deg;C</span>' +
        '</div>' +
        '<div class="wx-section">' +
            '<label>QNH</label>' +
            '<span class="qnh-value">' + metar.qnh_hpa + ' hPa</span>' +
        '</div>' +
        '<div class="wx-section">' +
            '<label>FLIGHT CATEGORY</label>' +
            '<span class="flight-cat ' + catClass + '">' + metar.flight_category + '</span>' +
        '</div>' +
        wxSection;
}

function startUTCClock() {
    var clockEl = document.getElementById('utc-clock');

    function update() {
        var now = new Date();
        clockEl.textContent =
            String(now.getUTCHours()).padStart(2, '0') + ':' +
            String(now.getUTCMinutes()).padStart(2, '0') + ':' +
            String(now.getUTCSeconds()).padStart(2, '0') + 'Z';
    }

    update();
    setInterval(update, 1000);
}

function updateRefreshTimestamp() {
    var el = document.getElementById('last-refresh');
    var now = new Date();
    el.textContent = 'Last refresh: ' +
        String(now.getUTCHours()).padStart(2, '0') + ':' +
        String(now.getUTCMinutes()).padStart(2, '0') + ':' +
        String(now.getUTCSeconds()).padStart(2, '0') + 'Z';
}

function setConnectionStatus(connected) {
    var el = document.getElementById('connection-status');
    el.textContent = connected ? 'CONNECTED' : 'DISCONNECTED';
    el.className = 'status-indicator ' + (connected ? 'connected' : 'disconnected');
}

function escapeHtml(text) {
    var div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
