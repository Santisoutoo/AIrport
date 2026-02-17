// wind.js -- TWR HMI: Smart Single Wind Widget with Safety Alerts

var windState = {
    direction: 0,
    speed: 0,
    gust: 0,
    maxSpeed: 0,
    minSpeed: 0,
    activeRwy: 170,   // default RWY 17
    XW_LIMIT: 20,
    TW_LIMIT: 5
};

// ---- Initialization ----

function initWindInstruments() {
    renderWindDial(document.getElementById('wind-dial'), windState.activeRwy);
    initRwySelector();
}

function initRwySelector() {
    var btns = document.querySelectorAll('.rwy-btn');
    btns.forEach(function (btn) {
        btn.addEventListener('click', function () {
            btns.forEach(function (b) { b.classList.remove('active'); });
            btn.classList.add('active');
            windState.activeRwy = parseInt(btn.dataset.rwy) || 170;
            renderWindDial(document.getElementById('wind-dial'), windState.activeRwy);
            updateWindDisplay();
        });
    });
}

// ---- SVG Wind Dial ----

function renderWindDial(container, rwyHdg) {
    if (!container) return;

    var size = 130;
    var cx = size / 2;
    var cy = size / 2;
    var r = 52;

    var svg = '<svg width="' + size + '" height="' + size +
        '" viewBox="0 0 ' + size + ' ' + size + '">';

    // Outer ring
    svg += '<circle cx="' + cx + '" cy="' + cy + '" r="' + r +
        '" fill="none" stroke="#334" stroke-width="2"/>';

    // Runway strip
    var rwyLen = 52;
    var rwyW = 6;
    var rwyRad = (rwyHdg - 90) * Math.PI / 180;
    var perpRad = rwyRad + Math.PI / 2;

    var dx = rwyLen * Math.cos(rwyRad);
    var dy = rwyLen * Math.sin(rwyRad);
    var px = rwyW * Math.cos(perpRad);
    var py = rwyW * Math.sin(perpRad);

    svg += '<polygon points="' +
        (cx + dx + px) + ',' + (cy + dy + py) + ' ' +
        (cx + dx - px) + ',' + (cy + dy - py) + ' ' +
        (cx - dx - px) + ',' + (cy - dy - py) + ' ' +
        (cx - dx + px) + ',' + (cy - dy + py) +
        '" fill="rgba(0,229,255,0.2)" stroke="rgba(0,229,255,0.5)" stroke-width="1" class="smr-rwy-shape"/>';

    // Dashed centerline
    for (var d = 0; d < 4; d++) {
        var t = -rwyLen + d * rwyLen * 2 / 7 * 2;
        var dsx = cx + t * Math.cos(rwyRad);
        var dsy = cy + t * Math.sin(rwyRad);
        var dex = cx + (t + rwyLen * 2 / 7) * Math.cos(rwyRad);
        var dey = cy + (t + rwyLen * 2 / 7) * Math.sin(rwyRad);
        svg += '<line x1="' + dsx + '" y1="' + dsy +
            '" x2="' + dex + '" y2="' + dey +
            '" stroke="rgba(255,255,255,0.3)" stroke-width="1"/>';
    }

    // Tick marks
    for (var deg = 0; deg < 360; deg += 10) {
        var rad = (deg - 90) * Math.PI / 180;
        var isMajor = deg % 30 === 0;
        var innerR = isMajor ? r - 10 : r - 5;

        var x1 = cx + innerR * Math.cos(rad);
        var y1 = cy + innerR * Math.sin(rad);
        var x2 = cx + r * Math.cos(rad);
        var y2 = cy + r * Math.sin(rad);

        svg += '<line x1="' + x1 + '" y1="' + y1 +
            '" x2="' + x2 + '" y2="' + y2 +
            '" stroke="' + (isMajor ? '#889' : '#445') +
            '" stroke-width="' + (isMajor ? 1.5 : 0.8) + '"/>';

        if (isMajor) {
            var labelR = r - 18;
            var lx = cx + labelR * Math.cos(rad);
            var ly = cy + labelR * Math.sin(rad);
            svg += '<text x="' + lx + '" y="' + ly +
                '" text-anchor="middle" dominant-baseline="central" ' +
                'fill="#778" font-size="8" font-family="monospace">' +
                String(deg).padStart(3, '0') + '</text>';
        }
    }

    // Cardinal labels
    var cardinals = [
        { deg: 0, label: 'N' }, { deg: 90, label: 'E' },
        { deg: 180, label: 'S' }, { deg: 270, label: 'W' }
    ];
    cardinals.forEach(function (c) {
        var cRad = (c.deg - 90) * Math.PI / 180;
        var lx = cx + (r + 10) * Math.cos(cRad);
        var ly = cy + (r + 10) * Math.sin(cRad);
        svg += '<text x="' + lx + '" y="' + ly +
            '" text-anchor="middle" dominant-baseline="central" ' +
            'fill="#99a" font-size="11" font-weight="700" font-family="monospace">' +
            c.label + '</text>';
    });

    // Gust arc (shows variability range)
    svg += '<path class="wind-gust-arc" d="" fill="rgba(255,145,0,0.15)" stroke="rgba(255,145,0,0.5)" stroke-width="1"/>';

    // Wind direction arrow
    svg += '<line class="wind-arrow" x1="' + cx + '" y1="' + cy +
        '" x2="' + cx + '" y2="' + (cy - r + 6) +
        '" stroke="#00e676" stroke-width="2.5" stroke-linecap="round"/>';
    svg += '<circle class="wind-arrow-tip" cx="' + cx + '" cy="' + (cy - r + 6) +
        '" r="4" fill="#00e676"/>';

    // Center speed display
    svg += '<rect x="' + (cx - 26) + '" y="' + (cy - 12) +
        '" width="52" height="24" rx="3" fill="#0a0e14" stroke="#334" stroke-width="1"/>';
    svg += '<text class="wind-speed-svg" x="' + cx + '" y="' + (cy + 2) +
        '" text-anchor="middle" dominant-baseline="central" ' +
        'fill="#00e676" font-size="18" font-weight="700" font-family="monospace">--</text>';
    svg += '<text x="' + cx + '" y="' + (cy + 18) +
        '" text-anchor="middle" fill="#556" font-size="8" font-family="monospace">kt</text>';

    svg += '</svg>';
    container.innerHTML = svg;
}

