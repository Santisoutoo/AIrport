// wind.js -- Wind Instrument (Telvent-style) -- multi-instance

var windGlobal = {
    windDirection: 0,
    windSpeed: 0,
    windGust: 0,
    maxWind: 0,
    minWind: 0
};

// ---- Init all instruments ----

function initWindInstruments() {
    var instruments = document.querySelectorAll('.wind-instrument');
    instruments.forEach(function (el) {
        renderWindCompass(el.querySelector('.wind-compass'));
    });
}

// ---- SVG Compass Rose ----

function renderWindCompass(container) {
    if (!container) return;

    var size = 220;
    var cx = size / 2;
    var cy = size / 2;
    var r = 90;

    var svg = '<svg width="' + size + '" height="' + size +
        '" viewBox="0 0 ' + size + ' ' + size + '">';

    // Outer ring
    svg += '<circle cx="' + cx + '" cy="' + cy + '" r="' + r +
        '" fill="none" stroke="#555" stroke-width="2"/>';

    // Tick marks & labels
    for (var deg = 0; deg < 360; deg += 10) {
        var rad = (deg - 90) * Math.PI / 180;
        var isMajor = deg % 30 === 0;
        var innerR = isMajor ? r - 14 : r - 7;

        var x1 = cx + innerR * Math.cos(rad);
        var y1 = cy + innerR * Math.sin(rad);
        var x2 = cx + r * Math.cos(rad);
        var y2 = cy + r * Math.sin(rad);

        svg += '<line x1="' + x1 + '" y1="' + y1 +
            '" x2="' + x2 + '" y2="' + y2 +
            '" stroke="' + (isMajor ? '#bbb' : '#666') +
            '" stroke-width="' + (isMajor ? 2 : 1) + '"/>';

        if (isMajor) {
            var labelR = r - 24;
            var lx = cx + labelR * Math.cos(rad);
            var ly = cy + labelR * Math.sin(rad);
            svg += '<text x="' + lx + '" y="' + ly +
                '" text-anchor="middle" dominant-baseline="central" ' +
                'fill="#999" font-size="9" font-family="monospace">' +
                String(deg).padStart(3, '0') + '</text>';
        }
    }

    // Cardinal labels outside ring
    var cardinals = [
        { deg: 0, label: 'N' }, { deg: 90, label: 'E' },
        { deg: 180, label: 'S' }, { deg: 270, label: 'W' }
    ];
    cardinals.forEach(function (c) {
        var cRad = (c.deg - 90) * Math.PI / 180;
        var lx = cx + (r + 13) * Math.cos(cRad);
        var ly = cy + (r + 13) * Math.sin(cRad);
        svg += '<text x="' + lx + '" y="' + ly +
            '" text-anchor="middle" dominant-baseline="central" ' +
            'fill="#aaa" font-size="13" font-weight="700" font-family="monospace">' +
            c.label + '</text>';
    });

    // Wind direction arrow (updated dynamically)
    svg += '<line class="wind-arrow" x1="' + cx + '" y1="' + cy +
        '" x2="' + cx + '" y2="' + (cy - r + 8) +
        '" stroke="#3fb950" stroke-width="3" stroke-linecap="round"/>';
    svg += '<circle class="wind-arrow-tip" cx="' + cx + '" cy="' + (cy - r + 8) +
        '" r="5" fill="#3fb950"/>';

    // Center speed background
    svg += '<rect x="' + (cx - 34) + '" y="' + (cy - 16) +
        '" width="68" height="32" rx="4" fill="#111" stroke="#444" stroke-width="1"/>';
    svg += '<text class="wind-speed-svg" x="' + cx + '" y="' + (cy + 2) +
        '" text-anchor="middle" dominant-baseline="central" ' +
        'fill="#3fb950" font-size="22" font-weight="700" font-family="monospace">--</text>';

    // Kt label
    svg += '<text x="' + cx + '" y="' + (cy + 24) +
        '" text-anchor="middle" fill="#777" font-size="10" font-family="monospace">Kt</text>';

    svg += '</svg>';
    container.innerHTML = svg;
}

