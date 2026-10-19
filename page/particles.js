const W = 1080, H = 1350, N = 1700, FPS = 30, SUB = 2;
const INK = (a) => `rgba(28,26,22,${a})`, EMBER = (a) => `rgba(210,80,47,${a})`, PAPER = '#f1ebe1';
const SANS = '"Helvetica Neue", Helvetica, Arial, sans-serif', MONO = 'Menlo, "SF Mono", monospace';

function rng(seed) { let s = seed >>> 0 || 1; return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296); }
const smooth = (x) => (x <= 0 ? 0 : x >= 1 ? 1 : x * x * (3 - 2 * x));

const SHAPES = {
  cloud: (u, r) => [(r() - 0.5) * 2.6, (r() - 0.5) * 0.5, (r() - 0.5) * 2.2],
  ring: (u, r) => { const a = u * Math.PI * 2, R = 1 + (r() - 0.5) * 0.08; return [Math.cos(a) * R, (r() - 0.5) * 0.06, Math.sin(a) * R]; },
  spiral: (u, r) => { const a = u * Math.PI * 6, R = 0.15 + u * 1.0; return [Math.cos(a) * R, (u - 0.5) * 0.5 + (r() - 0.5) * 0.04, Math.sin(a) * R]; },
  fan: (u, r) => { const b = Math.floor(u * 3), L = 0.25 + ((u * 3) % 1) * 1.05, a = b * (Math.PI * 2 / 3) + L * 0.9; return [Math.cos(a) * L, (r() - 0.5) * 0.08, Math.sin(a) * L]; },
  tower: (u, r) => { const a = u * Math.PI * 2 * 9, y = (u - 0.5) * 2; return [Math.cos(a) * 0.42, y, Math.sin(a) * 0.42]; },
  burst: (u, r) => { const k = Math.floor(u * 40), z = (k / 40) * 2 - 1, a = k * 2.399, s = Math.sqrt(1 - z * z), L = 0.25 + ((u * 40) % 1) * 1.15; return [Math.cos(a) * s * L, z * L * 0.7, Math.sin(a) * s * L]; },
  crown: (u, r) => { const a = u * Math.PI * 2; return [Math.cos(a) * 0.95, Math.abs(Math.sin(a * 5)) * 0.45 - 0.15, Math.sin(a) * 0.95]; },
  knot: (u, r) => { const a = u * Math.PI * 2 * 2, R = 0.75 + 0.3 * Math.cos(1.5 * a); return [Math.cos(a) * R, 0.3 * Math.sin(1.5 * a), Math.sin(a) * R]; },
};
const WALK = ['ring', 'spiral', 'fan', 'tower', 'burst', 'crown', 'knot'];

function targets(name) {
  const r = rng(name.length * 7919 + 13), pts = Array.from({ length: N }, (_, i) => SHAPES[name](i / N, r));
  const order = pts.map((p, i) => [Math.atan2(p[2], p[0]), p[1], i]).sort((a, b) => a[0] - b[0] || a[1] - b[1]).map((x) => x[2]);
  return order.map((i) => pts[i]);
}

function curl(x, y, z, t) {
  const a = 1.7, b = 2.3, c = 1.3;
  return [
    a * Math.cos(a * y + t) - c * Math.cos(c * z - t * 0.7),
    b * Math.cos(b * z + t * 0.8) - a * Math.cos(a * x - t * 0.6),
    c * Math.cos(c * x + t * 0.9) - b * Math.cos(b * y - t),
  ];
}