// ---- Update from METAR ----

function updateWindInstruments(metar) {
    if (!metar) return;

    windState.direction = metar.wind_direction || 0;
    windState.speed = metar.wind_speed || 0;
    windState.gust = metar.wind_gust || 0;

    if (windState.speed > windState.maxSpeed) windState.maxSpeed = windState.speed;
    if (windState.minSpeed === 0 || windState.speed < windState.minSpeed) windState.minSpeed = windState.speed;

    updateWindDisplay();
}

function updateWindDisplay() {
    var dialEl = document.getElementById('wind-dial');
    if (!dialEl) return;

    var svgEl = dialEl.querySelector('svg');
    if (!svgEl) return;

    var cx = 65, cy = 65, r = 52;
    var dir = windState.direction;
    var speed = windState.speed;
    var gust = windState.gust;

    // Update arrow position
    var arrow = svgEl.querySelector('.wind-arrow');
    var tip = svgEl.querySelector('.wind-arrow-tip');
    if (arrow && tip) {
        var rad = (dir - 90) * Math.PI / 180;
        var x2 = cx + (r - 6) * Math.cos(rad);
        var y2 = cy + (r - 6) * Math.sin(rad);
        var x1 = cx - 18 * Math.cos(rad);
        var y1 = cy - 18 * Math.sin(rad);

        arrow.setAttribute('x1', x1);
        arrow.setAttribute('y1', y1);
        arrow.setAttribute('x2', x2);
        arrow.setAttribute('y2', y2);
        tip.setAttribute('cx', x2);
        tip.setAttribute('cy', y2);

        var color = '#00e676';
        if (speed > 25) color = '#ff1744';
        else if (speed > 15) color = '#ff9100';
        arrow.setAttribute('stroke', color);
        tip.setAttribute('fill', color);
    }

    // Gust arc: draw an arc showing gust spread
    var gustArc = svgEl.querySelector('.wind-gust-arc');
    if (gustArc && gust > 0) {
        var spread = Math.min(30, (gust - speed) * 3);
        var startDeg = dir - spread;
        var endDeg = dir + spread;
        var arcR = r - 4;
        var startRad = (startDeg - 90) * Math.PI / 180;
        var endRad = (endDeg - 90) * Math.PI / 180;

        var sx = cx + arcR * Math.cos(startRad);
        var sy = cy + arcR * Math.sin(startRad);
        var ex = cx + arcR * Math.cos(endRad);
        var ey = cy + arcR * Math.sin(endRad);
        var largeArc = (endDeg - startDeg) > 180 ? 1 : 0;

        gustArc.setAttribute('d',
            'M ' + cx + ' ' + cy +
            ' L ' + sx + ' ' + sy +
            ' A ' + arcR + ' ' + arcR + ' 0 ' + largeArc + ' 1 ' + ex + ' ' + ey +
            ' Z');
    } else if (gustArc) {
        gustArc.setAttribute('d', '');
    }

    // Speed display
    var speedSvg = svgEl.querySelector('.wind-speed-svg');
    if (speedSvg) speedSvg.textContent = speed || '--';

    // Wind components for active runway
    var rwyHdg = windState.activeRwy;
    var angleDiff = (dir - rwyHdg) * Math.PI / 180;
    var headwind = Math.round(speed * Math.cos(angleDiff));
    var crosswind = Math.round(Math.abs(speed * Math.sin(angleDiff)));
    var tailwind = headwind < 0 ? Math.abs(headwind) : 0;
    var hwDisplay = headwind >= 0 ? headwind : 0;

    // Update XW bar
    updateLimitBar('xw', crosswind, windState.XW_LIMIT);
    var xwVal = document.getElementById('xw-value');
    if (xwVal) xwVal.textContent = crosswind + ' kt';

    // Update TW bar
    updateLimitBar('tw', tailwind, windState.TW_LIMIT);
    var twVal = document.getElementById('tw-value');
    if (twVal) twVal.textContent = tailwind + ' kt';

    // Update HW bar (no strict limit, just display)
    var hwBar = document.getElementById('hw-bar');
    if (hwBar) {
        var hwFill = hwBar.querySelector('.limit-bar-fill');
        if (hwFill) {
            var hwPct = Math.min(100, (hwDisplay / 40) * 100);
            hwFill.style.width = hwPct + '%';
        }
    }
    var hwVal = document.getElementById('hw-value');
    if (hwVal) hwVal.textContent = hwDisplay + ' kt';

    // Runway change alert
    var alertEl = document.getElementById('rwy-change-alert');
    if (alertEl) {
        if (tailwind > windState.TW_LIMIT) {
            var suggestedRwy = findOppositeRunway(rwyHdg);
            alertEl.textContent = 'TAILWIND ' + tailwind + 'kt > LIMIT ' + windState.TW_LIMIT + 'kt | SUGGEST: CHANGE TO RWY ' + suggestedRwy;
            alertEl.classList.remove('hidden');
        } else if (crosswind > windState.XW_LIMIT) {
            alertEl.textContent = 'CROSSWIND ' + crosswind + 'kt > LIMIT ' + windState.XW_LIMIT + 'kt';
            alertEl.classList.remove('hidden');
        } else {
            alertEl.classList.add('hidden');
        }
    }
}

function updateLimitBar(prefix, value, limit) {
    var bar = document.getElementById(prefix + '-bar');
    if (!bar) return;
    var fill = bar.querySelector('.limit-bar-fill');
    if (!fill) return;

    var pct = Math.min(100, (value / (limit * 1.5)) * 100);
    fill.style.width = pct + '%';

    if (value > limit) {
        fill.style.backgroundColor = 'var(--hmi-red)';
    } else if (value > limit * 0.7) {
        fill.style.backgroundColor = 'var(--hmi-orange)';
    } else {
        fill.style.backgroundColor = 'var(--hmi-green)';
    }
}

function findOppositeRunway(currentHdg) {
    // Find the opposite runway from the selector buttons
    var btns = document.querySelectorAll('.rwy-btn');
    for (var i = 0; i < btns.length; i++) {
        var hdg = parseInt(btns[i].dataset.rwy);
        if (hdg !== currentHdg) {
            return btns[i].textContent.replace('RWY ', '');
        }
    }
    // Fallback: calculate reciprocal
    var opp = (currentHdg + 180) % 360;
    return String(Math.round(opp / 10)).padStart(2, '0');
}
