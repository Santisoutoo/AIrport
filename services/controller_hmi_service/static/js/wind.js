// wind.js -- TWR HMI: Paired Runway Wind Widget with Safety Alerts

var windState = {
    direction: 0,
    speed: 0,
    gust: 0,
    maxSpeed: 0,
    minSpeed: 0,
    runwayGroups: [],
    XW_LIMIT: 20,
    TW_LIMIT: 5
};

// ---- Initialization ----

function initWindInstruments() {
    renderAllWindGroups();
}

function setRunwayGroups(groups) {
    windState.runwayGroups = groups;
    renderAllWindGroups();
}

function renderAllWindGroups() {
    var container = document.getElementById('wind-pairs-container');
    if (!container) return;

    container.innerHTML = '';

    if (windState.runwayGroups.length === 0) return;

    windState.runwayGroups.forEach(function (group) {
        var card = createWindPairCard(group);
        container.appendChild(card);
        renderWindDial(card.querySelector('.wind-dial'), group.hdg);
    });

    updateWindDisplay();
}

function createWindPairCard(group) {
    var card = document.createElement('div');
    card.className = 'wind-pair-card';
    card.dataset.rwyHdg = group.hdg;

    var header = document.createElement('div');
    header.className = 'wind-pair-header';
    header.textContent = group.labels.join(' / ');
    card.appendChild(header);

    var body = document.createElement('div');
    body.className = 'wind-pair-body';

    var dialContainer = document.createElement('div');
    dialContainer.className = 'wind-dial-container';
    var dial = document.createElement('div');
    dial.className = 'wind-dial';
    dialContainer.appendChild(dial);
    body.appendChild(dialContainer);

    var limits = document.createElement('div');
    limits.className = 'wind-limits-container';
    limits.appendChild(createLimitRow('XW', 'xw-' + group.hdg));
    limits.appendChild(createLimitRow('TW', 'tw-' + group.hdg));
    limits.appendChild(createLimitRow('HW', 'hw-' + group.hdg, true));
    body.appendChild(limits);

    card.appendChild(body);

    var alert = document.createElement('div');
    alert.className = 'rwy-change-alert hidden';
    alert.id = 'rwy-alert-' + group.hdg;
    card.appendChild(alert);

    return card;
}

function createLimitRow(label, idPrefix, isHw) {
    var row = document.createElement('div');
    row.className = 'wind-limit-row';

    var lbl = document.createElement('label');
    lbl.textContent = label;
    row.appendChild(lbl);

    var wrapper = document.createElement('div');
    wrapper.className = 'limit-bar-wrapper';

    var bar = document.createElement('div');
    bar.className = 'limit-bar' + (isHw ? ' limit-bar-hw' : '');
    bar.id = idPrefix + '-bar';
    var fill = document.createElement('div');
    fill.className = 'limit-bar-fill';
    bar.appendChild(fill);
    wrapper.appendChild(bar);

    var val = document.createElement('span');
    val.className = 'limit-value';
    val.id = idPrefix + '-value';
    val.textContent = '-- kt';
    wrapper.appendChild(val);

    row.appendChild(wrapper);
    return row;
}

// ---- SVG Wind Dial ----