// ---- Update all instruments from METAR ----

function updateWindInstruments(metar) {
    if (!metar) return;

    windGlobal.windDirection = metar.wind_direction || 0;
    windGlobal.windSpeed = metar.wind_speed || 0;
    windGlobal.windGust = metar.wind_gust || 0;

    if (windGlobal.windSpeed > windGlobal.maxWind) {
        windGlobal.maxWind = windGlobal.windSpeed;
    }
    if (windGlobal.minWind === 0 || windGlobal.windSpeed < windGlobal.minWind) {
        windGlobal.minWind = windGlobal.windSpeed;
    }

    var instruments = document.querySelectorAll('.wind-instrument');
    instruments.forEach(function (el) {
        var rwyHdg = parseInt(el.dataset.rwyHeading) || 0;
        updateOneInstrument(el, rwyHdg);
    });
}

function updateOneInstrument(el, rwyHdg) {
    // Arrow
    var arrow = el.querySelector('.wind-arrow');
    var tip = el.querySelector('.wind-arrow-tip');
    if (arrow && tip) {
        var dir = windGlobal.windDirection;
        var rad = (dir - 90) * Math.PI / 180;
        var cx = 110, cy = 110, r = 90;

        var x2 = cx + (r - 8) * Math.cos(rad);
        var y2 = cy + (r - 8) * Math.sin(rad);
        var x1 = cx - 22 * Math.cos(rad);
        var y1 = cy - 22 * Math.sin(rad);

        arrow.setAttribute('x1', x1);
        arrow.setAttribute('y1', y1);
        arrow.setAttribute('x2', x2);
        arrow.setAttribute('y2', y2);
        tip.setAttribute('cx', x2);
        tip.setAttribute('cy', y2);

        var color = '#3fb950';
        if (windGlobal.windSpeed > 25) color = '#f85149';
        else if (windGlobal.windSpeed > 15) color = '#d29922';
        arrow.setAttribute('stroke', color);
        tip.setAttribute('fill', color);
    }

    // Speed in compass center
    var speedSvg = el.querySelector('.wind-speed-svg');
    if (speedSvg) speedSvg.textContent = windGlobal.windSpeed || '--';

    // Data displays
    var dirVal = el.querySelector('.wind-dir-value');
    if (dirVal) {
        dirVal.textContent = windGlobal.windDirection === 0
            ? 'VRB'
            : String(windGlobal.windDirection).padStart(3, '0') + '\u00B0';
    }

    var maxVal = el.querySelector('.wind-max-value');
    if (maxVal) maxVal.textContent = windGlobal.maxWind || '--';

    var minVal = el.querySelector('.wind-min-value');
    if (minVal) minVal.textContent = windGlobal.minWind || '--';

    var gustVal = el.querySelector('.wind-gust-value');
    if (gustVal) gustVal.textContent = windGlobal.windGust ? 'G' + windGlobal.windGust : '--';

    // Wind components for this runway
    var windDir = windGlobal.windDirection;
    var windSpd = windGlobal.windSpeed;
    var angleDiff = (windDir - rwyHdg) * Math.PI / 180;
    var headwind = Math.round(windSpd * Math.cos(angleDiff));
    var crosswind = Math.round(windSpd * Math.sin(angleDiff));

    var hwEl = el.querySelector('.comp-headwind');
    if (hwEl) {
        var hwLabel = headwind >= 0 ? 'HW' : 'TW';
        hwEl.textContent = hwLabel + ' ' + Math.abs(headwind) + ' kt';
        hwEl.className = 'comp-headwind comp-value ' + (headwind >= 0 ? 'comp-hw' : 'comp-tw');
    }

    var xwEl = el.querySelector('.comp-crosswind');
    if (xwEl) {
        var xwLabel = crosswind >= 0 ? 'XW\u2192' : 'XW\u2190';
        xwEl.textContent = xwLabel + ' ' + Math.abs(crosswind) + ' kt';
        xwEl.className = 'comp-crosswind comp-value comp-xw';
    }
}