export function simulate(s, opt) {
  const tr = s.track, F = tr.frames, dur = tr.duration, dt = 1 / FPS / SUB;
  const onsets = [], per = new Float32Array(F);
  for (const n of s.notes) { const f = Math.floor(n.t * FPS); if (f >= 0 && f < F) per[f] += 1; const last = onsets.at(-1); if (last && n.t - last.t < 0.035) last.vel = Math.max(last.vel, n.vel), last.lo = Math.min(last.lo, n.midi), last.hi = Math.max(last.hi, n.midi); else onsets.push({ t: n.t, vel: n.vel, lo: n.midi, hi: n.midi }); }
  const busy = new Float32Array(F);
  for (let f = 0, e = 0; f < F; f++) { let a = 0; for (let k = f; k < Math.min(F, f + FPS); k++) a += per[k]; e += (a - e) * 0.08; busy[f] = e; }
  const peak = Math.max(1, ...busy);
  const stopAt = (t) => s.breaks.find((b) => t >= b.t0 && t < b.t1);

  const secs = tr.sections.length ? tr.sections : [{ start: 0, end: dur, name: 'Groove' }];
  let w = 0;
  const plan = secs.map((x, i) => ({ ...x, shape: i === 0 ? 'cloud' : x.name === 'Break' ? null : WALK[w++ % WALK.length] }));
  plan.forEach((x, i) => { if (!x.shape) x.shape = plan[i - 1]?.shape ?? 'ring'; });
  const T = Object.fromEntries([...new Set(plan.map((x) => x.shape))].map((n) => [n, targets(n)]));

  const spin = new Float32Array(F);
  for (let f = 0, a = 0, v = 0; f < F; f++) {
    const t = f / FPS, st = stopAt(t), want = st ? 0 : opt.cruise * (0.35 + 0.65 * busy[f] / peak);
    v += (want - v) * (want > v ? 0.1 : 0.05); a += v / FPS; spin[f] = a;
  }

  const r = rng(99), P = new Float32Array(N * 3), V = new Float32Array(N * 3), K = new Float32Array(N), D = new Float32Array(N);
  const t0 = T[plan[0].shape];
  for (let i = 0; i < N; i++) { P.set(t0[i], i * 3); K[i] = opt.k * (0.55 + r() * 0.9); D[i] = 2 * Math.sqrt(K[i]); }
  const out = new Float32Array(F * N * 3), vel = new Float32Array(F * N);
  let oi = 0;
  for (let f = 0; f < F; f++) {
    const t = f / FPS, si = Math.max(0, plan.findIndex((x) => t >= x.start && t < x.end)), sec = plan[si] ?? plan.at(-1), nxt = plan[si + 1] ?? sec;
    const prog = smooth((t - sec.start) / Math.max(0.1, sec.end - sec.start));
    const A = T[sec.shape], B = T[nxt.shape], stop = stopAt(t), life = stop ? 0 : busy[f] / peak;
    const gather = 1 - opt.gather * life;
    const kicks = [];
    while (oi < onsets.length && onsets[oi].t < t + 1 / FPS) { if (onsets[oi].t >= t) kicks.push(onsets[oi]); oi++; }
    for (let sub = 0; sub < SUB; sub++) {
      const tt = t + sub * dt;
      for (let i = 0; i < N; i++) {
        const j = i * 3, lag = (i % 17) / 17 * 0.25, q = smooth((prog - lag) / (1 - lag)) * (sec.shape === nxt.shape ? 0 : 1);
        const tx = (A[i][0] + (B[i][0] - A[i][0]) * q) * gather, ty = (A[i][1] + (B[i][1] - A[i][1]) * q) * gather, tz = (A[i][2] + (B[i][2] - A[i][2]) * q) * gather;
        const c = curl(P[j] * 1.3, P[j + 1] * 1.3, P[j + 2] * 1.3, tt * 0.6), amp = opt.flow * (0.25 + life) * (stop ? 0 : 1);
        const damp = stop ? D[i] * 2.5 : D[i];
        V[j] += (K[i] * (tx - P[j]) - damp * V[j] + c[0] * amp) * dt;
        V[j + 1] += (K[i] * (ty - P[j + 1]) - damp * V[j + 1] + c[1] * amp * 0.5) * dt;
        V[j + 2] += (K[i] * (tz - P[j + 2]) - damp * V[j + 2] + c[2] * amp) * dt;
        if (sub === 0) for (const o of kicks) {
          const band = (P[j + 1] + 1) / 2, pitch = (((o.lo + o.hi) / 2) - s.lo) / Math.max(1, s.hi - s.lo);
          const near = Math.exp(-((band - pitch) ** 2) / 0.08) * o.vel * opt.kick, rr = Math.hypot(P[j], P[j + 2]) || 1;
          V[j] += (-P[j + 2] / rr) * near; V[j + 2] += (P[j] / rr) * near;
        }
        P[j] += V[j] * dt; P[j + 1] += V[j + 1] * dt; P[j + 2] += V[j + 2] * dt;
      }
    }
    out.set(P, f * N * 3);
    for (let i = 0; i < N; i++) vel[f * N + i] = Math.hypot(V[i * 3], V[i * 3 + 1], V[i * 3 + 2]);
  }
  return { F, out, vel, spin, plan, busy, peak };
}