function renderWindDial(container, rwyHdg) {
    if (!container) return;

    var size = 100;
    var cx = size / 2;
    var cy = size / 2;
    var r = 40;

    var svg = '<svg width="' + size + '" height="' + size +
        '" viewBox="0 0 ' + size + ' ' + size + '">';

    // Outer ring
    svg += '<circle cx="' + cx + '" cy="' + cy + '" r="' + r +
        '" fill="none" stroke="#334" stroke-width="2"/>';

    // Runway strip
    var rwyLen = 40;
    var rwyW = 5;
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
        '" fill="rgba(0,229,255,0.2)" stroke="rgba(0,229,255,0.5)" stroke-width="1"/>';

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
        var innerR = isMajor ? r - 8 : r - 4;

        var x1 = cx + innerR * Math.cos(rad);
        var y1 = cy + innerR * Math.sin(rad);
        var x2 = cx + r * Math.cos(rad);
        var y2 = cy + r * Math.sin(rad);

        svg += '<line x1="' + x1 + '" y1="' + y1 +
            '" x2="' + x2 + '" y2="' + y2 +
            '" stroke="' + (isMajor ? '#889' : '#445') +
            '" stroke-width="' + (isMajor ? 1.5 : 0.8) + '"/>';
    }

    // Cardinal labels
    var cardinals = [
        { deg: 0, label: 'N' }, { deg: 90, label: 'E' },
        { deg: 180, label: 'S' }, { deg: 270, label: 'W' }
    ];
    cardinals.forEach(function (c) {
        var cRad = (c.deg - 90) * Math.PI / 180;
        var lx = cx + (r + 8) * Math.cos(cRad);
        var ly = cy + (r + 8) * Math.sin(cRad);
        svg += '<text x="' + lx + '" y="' + ly +
            '" text-anchor="middle" dominant-baseline="central" ' +
            'fill="#99a" font-size="9" font-weight="700" font-family="monospace">' +
            c.label + '</text>';
    });

    // Gust arc
    svg += '<path class="wind-gust-arc" d="" fill="rgba(255,145,0,0.15)" stroke="rgba(255,145,0,0.5)" stroke-width="1"/>';

    // Wind direction arrow
    svg += '<line class="wind-arrow" x1="' + cx + '" y1="' + cy +
        '" x2="' + cx + '" y2="' + (cy - r + 6) +
        '" stroke="#00e676" stroke-width="2.5" stroke-linecap="round"/>';
    svg += '<circle class="wind-arrow-tip" cx="' + cx + '" cy="' + (cy - r + 6) +
        '" r="3.5" fill="#00e676"/>';

    // Center speed display
    svg += '<rect x="' + (cx - 18) + '" y="' + (cy - 9) +
        '" width="36" height="18" rx="3" fill="#0a0e14" stroke="#334" stroke-width="1"/>';
    svg += '<text class="wind-speed-svg" x="' + cx + '" y="' + (cy + 2) +
        '" text-anchor="middle" dominant-baseline="central" ' +
        'fill="#00e676" font-size="14" font-weight="700" font-family="monospace">--</text>';

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
    var container = document.getElementById('wind-pairs-container');
    if (!container) return;

    var cards = container.querySelectorAll('.wind-pair-card');
    cards.forEach(function (card) {
        var rwyHdg = parseInt(card.dataset.rwyHdg);
        updateCardWind(card, rwyHdg);
    });
}

function updateCardWind(card, rwyHdg) {
    var svgEl = card.querySelector('svg');
    if (!svgEl) return;

    var cx = 50, cy = 50, r = 40;

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
        var x1 = cx - 14 * Math.cos(rad);
        var y1 = cy - 14 * Math.sin(rad);

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

    // Gust arc
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

    // Wind components for this runway heading
    var angleDiff = (dir - rwyHdg) * Math.PI / 180;
    var headwind = Math.round(speed * Math.cos(angleDiff));
    var crosswind = Math.round(Math.abs(speed * Math.sin(angleDiff)));
    var tailwind = headwind < 0 ? Math.abs(headwind) : 0;
    var hwDisplay = headwind >= 0 ? headwind : 0;

    // Update XW bar
    updateLimitBar('xw-' + rwyHdg, crosswind, windState.XW_LIMIT);
    var xwVal = document.getElementById('xw-' + rwyHdg + '-value');
    if (xwVal) xwVal.textContent = crosswind + ' kt';

    // Update TW bar
    updateLimitBar('tw-' + rwyHdg, tailwind, windState.TW_LIMIT);
    var twVal = document.getElementById('tw-' + rwyHdg + '-value');
    if (twVal) twVal.textContent = tailwind + ' kt';

    // Update HW bar
    var hwBar = document.getElementById('hw-' + rwyHdg + '-bar');
    if (hwBar) {
        var hwFill = hwBar.querySelector('.limit-bar-fill');
        if (hwFill) {
            var hwPct = Math.min(100, (hwDisplay / 40) * 100);
            hwFill.style.width = hwPct + '%';
        }
    }
    var hwVal = document.getElementById('hw-' + rwyHdg + '-value');
    if (hwVal) hwVal.textContent = hwDisplay + ' kt';

    // Runway change alert
    var alertEl = document.getElementById('rwy-alert-' + rwyHdg);
    if (alertEl) {
        if (tailwind > windState.TW_LIMIT) {
            var reciprocal = findReciprocalGroup(rwyHdg);
            alertEl.textContent = 'TW ' + tailwind + 'kt > ' + windState.TW_LIMIT + 'kt | SUGGEST: ' + reciprocal;
            alertEl.classList.remove('hidden');
        } else if (crosswind > windState.XW_LIMIT) {
            alertEl.textContent = 'XW ' + crosswind + 'kt > ' + windState.XW_LIMIT + 'kt';
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

function findReciprocalGroup(hdg) {
    var recipHdg = (hdg + 180) % 360;
    if (recipHdg === 0) recipHdg = 360;
    for (var i = 0; i < windState.runwayGroups.length; i++) {
        if (windState.runwayGroups[i].hdg === recipHdg) {
            return windState.runwayGroups[i].labels.join('/');
        }
    }
    return 'RWY ' + String(Math.round(recipHdg / 10)).padStart(2, '0');
}
