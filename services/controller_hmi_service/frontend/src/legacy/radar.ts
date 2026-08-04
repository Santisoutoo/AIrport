/* ============================================
   AIrport TWR — Radar Background
   Airport at center with arrivals / departures
   ============================================ */

interface RadarAircraft {
  x: number;
  y: number;
  vx: number;
  vy: number;
  type: 'arrival' | 'departure';
  cs: string;
  lit: number;
  trail: [number, number][];
}

(() => {
  const canvas = document.getElementById('radar-bg') as HTMLCanvasElement | null;
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  if (!ctx) return;

  const D2R = Math.PI / 180;

  // ── Colours (muted, non-competing) ──────────────────────────────────
  const C_RING = 'rgba(0,229,255,0.05)';
  const C_GRID = 'rgba(0,229,255,0.035)';
  const C_SECTOR = 'rgba(0,229,255,0.07)';
  const C_APT_DIM = 'rgba(0,229,255,0.09)';
  const C_ARR = 'rgba(0,230,118,0.60)'; // arrival blip
  const C_DEP = 'rgba(0,182,255,0.55)'; // departure blip (cyan-ish)
  const C_LABEL = 'rgba(0,230,118,0.35)';
  const C_LABEL_D = 'rgba(0,182,255,0.30)';
  const C_DIM_DOT = 'rgba(0,230,118,0.08)';

  // ── State ────────────────────────────────────────────────────────────
  let W = 0,
    H = 0,
    CX = 0,
    CY = 0,
    maxR = 0;
  let sweepAngle = 0;
  const SWEEP_SPEED = 0.38; // rad/s
  let lastTime = 0;

  // ── Runways (defined in pixels from centre, scaled on resize) ───────
  // RW1 = departures only  (010/190, nearly N-S)
  // RW2 = arrivals  only  (075/255, ENE-WSW)
  const RW_DEP = { hdg: 10 * D2R, len: 58, w: 6 }; // takeoff runway
  const RW_ARR = { hdg: 75 * D2R, len: 46, w: 6 }; // landing runway

  // Arrivals come FROM east or west along RW_ARR axis
  const APP_HEADINGS = [
    (75 + 180) * D2R, // 255° – from east, landing heading 075
    75 * D2R, //  75° – from west, landing heading 255
  ];

  // Departures leave northbound or southbound along RW_DEP axis
  const DEP_HEADINGS = [
    10 * D2R, //  010° – northbound
    (10 + 180) * D2R, //  190° – southbound
  ];

  // ── Callsigns ────────────────────────────────────────────────────────
  const CS = [
    'IBE34F', 'VLG8BX', 'RYR12K', 'AEA921', 'EZY43W',
    'BAW26N', 'DLH5CY', 'AFR82J', 'SWR4QP', 'TAP731',
    'KLM07R', 'UAE19X', 'AAL50V', 'UAL24M', 'SKW68T',
    'BEL32P', 'WZZ51N', 'FIN7QA', 'SAS89C', 'THY4MW',
  ];
  let csIdx = 0;
  function nextCS(): string {
    return CS[csIdx++ % CS.length]!;
  }

  // ── Aircraft factory ─────────────────────────────────────────────────
  function spawnArrival(): RadarAircraft {
    const base = APP_HEADINGS[Math.floor(Math.random() * APP_HEADINGS.length)]!;
    const angle = base + (Math.random() - 0.5) * 18 * D2R;
    const dist = maxR * (0.72 + Math.random() * 0.22);
    const spd = 22 + Math.random() * 18;
    return {
      x: Math.cos(angle) * dist,
      y: Math.sin(angle) * dist,
      vx: -Math.cos(angle) * spd,
      vy: -Math.sin(angle) * spd,
      type: 'arrival',
      cs: nextCS(),
      lit: 0,
      trail: [],
    };
  }

  function spawnDeparture(): RadarAircraft {
    // Depart along RW_DEP axis, choose N or S randomly
    const base = DEP_HEADINGS[Math.floor(Math.random() * DEP_HEADINGS.length)]!;
    const angle = base + (Math.random() - 0.5) * 12 * D2R;
    const spd = 18 + Math.random() * 22;
    // Spawn near the departure runway threshold
    const tx = Math.sin(RW_DEP.hdg) * RW_DEP.len * (Math.random() < 0.5 ? 1 : -1);
    const ty = -Math.cos(RW_DEP.hdg) * RW_DEP.len * (Math.random() < 0.5 ? 1 : -1);
    return {
      x: tx + (Math.random() - 0.5) * 4,
      y: ty + (Math.random() - 0.5) * 4,
      vx: Math.cos(angle) * spd,
      vy: Math.sin(angle) * spd,
      type: 'departure',
      cs: nextCS(),
      lit: 0,
      trail: [],
    };
  }

  // 8 arrivals + 5 scattered arrivals + 6 departures
  let aircraft: RadarAircraft[] = [];
  function initAircraft(): void {
    aircraft = [];
    for (let i = 0; i < 8; i++) aircraft.push(spawnArrival());
    for (let i = 0; i < 5; i++) {
      const ac = spawnArrival();
      // Scatter arrivals across full route so they don't all start at edge
      const t = Math.random();
      ac.x *= t;
      ac.y *= t;
      aircraft.push(ac);
    }
    for (let i = 0; i < 6; i++) {
      const ac = spawnDeparture();
      const t = Math.random();
      ac.x += ac.vx * t * 8;
      ac.y += ac.vy * t * 8;
      aircraft.push(ac);
    }
  }

  // ── Resize ───────────────────────────────────────────────────────────
  function resize(): void {
    W = canvas!.width = window.innerWidth;
    H = canvas!.height = window.innerHeight;
    CX = W / 2;
    CY = H / 2;
    maxR = Math.sqrt(CX * CX + CY * CY);
    initAircraft();
  }

  // ── Draw: concentric rings ────────────────────────────────────────────
  function drawRings(): void {
    ctx!.strokeStyle = C_RING;
    ctx!.lineWidth = 0.6;
    ctx!.fillStyle = 'rgba(0,229,255,0.055)';
    ctx!.font = '9px "Courier New", monospace';
    for (let i = 1; i <= 5; i++) {
      const r = (i / 5) * maxR;
      ctx!.beginPath();
      ctx!.arc(CX, CY, r, 0, Math.PI * 2);
      ctx!.stroke();
      ctx!.fillText(`${i * 20}NM`, CX + 3, CY - r + 11);
    }
  }

  // ── Draw: radial grid ─────────────────────────────────────────────────
  function drawGrid(): void {
    ctx!.strokeStyle = C_GRID;
    ctx!.lineWidth = 0.5;
    for (let i = 0; i < 12; i++) {
      const a = (i / 12) * Math.PI * 2;
      ctx!.beginPath();
      ctx!.moveTo(CX, CY);
      ctx!.lineTo(CX + Math.cos(a) * maxR * 1.15, CY + Math.sin(a) * maxR * 1.15);
      ctx!.stroke();
    }
  }

  // ── Draw: airspace sectors ────────────────────────────────────────────
  const SECTORS: [number, number][][] = [
    [[-0.55, -0.85], [-0.12, -0.52], [-0.28, -0.08], [-0.72, -0.22]],
    [[0.08, -0.80], [0.58, -0.68], [0.62, -0.18], [0.18, -0.28]],
    [[-0.05, 0.08], [0.52, 0.04], [0.68, 0.62], [0.08, 0.78]],
    [[-0.68, 0.18], [-0.18, 0.28], [-0.12, 0.72], [-0.62, 0.88]],
  ];
  function drawSectors(): void {
    ctx!.strokeStyle = C_SECTOR;
    ctx!.lineWidth = 0.7;
    ctx!.setLineDash([4, 9]);
    for (const pts of SECTORS) {
      ctx!.beginPath();
      ctx!.moveTo(CX + pts[0]![0] * maxR, CY + pts[0]![1] * maxR);
      for (let i = 1; i < pts.length; i++)
        ctx!.lineTo(CX + pts[i]![0] * maxR, CY + pts[i]![1] * maxR);
      ctx!.closePath();
      ctx!.stroke();
    }
    ctx!.setLineDash([]);
  }

  // ── Draw: airport ─────────────────────────────────────────────────────
  function drawRunway(
    rw: { hdg: number; len: number; w: number },
    fillCol: string,
    edgeCol: string,
    lineCol: string,
  ): void {
    ctx!.save();
    ctx!.translate(CX, CY);
    ctx!.rotate(rw.hdg);

    ctx!.fillStyle = fillCol;
    ctx!.fillRect(-rw.w, -rw.len, rw.w * 2, rw.len * 2);

    ctx!.strokeStyle = edgeCol;
    ctx!.lineWidth = 0.9;
    ctx!.strokeRect(-rw.w, -rw.len, rw.w * 2, rw.len * 2);

    ctx!.strokeStyle = lineCol;
    ctx!.lineWidth = 0.6;
    ctx!.setLineDash([7, 5]);
    ctx!.beginPath();
    ctx!.moveTo(0, -rw.len);
    ctx!.lineTo(0, rw.len);
    ctx!.stroke();
    ctx!.setLineDash([]);

    ctx!.strokeStyle = edgeCol;
    ctx!.lineWidth = 1.4;
    for (const end of [-rw.len, rw.len]) {
      ctx!.beginPath();
      ctx!.moveTo(-rw.w, end);
      ctx!.lineTo(rw.w, end);
      ctx!.stroke();
    }

    ctx!.restore();
  }

  function drawAirport(): void {
    // Terminal block
    ctx!.fillStyle = 'rgba(0,229,255,0.06)';
    ctx!.fillRect(CX + 8, CY - 12, 18, 10);
    ctx!.strokeStyle = C_APT_DIM;
    ctx!.lineWidth = 0.6;
    ctx!.strokeRect(CX + 8, CY - 12, 18, 10);

    // Taxiway spine
    ctx!.strokeStyle = C_APT_DIM;
    ctx!.lineWidth = 1.2;
    ctx!.beginPath();
    ctx!.moveTo(CX + 8, CY - 7);
    ctx!.lineTo(CX + 2, CY - 7);
    ctx!.lineTo(CX + 2, CY + 5);
    ctx!.stroke();

    // DEP runway — cyan tint
    drawRunway(RW_DEP, 'rgba(0,229,255,0.08)', 'rgba(0,229,255,0.22)', 'rgba(0,229,255,0.26)');

    // ARR runway — green tint
    drawRunway(RW_ARR, 'rgba(0,230,118,0.07)', 'rgba(0,230,118,0.22)', 'rgba(0,230,118,0.24)');

    // Runway labels (tiny)
    ctx!.font = '7px "Courier New", monospace';
    const depEx = Math.sin(RW_DEP.hdg) * (RW_DEP.len + 10);
    const depEy = -Math.cos(RW_DEP.hdg) * (RW_DEP.len + 10);
    ctx!.fillStyle = 'rgba(0,229,255,0.30)';
    ctx!.fillText('DEP', CX + depEx - 8, CY + depEy + 3);
    ctx!.fillText('DEP', CX - depEx - 8, CY - depEy + 3);

    const arrEx = Math.sin(RW_ARR.hdg) * (RW_ARR.len + 10);
    const arrEy = -Math.cos(RW_ARR.hdg) * (RW_ARR.len + 10);
    ctx!.fillStyle = 'rgba(0,230,118,0.28)';
    ctx!.fillText('ARR', CX + arrEx - 8, CY + arrEy + 3);
    ctx!.fillText('ARR', CX - arrEx - 8, CY - arrEy + 3);

    // Airport centre dot
    ctx!.fillStyle = 'rgba(0,229,255,0.45)';
    ctx!.beginPath();
    ctx!.arc(CX, CY, 2.5, 0, Math.PI * 2);
    ctx!.fill();

    // ATZ circle
    ctx!.strokeStyle = 'rgba(0,229,255,0.11)';
    ctx!.lineWidth = 0.8;
    ctx!.beginPath();
    ctx!.arc(CX, CY, 18, 0, Math.PI * 2);
    ctx!.stroke();

    // ILS feathers — ARRIVAL runway only
    ctx!.strokeStyle = 'rgba(0,230,118,0.12)';
    ctx!.lineWidth = 0.7;
    ctx!.setLineDash([5, 7]);
    for (const sign of [-1, 1]) {
      const tx = CX + Math.sin(RW_ARR.hdg) * RW_ARR.len * sign;
      const ty = CY - Math.cos(RW_ARR.hdg) * RW_ARR.len * sign;
      // Extended centreline
      ctx!.beginPath();
      ctx!.moveTo(tx, ty);
      ctx!.lineTo(
        tx + Math.sin(RW_ARR.hdg) * maxR * 0.4 * sign,
        ty - Math.cos(RW_ARR.hdg) * maxR * 0.4 * sign,
      );
      ctx!.stroke();
      // Funnel (±3.5°)
      for (const side of [-1, 1]) {
        const fa = RW_ARR.hdg * sign + side * 3.5 * D2R;
        ctx!.beginPath();
        ctx!.moveTo(tx, ty);
        ctx!.lineTo(tx + Math.sin(fa) * maxR * 0.38 * sign, ty - Math.cos(fa) * maxR * 0.38 * sign);
        ctx!.stroke();
      }
    }
    ctx!.setLineDash([]);
  }

  // ── Draw: radar sweep ─────────────────────────────────────────────────
  function drawSweep(angle: number): void {
    const FADE = Math.PI * 0.5;
    const SLICES = 55;
    for (let i = 0; i < SLICES; i++) {
      const t = i / SLICES;
      const a1 = angle - FADE * (1 - t);
      const a2 = angle - FADE * (1 - (i + 1) / SLICES);
      ctx!.beginPath();
      ctx!.moveTo(CX, CY);
      ctx!.arc(CX, CY, maxR * 1.1, a1, a2, false);
      ctx!.closePath();
      ctx!.fillStyle = `rgba(0,229,255,${(t * 0.12).toFixed(3)})`;
      ctx!.fill();
    }
    // Leading edge
    ctx!.strokeStyle = 'rgba(0,229,255,0.20)';
    ctx!.lineWidth = 1.2;
    ctx!.beginPath();
    ctx!.moveTo(CX, CY);
    ctx!.lineTo(CX + Math.cos(angle) * maxR * 1.1, CY + Math.sin(angle) * maxR * 1.1);
    ctx!.stroke();
  }

  // ── Draw & update: aircraft ───────────────────────────────────────────
  function updateDrawAircraft(dt: number): void {
    for (const ac of aircraft) {
      // Move
      ac.x += ac.vx * dt;
      ac.y += ac.vy * dt;

      const dist = Math.sqrt(ac.x * ac.x + ac.y * ac.y);

      // Lifecycle
      if (ac.type === 'arrival' && dist < 14) {
        // Landed on ARR runway → new arrival spawns at edge
        Object.assign(ac, spawnArrival());
      } else if (ac.type === 'departure' && dist > maxR * 0.93) {
        // Left radar coverage → new departure spawns at DEP runway
        Object.assign(ac, spawnDeparture());
      }

      // Sweep detection
      const acAngle = Math.atan2(ac.y, ac.x);
      const diff = (((sweepAngle - acAngle) % (Math.PI * 2)) + Math.PI * 2) % (Math.PI * 2);
      if (diff < 0.09) {
        ac.lit = 1.0;
        ac.trail.unshift([ac.x, ac.y]);
        if (ac.trail.length > 5) ac.trail.pop();
      }
      ac.lit = Math.max(0, ac.lit - dt * 0.32);

      const sx = CX + ac.x;
      const sy = CY + ac.y;
      const isArr = ac.type === 'arrival';
      const blipC = isArr ? C_ARR : C_DEP;
      const labelC = isArr ? C_LABEL : C_LABEL_D;

      // Trail dots
      for (let i = 0; i < ac.trail.length; i++) {
        const [tx, ty] = ac.trail[i]!;
        const a = (1 - i / ac.trail.length) * 0.25;
        ctx!.fillStyle = isArr
          ? `rgba(0,230,118,${a.toFixed(2)})`
          : `rgba(0,182,255,${a.toFixed(2)})`;
        ctx!.beginPath();
        ctx!.arc(CX + tx, CY + ty, 1.8, 0, Math.PI * 2);
        ctx!.fill();
      }

      if (ac.lit > 0) {
        // Glowing blip
        ctx!.shadowColor = isArr ? 'rgba(0,230,118,0.55)' : 'rgba(0,182,255,0.5)';
        ctx!.shadowBlur = 10 * ac.lit;
        ctx!.fillStyle = blipC;
        ctx!.beginPath();
        ctx!.arc(sx, sy, 2.5, 0, Math.PI * 2);
        ctx!.fill();
        ctx!.shadowBlur = 0;

        // Aircraft chevron (→ for dep, ← for arr)
        ctx!.strokeStyle = blipC;
        ctx!.lineWidth = 0.9;
        const hx = ac.vx,
          hy = ac.vy;
        const hlen = Math.sqrt(hx * hx + hy * hy) || 1;
        const nx = (hx / hlen) * 6,
          ny = (hy / hlen) * 6;
        const px = -ny * 0.45,
          py = nx * 0.45;
        ctx!.beginPath();
        ctx!.moveTo(sx + nx, sy + ny);
        ctx!.lineTo(sx - nx + px, sy - ny + py);
        ctx!.moveTo(sx + nx, sy + ny);
        ctx!.lineTo(sx - nx - px, sy - ny - py);
        ctx!.stroke();

        // Callsign label
        ctx!.fillStyle = labelC;
        ctx!.font = '8px "Courier New", monospace';
        ctx!.fillText(ac.cs, sx + 7, sy - 4);
      } else {
        // Dim ghost dot
        ctx!.fillStyle = C_DIM_DOT;
        ctx!.beginPath();
        ctx!.arc(sx, sy, 1.5, 0, Math.PI * 2);
        ctx!.fill();
      }
    }
  }

  // ── Draw: degree tickmarks ────────────────────────────────────────────
  function drawTicks(): void {
    ctx!.fillStyle = 'rgba(0,229,255,0.07)';
    ctx!.strokeStyle = 'rgba(0,229,255,0.07)';
    ctx!.font = '8px "Courier New", monospace';
    ctx!.lineWidth = 0.5;
    for (let deg = 0; deg < 360; deg += 10) {
      const rad = (deg - 90) * D2R;
      const r1 = maxR * 0.95,
        r2 = maxR * 1.0;
      ctx!.beginPath();
      ctx!.moveTo(CX + Math.cos(rad) * r1, CY + Math.sin(rad) * r1);
      ctx!.lineTo(CX + Math.cos(rad) * r2, CY + Math.sin(rad) * r2);
      ctx!.stroke();
      if (deg % 30 === 0) {
        const lr = maxR * 0.88;
        ctx!.fillText(
          String(deg).padStart(3, '0') + '°',
          CX + Math.cos(rad) * lr - 10,
          CY + Math.sin(rad) * lr + 3,
        );
      }
    }
  }

  // ── Main loop ─────────────────────────────────────────────────────────
  function frame(ts: number): void {
    const dt = Math.min((ts - lastTime) / 1000, 0.1);
    lastTime = ts;
    sweepAngle = (sweepAngle + SWEEP_SPEED * dt) % (Math.PI * 2);

    ctx!.clearRect(0, 0, W, H);
    drawGrid();
    drawRings();
    drawSectors();
    drawTicks();
    drawSweep(sweepAngle);
    drawAirport();
    updateDrawAircraft(dt);

    requestAnimationFrame(frame);
  }

  // ── Init ──────────────────────────────────────────────────────────────
  resize();
  window.addEventListener('resize', resize);
  requestAnimationFrame((ts) => {
    lastTime = ts;
    requestAnimationFrame(frame);
  });
})();

export {};