export function draw(ctx, s, sim, t, label) {
  const F = sim.F, x = Math.max(0, Math.min(F - 1.001, t * FPS)), f = Math.floor(x), u = x - f;
  ctx.fillStyle = PAPER; ctx.fillRect(0, 0, W, H);
  ctx.fillStyle = INK(0.95); ctx.textAlign = 'left'; ctx.font = `600 40px ${SANS}`; ctx.fillText('techguyver', 68, 75);
  ctx.textAlign = 'right'; ctx.font = `28px ${MONO}`; ctx.fillText(`T+ ${String(Math.floor(t / 60)).padStart(2, '0')}:${(t % 60).toFixed(1).padStart(4, '0')}`, 1010, 72);
  const az = ((sim.spin[f] + (sim.spin[f + 1] - sim.spin[f]) * u) * Math.PI) / 180, ca = Math.cos(az), sa = Math.sin(az);
  const el = 0.42, ce = Math.cos(el), se = Math.sin(el), cx = 540, cy = 640, S = 400, CD = 4.2;
  const a = sim.out.subarray(f * N * 3, (f + 1) * N * 3), b = sim.out.subarray((f + 1) * N * 3, (f + 2) * N * 3);
  const pts = [];
  for (let i = 0; i < N; i++) {
    const j = i * 3, px = a[j] + (b[j] - a[j]) * u, py = a[j + 1] + (b[j + 1] - a[j + 1]) * u, pz = a[j + 2] + (b[j + 2] - a[j + 2]) * u;
    const x1 = px * ca - pz * sa, z1 = px * sa + pz * ca, y2 = py * ce - z1 * se, z2 = py * se + z1 * ce, d = CD / (CD + z2);
    const v = sim.vel[f * N + i];
    pts.push([cx + x1 * S * d, cy - y2 * S * d, z2, d, v, a, b, j]);
  }
  pts.sort((p, q) => q[2] - p[2]);
  const prevF = Math.max(0, f - 2), pa = sim.out.subarray(prevF * N * 3, (prevF + 1) * N * 3);
  for (const [sx, sy, z, d, v, , , j] of pts) {
    const depth = Math.max(0.15, Math.min(1, 0.6 - z * 0.35)), hot = Math.min(1, v / 2.2);
    const qx = pa[j] * ca - pa[j + 2] * sa, qz = pa[j] * sa + pa[j + 2] * ca, qy = pa[j + 1] * ce - qz * se, qz2 = pa[j + 1] * se + qz * ce, qd = CD / (CD + qz2);
    const tx = cx + qx * S * qd, ty = cy - qy * S * qd;
    if (hot > 0.15) { ctx.strokeStyle = (hot > 0.6 ? EMBER : INK)(depth * 0.35 * hot); ctx.lineWidth = 1.4 * d; ctx.beginPath(); ctx.moveTo(tx, ty); ctx.lineTo(sx, sy); ctx.stroke(); }
    ctx.fillStyle = hot > 0.6 ? EMBER(0.5 + 0.4 * depth) : INK(depth * 0.85);
    const r = (1.6 + hot * 1.8) * d;
    ctx.fillRect(sx - r, sy - r, r * 2, r * 2);
  }
  const sec = sim.plan.find((p) => t >= p.start && t < p.end) ?? sim.plan.at(-1);
  ctx.textAlign = 'left'; ctx.font = `20px ${MONO}`; ctx.fillStyle = INK(0.5);
  ctx.fillText(`${sec.name.toUpperCase()}  ${sec.shape}  ·  life ${Math.round((sim.busy[f] / sim.peak) * 100)}%`, 72, 1150);
  ctx.fillStyle = INK(0.12); ctx.fillRect(72, 1180, W - 144, 3);
  ctx.fillStyle = EMBER(0.9); ctx.fillRect(72, 1180, (W - 144) * Math.min(1, t / s.duration), 3);
  for (const p of sim.plan) { ctx.fillStyle = INK(0.4); ctx.fillRect(72 + (W - 144) * (p.start / s.duration), 1172, 1.5, 18); }
  ctx.fillStyle = INK(0.45); ctx.font = `20px ${MONO}`; ctx.fillText(label, 72, H - 72);
}
