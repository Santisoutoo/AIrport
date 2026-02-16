// efs.js -- Electronic Flight Strip rendering

function renderFlightStrips(plans, container) {
    container.innerHTML = '';

    if (!plans || plans.length === 0) {
        container.innerHTML =
            '<div class="strips-empty">' +
                '<div class="strips-empty-icon">&#9992;</div>' +
                '<div>No flight plans loaded</div>' +
                '<div style="font-size:12px;margin-top:4px;">Generate plans via the Flight Plan Service</div>' +
            '</div>';
        return;
    }

    plans.forEach(function(plan) {
        var strip = createStripElement(plan);
        container.appendChild(strip);
    });
}

function createStripElement(plan) {
    var strip = document.createElement('div');
    strip.className = 'flight-strip' + (plan.flight_rules === 'V' ? ' vfr' : '');
    strip.dataset.registration = plan.aircraft_registration;

    // Format departure time as HH:MM
    var depTime = String(plan.departure_time).padStart(4, '0');
    var depFormatted = depTime.slice(0, 2) + ':' + depTime.slice(2);

    // Format altitude (FL or feet)
    var altDisplay;
    if (plan.cruising_altitude >= 10000) {
        altDisplay = 'FL' + Math.round(plan.cruising_altitude / 100);
    } else {
        altDisplay = plan.cruising_altitude + 'ft';
    }

    // Wake turbulence category class
    var wtcClasses = {
        'H': 'wtc-heavy',
        'M': 'wtc-medium',
        'L': 'wtc-light',
        'J': 'wtc-super'
    };
    var wtcClass = wtcClasses[plan.wake_turbulence_category] || 'wtc-medium';

    // Rules badge
    var rulesClass = plan.flight_rules === 'I' ? 'ifr-badge' : 'vfr-badge';
    var rulesText = plan.flight_rules === 'I' ? 'IFR' : 'VFR';

    strip.innerHTML =
        '<div class="cell">' +
            '<span class="rules-badge ' + rulesClass + '">' + rulesText + '</span>' +
        '</div>' +
        '<div class="cell">' +
            '<span class="callsign">' + escapeHtml(plan.aircraft_registration) + '</span>' +
            '<span class="pic-name">' + escapeHtml(plan.PIC_name) + '</span>' +
        '</div>' +
        '<div class="cell">' +
            '<span class="acft-type">' + escapeHtml(plan.aircraft_type) + '</span>' +
        '</div>' +
        '<div class="cell">' +
            '<span class="wtc-badge ' + wtcClass + '">' + escapeHtml(plan.wake_turbulence_category) + '</span>' +
        '</div>' +
        '<div class="cell">' +
            '<span class="icao dep-icao">' + escapeHtml(plan.departure_ICAO) + '</span>' +
            '<span class="time">' + depFormatted + 'Z</span>' +
        '</div>' +
        '<div class="cell">' +
            '<span class="route" title="' + escapeHtml(plan.route) + '">' +
                escapeHtml(truncateRoute(plan.route, 40)) +
            '</span>' +
        '</div>' +
        '<div class="cell">' +
            '<span class="altitude">' + altDisplay + '</span>' +
        '</div>' +
        '<div class="cell">' +
            '<span class="speed">' + plan.cruising_speed + 'kt</span>' +
        '</div>' +
        '<div class="cell">' +
            '<span class="icao dest-icao">' + escapeHtml(plan.destination_ICAO) + '</span>' +
            '<span class="alt-icao">' + escapeHtml(plan.alternate_ICAO || '-') + '</span>' +
        '</div>' +
        '<div class="cell">' +
            '<span class="eet">' + escapeHtml(plan.total_EET) + '</span>' +
        '</div>';

    return strip;
}

function truncateRoute(route, maxLen) {
    if (!route) return 'DCT';
    if (route.length <= maxLen) return route;
    return route.substring(0, maxLen) + '...';
}

function sortFlightPlans(plans, sortBy) {
    return plans.slice().sort(function(a, b) {
        switch (sortBy) {
            case 'departure_time':
                return a.departure_time - b.departure_time;
            case 'callsign':
                return a.aircraft_registration.localeCompare(b.aircraft_registration);
            case 'destination':
                return a.destination_ICAO.localeCompare(b.destination_ICAO);
            default:
                return 0;
        }
    });
}
