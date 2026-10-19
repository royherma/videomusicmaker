// Music Motion engine: draw(ctx, t) is a pure function of time + track.json, so preview and
// frame-by-frame render produce identical pictures.

export const W = 1080, H = 1350;
export const SHAPES = ["Dots", "Ring", "Spiral", "Fan", "Tower", "Burst", "Crown", "String"];
export const STEMS = [
  { key: "bass", name: "Bass", to: "camera", kind: "curve" },
  { key: "vocal", name: "Vocal", to: "lift", kind: "curve" },
  { key: "keys", name: "Keys", to: "rotation", kind: "curve" },
  { key: "kick", name: "Kick", to: "breath", kind: "hits" },
  { key: "snare", name: "Snare", to: "flip", kind: "hits" },
  { key: "hats", name: "Hi-hats", to: "tick", kind: "hits" },
];
// Shapes walk this list in order, two per long section; quiet sections fall back to Ring, the ending to Ring then Dots.
const WALK = ["Ring", "Spiral", "Fan", "Tower", "Burst", "Crown", "String"];
const QUIET = /break|breakdown|bridge/i, HOLD = /stab/i;
// Camera elevation each shape settles at, and the extra spin it makes on arrival (measured off the reference).
export const POSE = {
  Dots: { el: 79, spin: -90, rate: 3 }, Ring: { el: 74, spin: 0, rate: 12 }, Spiral: { el: 38, spin: 0, rate: 18 },
  Fan: { el: 12, spin: 0, rate: 13 }, Tower: { el: 61, spin: 150, rate: 3 }, Burst: { el: 30, spin: -60, rate: 20 },
  Crown: { el: 17, spin: 0, rate: 16 }, String: { el: 50, spin: 40, rate: 5 },
};
export const TUNE = { marks: "", gather: 0, slowMorph: 0, flow: 0, startDelay: 0, morph: 1.6, labelAt: 0.2, camDur: 1.8, spinDur: 1.0, azBase: 0.3, bassGate: 3, bassSec: 1, secondAtBars: 5, liftGain: 1, ringLowEl: 55, liftEl: 0, towerRoll0: 60, towerRoll: 30, towerY: -1.1, stringSteps: 3, stringPhase: 0, stringR: 1.0, hitAttack: 0.25, hitRelease: 0.94, breathAmp: 0.03, flipAmp: 0.06, hatsJitter: 0, stringEase: 0.8, keysSec: 0.8, rotW: 3 };

const N = 144;
export const STRAND_COUNT = N;
const CAM_DIST = 7;
const INK = [28, 26, 22], PAPER = "#f1ebe1";
const SANS = '"Helvetica Neue", Helvetica, Arial, sans-serif';
const MONO = 'Menlo, "SF Mono", monospace';
const VIEW = { cx: 540, cy: 480, top: 150, bottom: 800, scale: 300 };
const PANEL = { x0: 365, x1: 985, labelY: 916, rowY0: 965, rowGap: 46, top: 925, bottom: 1212 };

function rng(seed) {
  let s = seed >>> 0 || 1;
  s ^= s << 13; s ^= s >>> 17; s ^= s << 5; s = (s * 2654435761) >>> 0;
  return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296);
}
const ease = (x) => (x <= 0 ? 0 : x >= 1 ? 1 : x * x * (3 - 2 * x));
const lerp = (a, b, u) => a + (b - a) * u;

function strand(shape, i) {
  const r = rng(i * 7919 + shape.length * 104729);
  const k = i / N, th = k * Math.PI * 2;
  const P = (x, y, z) => [x, y, z];
  switch (shape) {
    case "Dots": {
      const p = P((r() - 0.5) * 3.6, (r() - 0.5) * 0.6, (r() - 0.5) * 3.0);
      return { a: p, b: p.slice(), w: 0, dot: 1 };
    }
    case "Ring": {
      const t = (Math.floor(i / 3) / (N / 3)) * Math.PI * 2 + (i % 3) * 0.035;
      const out = i % 3 === 0 ? 0.64 : 0.56;
      return { a: P(Math.cos(t) * 0.42, 0, Math.sin(t) * 0.42), b: P(Math.cos(t) * out, 0, Math.sin(t) * out), w: 0.004, arrow: i % 3 === 0 ? 1 : 0, rank: (i * 37) % N };
    }
    case "Spiral": {
      const o = 1.35 + r() * 0.25;
      return { a: P(Math.cos(th) * 0.36, 0, Math.sin(th) * 0.36), b: P(Math.cos(th + 0.35) * o, 0, Math.sin(th + 0.35) * o), w: 0.01 };
    }
    case "Fan": {
      if (i % 4 === 3) {
        const t = Math.PI * ((Math.floor(i / 4) / (N / 4)) * 0.9 + 0.05);
        return { a: P(-Math.cos(t) * 0.4, Math.sin(t) * 0.4, 0), b: P(-Math.cos(t) * 1.05, Math.sin(t) * 1.05, 0), w: 0.004 };
      }
      const blade = i % 3, j = (i % 48) / 48, t = blade * (Math.PI * 2 / 3) + (j - 0.5) * 0.9, o = 1.0 + r() * 0.15;
      return { a: P(Math.cos(t) * 0.3, 0, Math.sin(t) * 0.3), b: P(Math.cos(t) * o, 0, Math.sin(t) * o), w: 0.012 };
    }
    case "Tower": {
      const ray = Math.floor(i / 4), t = Math.PI * ((ray / (N / 4)) * 0.98 + 0.01), o = 1.9 + r() * 0.2;
      if (i % 4 === 1) return { a: P(-Math.cos(t) * 0.3, Math.sin(t) * 0.3, 0), b: P(-Math.cos(t) * 0.5, Math.sin(t) * 0.5, 0), w: 0.004, face: 1 };
      if (i % 4 === 0) return { a: P(-Math.cos(t) * 0.7, Math.sin(t) * 0.7, 0), b: P(-Math.cos(t) * o, Math.sin(t) * o, 0), w: 0.02, face: 1 };
      return { a: P(-Math.cos(t) * 0.7, Math.sin(t) * 0.7, 0), b: P(-Math.cos(t) * o, Math.sin(t) * o, 0), w: 0.02, face: 1, hide: 1 };
    }
    case "Burst": {
      const u = r() * 2 - 1, a = r() * Math.PI * 2, s = Math.sqrt(1 - u * u), len = 0.5 + r() * 1.1;
      const d = [Math.cos(a) * s, u * 0.8, Math.sin(a) * s];
      return { a: d.map((v) => v * 0.2), b: d.map((v) => v * len * 0.8), w: 0.004 };
    }
    case "Crown": {
      return { a: P(Math.cos(th) * 1.15, -0.5, Math.sin(th) * 1.15), b: P(Math.cos(th) * 1.15, 1.6, Math.sin(th) * 1.15), w: 0.006 };
    }
    case "String": {
      return { a: P(Math.cos(th) * 1.3, 0, Math.sin(th) * 1.3), b: P(Math.cos(th * 2) * 1.3, 0, Math.sin(th * 2) * 1.3), w: 0.003, times: 1 };
    }
  }
}

const STRANDS = Object.fromEntries(SHAPES.map((s) => [s, Array.from({ length: N }, (_, i) => strand(s, i))]));
const NEAREST = STRANDS.Dots.map((d, i) => {
  let best = -1, bd = Infinity;
  STRANDS.Dots.forEach((o, j) => { const dd = (o.a[0] - d.a[0]) ** 2 + (o.a[2] - d.a[2]) ** 2; if (j !== i && dd < bd) { bd = dd; best = j; } });
  return best;
});
const DENSITY = { Dots: 0, Ring: 0.45, Spiral: 1.1, Fan: 1.5, Tower: 0.9, Burst: 0.6, Crown: 0.75, String: 1.15 };

const JITTER = (() => {
  const r = rng(42), out = new Float32Array(4096 * 3);
  for (let i = 0; i < 4096; i++) {
    const g = (r() + r() + r() - 1.5) * 1.15;
    out[i * 3] = r(); out[i * 3 + 1] = g; out[i * 3 + 2] = r();
  }
  return out;
})();

function buildSchedule(track) {
  const bar = (4 * 60) / (track.tempo || 120), out = [];
  let k = 0;
  const walk = () => { let sh = WALK[k++ % WALK.length]; if (sh === out.at(-1)?.shape) sh = WALK[k++ % WALK.length]; return sh; };
  track.sections.forEach((s, si) => {
    const len = s.end - s.start, last = si === track.sections.length - 1;
    if (si === 0) return out.push({ t: s.start, shape: "Dots" });
    if (last) { out.push({ t: s.start, shape: out.at(-1)?.shape === "Ring" ? walk() : "Ring" }); return out.push({ t: s.start + Math.min(3 * bar, len * 0.6), shape: "Dots" }); }
    if (QUIET.test(s.name)) return out.push({ t: s.start, shape: "Ring", quiet: true });
    if (HOLD.test(s.name) && out.length) return;
    out.push({ t: s.start, shape: walk() });
    if (len >= 7 * bar) out.push({ t: s.start + Math.min(TUNE.secondAtBars * bar, len * 0.65), shape: walk() });
  });
  return out;
}

export function prepare(track) {
  const F = track.frames, fps = track.fps, c = track.curves, h = track.hits;
  const az = new Float32Array(F), el = new Float32Array(F), rot = new Float32Array(F);
  const breath = new Float32Array(F), flip = new Float32Array(F), tick = new Float32Array(F), lift = new Float32Array(F);
  const schedule = buildSchedule(track);
  schedule.forEach((e, i) => { if (i > 0) e.t += TUNE.startDelay; });
  let a = 0, r = 0, rv = 0, keysS = c.keys[0] ?? 0.5, b = 0, fl = 0, tk = 0, lf = 0, bT = 0, flT = 0, tkT = 0, bassS = 0, kickRecent = 0, si = 0, elFrom = POSE.Dots.el, e = POSE.Dots.el;
  for (let f = 0; f < F; f++) {
    const t = f / fps;
    if (si + 1 < schedule.length && schedule[si + 1].t <= t) { si++; elFrom = e; }
    const cur = schedule[si], since = t - cur.t, pose = POSE[cur.shape];
    bassS += (c.bass[f] - bassS) / (fps * TUNE.bassSec);
    const ringEl = lerp(pose.el, TUNE.ringLowEl, ease(since / ((schedule[si + 1]?.t ?? t + 1) - cur.t)) * Math.min(1, bassS * 3));
    const target = (cur.shape === "Ring" ? ringEl : pose.el) + lf * TUNE.liftEl;
    e = si === 0 ? pose.el : lerp(elFrom, target, ease(since / TUNE.camDur));
    const su = (since - 0.4) / TUNE.spinDur;
    const spin = si === 0 || su <= 0 || su >= 1 ? 0 : (pose.spin / (TUNE.spinDur * fps)) * 2 * Math.sin(Math.PI * su) ** 2;
    a += (TUNE.azBase + pose.rate * Math.min(1, bassS * TUNE.bassGate)) / fps + spin;
    keysS += (c.keys[f] - keysS) / (fps * TUNE.keysSec);
    rv += (TUNE.rotW ** 2 * ((keysS - 0.5) * 20 - r) - 2 * TUNE.rotW * rv) / fps; r += rv / fps;
    bT = Math.max(h.kick[f], bT * TUNE.hitRelease);
    flT = Math.max(h.snare[f], flT * TUNE.hitRelease);
    if (h.hats[f] > 0.35) tkT += 2.5;
    b += (bT - b) * TUNE.hitAttack; fl += (flT - fl) * TUNE.hitAttack; tk += (tkT - tk) * TUNE.hitAttack;
    kickRecent = h.kick[f] > 0.2 ? fps * 2 : Math.max(0, kickRecent - 1);
    lf += (Math.min(1, c.vocal[f] * TUNE.liftGain) * (kickRecent > 0 ? 1 : 0) - lf) * 0.05;
    az[f] = ((a % 360) + 360) % 360; el[f] = e; rot[f] = r; breath[f] = b; flip[f] = fl; tick[f] = tk; lift[f] = lf;
  }
  schedule.forEach((e, i) => {
    e.end = schedule[i + 1]?.t ?? track.duration;
    e.face = az[Math.min(F - 1, Math.floor((e.t + 0.4 + TUNE.spinDur) * fps))];
  });
  return { track, F, az, el, rot, breath, flip, tick, lift, schedule, panel: null };
}

function shapeAt(st, t) {
  let i = 0;
  while (i + 1 < st.schedule.length && st.schedule[i + 1].t <= t) i++;
  const cur = st.schedule[i], prev = st.schedule[Math.max(0, i - 1)];
  const since = t - cur.t, from = i === 0 ? cur : prev;
  return { cur: since < TUNE.morph * TUNE.labelAt ? from.shape : cur.shape, to: cur.shape, prev: from.shape, since, toE: cur, fromE: from, t };
}

const yaw = (p, deg) => {
  const A = (deg * Math.PI) / 180, c = Math.cos(A), s = Math.sin(A);
  return [p[0] * c + p[2] * s, p[1], -p[0] * s + p[2] * c];
};

// Per-frame changes a shape makes to its resting strands: Tower faces the camera, String's chords
// re-thread over time, a quiet Ring starts as 2 spokes, then 8, then the full ring.
function towerPose(e, t) {
  return { roll: TUNE.towerRoll0 + TUNE.towerRoll * (t - e.t), cy: TUNE.towerY };
}

function live(S, e, i, t) {
  if (S.face) {
    const { roll, cy } = towerPose(e, t), R = (roll * Math.PI) / 180, c = Math.cos(R), s = Math.sin(R);
    const rot = (p) => [p[0] * c - p[1] * s, p[0] * s + p[1] * c + cy, 0];
    return { ...S, a: rot(S.a), b: rot(S.b) };
  }
    if (S.times) {
    const th = (i / N) * Math.PI * 2 + (TUNE.stringPhase * Math.PI) / 180, R = TUNE.stringR, x = Math.min(0.999, (t - e.t) / Math.max(1, e.end - e.t)) * TUNE.stringSteps;
    const step = Math.floor(x), mult = 2 + step + ease((x - step - (1 - TUNE.stringEase)) / TUNE.stringEase);
    return { ...S, a: [Math.cos(th) * R, 0, Math.sin(th) * R], b: [Math.cos(th * mult) * R, 0, Math.sin(th * mult) * R] };
  }
  if (e.quiet && S.rank !== undefined) {
    const since = t - e.t, spoke = i % 3 === 0 ? i / 3 : -1;
    if (since > 10) return S;
    const show = spoke >= 0 && spoke % (since < 6 ? 24 : 6) === 0;
    if (!show) return { ...S, hide: 1 };
    const d = S.a.map((v) => v / 0.42);
    return { ...S, a: d.map((v) => v * 0.33), b: d.map((v) => v * 0.85), w: 0.02, arrow: 0, thick: 1 };
  }
  return S;
}

// Screen-facing shapes (Tower) ignore the camera: blend the world projection toward a flat one.
function billboard(pw, p, k) {
  if (k <= 0) return pw;
  const sx = VIEW.cx + p[0] * VIEW.scale, sy = VIEW.cy - p[1] * VIEW.scale;
  return [lerp(pw[0], sx, k), lerp(pw[1], sy, k), lerp(pw[2], 0, k), lerp(pw[3], 1, k)];
}

function project(p, m, cam) {
  let [x, y, z] = p;
  x *= m.s; y = y * m.s + m.lift; z *= m.s;
  let x1 = x * m.cr - z * m.sr, z1 = x * m.sr + z * m.cr;
  let y1 = y * m.cf - z1 * m.sf, z2 = y * m.sf + z1 * m.cf;
  let x2 = x1 * m.ct - y1 * m.stt, y2 = x1 * m.stt + y1 * m.ct;
  let x3 = x2 * cam.ca - z2 * cam.sa, z3 = x2 * cam.sa + z2 * cam.ca;
  let y3 = y2 * cam.ce - z3 * cam.se, z4 = y2 * cam.se + z3 * cam.ce;
  const d = CAM_DIST / (CAM_DIST + z4);
  return [VIEW.cx + x3 * VIEW.scale * d, VIEW.cy - y3 * VIEW.scale * d, z4, d];
}

let paperNoise = null;
function paper(ctx) {
  if (!paperNoise) {
    paperNoise = document.createElement("canvas");
    paperNoise.width = W; paperNoise.height = H;
    const g = paperNoise.getContext("2d"), r = rng(7);
    g.fillStyle = PAPER; g.fillRect(0, 0, W, H);
    for (let i = 0; i < 26000; i++) { g.fillStyle = `rgba(80,60,30,${r() * 0.05})`; g.fillRect(r() * W, r() * H, 1.2, 1.2); }
  }
  ctx.drawImage(paperNoise, 0, 0);
}

function ink(a) { return `rgba(${INK[0]},${INK[1]},${INK[2]},${a})`; }

function drawRulers(ctx, az, el, liftV) {
  ctx.strokeStyle = ink(0.45); ctx.fillStyle = ink(0.55); ctx.lineWidth = 1;
  ctx.font = `15px ${MONO}`; ctx.textAlign = "center";
  const L = 72, R = 998, span = 160;
  ctx.beginPath();
  for (let d = Math.ceil((az - span / 2) / 5) * 5; d <= az + span / 2; d += 5) {
    const x = L + 60 + ((d - (az - span / 2)) / span) * (R - L - 120);
    const major = d % 20 === 0;
    ctx.moveTo(x, 108); ctx.lineTo(x, major ? 122 : 116);
    ctx.moveTo(x, 838); ctx.lineTo(x, major ? 850 : 845);
    if (major) ctx.fillText(String(((d % 360) + 360) % 360).padStart(3, "0").replace(/^0(?=\d\d$)/, ""), x, 140);
  }
  for (let y = 165; y <= 790; y += 34.5) { ctx.moveTo(64, y); ctx.lineTo(76, y); ctx.moveTo(1004, y); ctx.lineTo(1016, y); }
  ctx.stroke();
  ctx.textAlign = "left"; ctx.fillText("EL", 82, 140);
  ctx.textAlign = "right"; ctx.fillText("LIFT", 997, 140);
  ctx.textAlign = "left";
  const elY = 790 - (el / 90) * 625;
  ctx.fillText(String(Math.round(el / 10) * 10 || 30), 82, 377);
  ctx.textAlign = "right"; ctx.fillText(String(Math.round(liftV * 100) || 50).padStart(2, "0"), 998, 481);
  ctx.fillStyle = ink(0.9);
  ctx.beginPath(); ctx.moveTo(540, 141); ctx.lineTo(546, 151); ctx.lineTo(534, 151); ctx.fill();
  arrow(ctx, 82, Math.min(780, Math.max(170, elY)), -1);
  arrow(ctx, 1000, 785, 1);
}

function arrow(ctx, tip, y, dir) {
  ctx.strokeStyle = ink(0.9); ctx.fillStyle = ink(0.9); ctx.lineWidth = 1.4;
  ctx.beginPath(); ctx.moveTo(tip - 26 * dir, y); ctx.lineTo(tip - 6 * dir, y); ctx.stroke();
  ctx.beginPath(); ctx.moveTo(tip, y); ctx.lineTo(tip - 10 * dir, y - 5); ctx.lineTo(tip - 10 * dir, y + 5); ctx.fill();
}

function drawOrbit(ctx, m, cam) {
  ctx.fillStyle = ink(0.32);
  ctx.beginPath();
  for (let i = 0; i < 140; i++) {
    const t = (i / 140) * Math.PI * 2;
    const p = project([Math.cos(t) * 1.75, 0, Math.sin(t) * 1.75], { ...m, s: 1, lift: 0 }, cam);
    const q = project([Math.cos(t) * 1.8, 0, Math.sin(t) * 1.8], { ...m, s: 1, lift: 0 }, cam);
    if (p[1] < VIEW.top - 20 || p[1] > VIEW.bottom + 30) continue;
    const dx = q[0] - p[0], dy = q[1] - p[1];
    for (let k = 0; k < 6; k++) ctx.rect(p[0] + dx * (k / 6) + (k % 2), p[1] + dy * (k / 6), 1.1, 1.1);
  }
  ctx.fill();
}

const at = (arr, t, fps) => { if (!arr) return 0; const x = Math.max(0, Math.min(arr.length - 1, t * fps)), f = Math.floor(x), u = x - f; return arr[f] + ((arr[Math.min(arr.length - 1, f + 1)] ?? arr[f]) - arr[f]) * u; };

function drawStrands(ctx, st, f, t, sh, m, cam) {
  const fps = st.track.fps, next = st.schedule[st.schedule.indexOf(sh.toE) + 1];
  if (TUNE.slowMorph && !sh.toE.quiet) {
    if (next && !next.quiet) {
      const p0 = at(st.push, sh.toE.t, fps), p1 = at(st.push, next.t, fps), p = at(st.push, t, fps);
      sh = { ...sh, prev: sh.to, fromE: sh.toE, to: next.shape, toE: next, since: TUNE.morph * Math.max(0, Math.min(1, (p - p0) / Math.max(1e-6, p1 - p0))) };
    } else if (!sh.fromE.quiet) sh = { ...sh, prev: sh.to, fromE: sh.toE, since: TUNE.morph };
  }
  const gather = 1 - TUNE.gather * at(st.gather, t, fps), flow = TUNE.flow * at(st.flow, t, fps);
  const fromS = STRANDS[sh.prev], toS = STRANDS[sh.to];
  const morph = sh.since / TUNE.morph;
  const dens = lerp(DENSITY[sh.prev], DENSITY[sh.to], ease(morph));
  const hatsJ = st.track.hits.hats[f] * TUNE.hatsJitter;
  const buckets = [new Path2D(), new Path2D(), new Path2D()];
  const marks = [];
  const heads = new Path2D(), dots = new Path2D();
  for (let i = 0; i < N; i++) {
    const u = ease(morph * 1.5 - (i / N) * 0.5);
    const A = live(fromS[i], sh.fromE, i, t), B = live(toS[i], sh.toE, i, t);
    if ((A.hide && B.hide) || (B.hide && u >= 0.5) || (A.hide && u <= 0.5)) continue;
    let a = [0, 1, 2].map((k) => lerp(A.a[k], B.a[k], u) * gather);
    let b = [0, 1, 2].map((k) => lerp(A.b[k], B.b[k], u) * (1 + hatsJ * ((i * 37) % 7 - 3)) * gather);
    if (flow) { const sw = flow * (0.4 + 0.6 * (((i * 13) % 7) / 6)) * 0.6; a = yaw(a, sw); b = yaw(b, sw); }
    const w = lerp(A.w, B.w, u), dotness = lerp(A.dot || 0, B.dot || 0, u), arrowness = lerp(A.arrow || 0, B.arrow || 0, u);
    const bill = lerp(A.face ? 1 : 0, B.face ? 1 : 0, u);
    const pa = billboard(project(a, m, cam), a, bill), pb = billboard(project(b, m, cam), b, bill);
    const hit = st.act ? st.act[f * N + i] : 0;
    if (TUNE.marks && hit > 0.04) marks.push([a, b, hit, st.age[f * N + i], bill]);
    const dx = pb[0] - pa[0], dy = pb[1] - pa[1], L = Math.hypot(dx, dy);
    const bucket = buckets[pa[2] + pb[2] < -0.4 ? 0 : pa[2] + pb[2] < 0.6 ? 1 : 2];
    if (dotness > 0.5 || L < 2) {
      const r = 3.2 + 2 * ((i * 13) % 5) / 5;
      dots.moveTo(pb[0] + r, pb[1]); dots.arc(pb[0], pb[1], r * pb[3], 0, Math.PI * 2);
      const voc = st.track.curves.vocal[f] * dotness;
      if (voc > 0.3 && i % 2 === 0) {
        const n = project(STRANDS.Dots[NEAREST[i]].a, m, cam);
        const k = Math.min(1, (voc - 0.3) * 3);
        bucket.moveTo(pb[0], pb[1]);
        const steps = Math.floor(Math.hypot(n[0] - pb[0], n[1] - pb[1]) * k / 3);
        for (let s = 0; s < steps; s++) bucket.rect(lerp(pb[0], n[0], (s / steps) * k), lerp(pb[1], n[1], (s / steps) * k), 1.2, 1.2);
      }
      continue;
    }
    const nx = -dy / L, ny = dx / L;
    const count = Math.min(600, Math.floor(L * dens * (B.thick && u > 0.5 ? 3 : 1)));
    const off = (i * 97) % 3800, wpx = w * VIEW.scale;
    for (let k = 0; k < count; k++) {
      const j = (off + k) * 3, uu = flow ? (JITTER[j] + flow * 0.004 * (0.6 + JITTER[j + 2])) % 1 : JITTER[j], spread = wpx * (0.4 + uu) * JITTER[j + 1];
      bucket.rect(pa[0] + dx * uu + nx * spread, pa[1] + dy * uu + ny * spread, 1.25, 1.25);
    }
    if (arrowness > 0.3) {
      const hx = dx / L, hy = dy / L, s = 7 * arrowness;
      heads.moveTo(pb[0] + hx * s, pb[1] + hy * s);
      heads.lineTo(pb[0] - hx * s + nx * s * 0.55, pb[1] - hy * s + ny * s * 0.55);
      heads.lineTo(pb[0] - hx * s - nx * s * 0.55, pb[1] - hy * s - ny * s * 0.55);
      heads.closePath();
    }
  }
  ctx.save();
  ctx.beginPath(); ctx.rect(72, VIEW.top - 25, 932, VIEW.bottom - VIEW.top + 20); ctx.clip();
  [0.35, 0.6, 0.85].forEach((a, k) => { ctx.fillStyle = ink(a); ctx.fill(buckets[k]); });
  ctx.fillStyle = ink(0.85); ctx.fill(heads); ctx.fill(dots);
  if (marks.length) drawMarks(ctx, marks, m, cam);
  ctx.restore();
}

const EMBER = (a) => `rgba(210,80,47,${a})`;
function drawMarks(ctx, marks, m, cam) {
  const P = (p, bill) => billboard(project(p, m, cam), p, bill);
  for (const [a, b, hit, age, bill] of marks) {
    const u = Math.min(1, age / 0.4);
    if (TUNE.marks === "glow") {
      const pa = P(a, bill), pb = P(b, bill), L = Math.hypot(pb[0] - pa[0], pb[1] - pa[1]);
      ctx.fillStyle = ink(Math.min(0.95, 0.25 + hit * 0.75));
      if (L < 3) { ctx.beginPath(); ctx.arc(pb[0], pb[1], 3 + 4 * hit, 0, Math.PI * 2); ctx.fill(); continue; }
      const n = Math.min(120, Math.floor(L / 3));
      for (let k = 0; k <= n; k++) ctx.fillRect(pa[0] + (pb[0] - pa[0]) * (k / n) - 1.1, pa[1] + (pb[1] - pa[1]) * (k / n) - 1.1, 2.2, 2.2);
    } else if (TUNE.marks === "bead") {
      const q = [0, 1, 2].map((k) => a[k] + (b[k] - a[k]) * (0.1 + 1.1 * u)), pq = P(q, bill);
      ctx.fillStyle = EMBER(Math.min(0.95, 0.35 + hit)); ctx.beginPath(); ctx.arc(pq[0], pq[1], (3 + 6 * hit) * pq[3], 0, Math.PI * 2); ctx.fill();
      const tail = [0, 1, 2].map((k) => a[k] + (b[k] - a[k]) * Math.max(0, 1.1 * u - 0.15)), pt = P(tail, bill);
      ctx.strokeStyle = EMBER(hit * 0.6); ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(pt[0], pt[1]); ctx.lineTo(pq[0], pq[1]); ctx.stroke();
    } else if (TUNE.marks === "spark") {
      const r = Math.hypot(b[0], b[2]) || 1, tan = [b[2] / r, 0, -b[0] / r];
      for (let k = 0; k < 3; k++) {
        const d = u * (0.18 + 0.12 * k), q = [b[0] * (1 + d * 0.5) + tan[0] * d, b[1] + (k - 1) * d * 0.25, b[2] * (1 + d * 0.5) + tan[2] * d], pq = P(q, bill);
        ctx.fillStyle = EMBER(Math.min(0.95, hit * (1 - k * 0.25))); ctx.fillRect(pq[0] - 2.5, pq[1] - 2.5, 5, 5);
      }
      const pb = P(b, bill); ctx.fillStyle = EMBER(hit * 0.8); ctx.beginPath(); ctx.arc(pb[0], pb[1], 3 + 4 * hit, 0, Math.PI * 2); ctx.fill();
    }
  }
}


function drawCore(ctx, m, cam, breath, bill) {
  const r = 0.33 * m.s;
  const c = billboard(project([0, 0, 0], { ...m, s: 1 }, cam), [0, TUNE.towerY, 0], bill);
  const ry = r * VIEW.scale * c[3] * (0.35 + 0.65 * Math.abs(Math.sin((cam.el * Math.PI) / 180)));
  ctx.fillStyle = PAPER;
  ctx.beginPath(); ctx.ellipse(c[0], c[1], r * VIEW.scale * c[3] * 0.8, ry * 0.75, 0, 0, Math.PI * 2); ctx.fill();
  const s = 1 + breath * TUNE.breathAmp * 2;
  ctx.save(); ctx.translate(c[0], c[1]); ctx.scale(s, s);
  ctx.strokeStyle = ink(0.95); ctx.lineWidth = 1.6;
  ctx.beginPath();
  for (let k = 0; k < 3; k++) {
    const a = (k / 3) * Math.PI;
    ctx.moveTo(Math.cos(a) * 16, Math.sin(a) * 16); ctx.lineTo(-Math.cos(a) * 16, -Math.sin(a) * 16);
  }
  ctx.moveTo(10, 0); ctx.arc(0, 0, 10, 0, Math.PI * 2);
  ctx.stroke(); ctx.restore();
  return c;
}

function drawReadout(ctx, cur, az, el, liftV) {
  ctx.font = `15px ${MONO}`; ctx.textAlign = "left";
  let x = 82;
  for (const s of SHAPES) {
    ctx.fillStyle = s === cur ? ink(0.95) : ink(0.22);
    ctx.fillText(s, x, 825); x += ctx.measureText(s).width + 14;
  }
  ctx.textAlign = "right"; ctx.fillStyle = ink(0.75);
  ctx.fillText(`AZ ${az.toFixed(1)}   EL ${el.toFixed(1)}   LIFT ${String(Math.round(liftV * 100)).padStart(3, "0")}`, 998, 825);
}

function buildPanel(st) {
  const { track } = st, F = track.frames, cols = PANEL.x1 - PANEL.x0;
  const mk = (alpha) => {
    const c = document.createElement("canvas"); c.width = W; c.height = H;
    const g = c.getContext("2d");
    g.strokeStyle = ink(alpha); g.fillStyle = ink(alpha); g.lineWidth = 1.3;
    (st.rows ?? STEMS).forEach((stem, ri) => {
      const base = PANEL.rowY0 + ri * PANEL.rowGap + 14;
      const src = stem.kind === "curve" ? track.curves[stem.key] : track.hits[stem.key];
      if (stem.kind === "curve") {
        g.beginPath();
        for (let x = 0; x < cols; x++) {
          const f0 = Math.floor((x / cols) * F), f1 = Math.max(f0 + 1, Math.floor(((x + 1) / cols) * F));
          let v = 0; for (let f = f0; f < f1; f++) v = Math.max(v, src[f] || 0);
          const y = base - v * 30;
          x === 0 ? g.moveTo(PANEL.x0 + x, y) : g.lineTo(PANEL.x0 + x, y);
        }
        g.stroke();
      } else {
        for (let x = 0; x < cols; x++) {
          const f0 = Math.floor((x / cols) * F), f1 = Math.max(f0 + 1, Math.floor(((x + 1) / cols) * F));
          let v = 0; for (let f = f0; f < f1; f++) v = Math.max(v, src[f] || 0);
          if (v > 0.05) g.fillRect(PANEL.x0 + x, base - v ** 0.7 * 30, 2, v ** 0.7 * 30);
        }
      }
      if (stem.key === "vocal") for (const fm of track.vocalMarks || []) g.fillRect(PANEL.x0 + (fm / F) * cols, base + 8, 1.5, 8);
    });
    return c;
  };
  st.panel = { past: mk(0.95), future: mk(0.28) };
}

function drawPanel(ctx, st, f, t) {
  if (!st.panel) buildPanel(st);
  const { track } = st, dur = track.duration, X = (s) => PANEL.x0 + (s / dur) * (PANEL.x1 - PANEL.x0);
  const px = X(t);
  ctx.drawImage(st.panel.future, 0, 0);
  ctx.save(); ctx.beginPath(); ctx.rect(0, PANEL.top - 20, px, PANEL.bottom - PANEL.top + 40); ctx.clip();
  ctx.drawImage(st.panel.past, 0, 0); ctx.restore();

  ctx.font = `15px ${SANS}`; ctx.textAlign = "left"; ctx.lineWidth = 1;
  const cur = track.sections.findIndex((s) => t >= s.start && t < s.end);
  let lastLabelEnd = -1;
  track.sections.forEach((s, i) => {
    const x = X(s.start);
    ctx.strokeStyle = ink(0.12); ctx.beginPath(); ctx.moveTo(x, PANEL.top - 2); ctx.lineTo(x, PANEL.bottom); ctx.stroke();
    ctx.fillStyle = i === cur ? ink(0.95) : ink(0.55);
    ctx.font = `${i === cur ? "600 " : ""}15px ${SANS}`;
    if (x + 4 > lastLabelEnd || i === cur) { ctx.fillText(s.name, x + 4, PANEL.labelY); lastLabelEnd = x + 8 + ctx.measureText(s.name).width; }
    if (i === cur) {
      ctx.strokeStyle = ink(0.9); ctx.lineWidth = 1.5;
      ctx.beginPath(); ctx.moveTo(x, PANEL.labelY - 18); ctx.lineTo(X(s.end), PANEL.labelY - 18);
      ctx.moveTo(x, PANEL.top + 8); ctx.lineTo(X(s.end), PANEL.top + 8); ctx.stroke(); ctx.lineWidth = 1;
    }
  });
  ctx.strokeStyle = ink(0.9); ctx.lineWidth = 2;
  ctx.beginPath(); ctx.moveTo(px, PANEL.top - 2); ctx.lineTo(px, PANEL.bottom); ctx.stroke();

  (st.rows ?? STEMS).forEach((stem, ri) => {
    const y = PANEL.rowY0 + ri * PANEL.rowGap;
    const v = stem.kind === "curve" ? track.curves[stem.key][f] : Math.max(...track.hits[stem.key].slice(Math.max(0, f - 4), f + 1));
    ctx.fillStyle = ink(0.15 + 0.7 * Math.min(1, v * 1.4));
    ctx.beginPath(); ctx.arc(98, y - 1, 6, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = ink(0.8); ctx.font = `20px ${SANS}`; ctx.fillText(stem.name, 120, y + 6);
    ctx.fillStyle = ink(0.5); ctx.font = `15px ${MONO}`; ctx.fillText(`→ ${stem.to}`, 224, y + 6);
    ctx.fillStyle = ink(0.9); ctx.beginPath(); ctx.arc(px, y + 14, 2.6, 0, Math.PI * 2); ctx.fill();
  });

  ctx.fillStyle = ink(0.6); ctx.font = `15px ${MONO}`; ctx.textAlign = "center";
  const step = dur > 150 ? 30 : 15;
  for (let s = 0; s <= dur + 0.01; s += step) ctx.fillText(String(Math.round(s)).padStart(3, "0"), X(s), 1257);
}

export function stateAt(st, t) {
  const f = Math.max(0, Math.min(st.F - 1, Math.floor(t * st.track.fps)));
  return { shape: shapeAt(st, t).cur, az: st.az[f], el: st.el[f], lift: Math.round(st.lift[f] * 100) };
}

function sampler(st, t) {
  const x = Math.max(0, Math.min(st.F - 1, t * st.track.fps)), f = Math.floor(x), u = x - f, i = (k) => Math.max(0, Math.min(st.F - 1, f + k));
  const cr = (p0, p1, p2, p3) => p1 + 0.5 * u * (p2 - p0 + u * (2 * p0 - 5 * p1 + 4 * p2 - p3 + u * (3 * (p1 - p2) + p3 - p0)));
  const at = (a) => cr(a[i(-1)], a[f], a[i(1)], a[i(2)]), lin = (a) => a[f] + (a[i(1)] - a[f]) * u;
  const near = (v, ref) => v - 360 * Math.round((v - ref) / 360);
  const wrap = (a) => { const p1 = a[f], p0 = near(a[i(-1)], p1), p2 = near(a[i(1)], p1), p3 = near(a[i(2)], p2); return ((cr(p0, p1, p2, p3) % 360) + 360) % 360; };
  return { f, at, lin, wrap };
}

export function params(st, t) {
  const { f, at, lin, wrap } = sampler(st, t);
  return { f, az: wrap(st.az), el: at(st.el), rot: at(st.rot), breath: lin(st.breath), flip: lin(st.flip), tick: lin(st.tick), lift: at(st.lift) };
}

export function draw(ctx, st, t, opts = {}) {
  const { f, az, el, rot, breath: breathV, flip, tick, lift: liftV } = params(st, t);
  const sh = shapeAt(st, t);
  const cam = { ca: Math.cos((az * Math.PI) / 180), sa: Math.sin((az * Math.PI) / 180), ce: Math.cos((-el * Math.PI) / 180), se: Math.sin((-el * Math.PI) / 180), el };
  const rotR = (rot * Math.PI) / 180, flipR = flip * TUNE.flipAmp, tickR = (tick * Math.PI) / 180 * 0.05;
  const m = {
    s: 1 + breathV * TUNE.breathAmp, lift: liftV * 0.25,
    cr: Math.cos(rotR), sr: Math.sin(rotR), cf: Math.cos(flipR), sf: Math.sin(flipR), ct: Math.cos(tickR), stt: Math.sin(tickR),
  };
  paper(ctx);
  ctx.fillStyle = ink(0.95); ctx.textAlign = "left"; ctx.font = `600 40px ${SANS}`;
  if (opts.title) ctx.fillText(opts.title, 68, 75);
  ctx.textAlign = "right"; ctx.font = `28px ${MONO}`;
  const mm = Math.floor(t / 60), ss = (t % 60).toFixed(1).padStart(4, "0");
  ctx.fillText(`T+ ${String(mm).padStart(2, "0")}:${ss}`, 1010, 72);
  drawRulers(ctx, az, el, liftV);
  ctx.save(); ctx.beginPath(); ctx.rect(80, VIEW.top - 25, 920, VIEW.bottom - VIEW.top + 20); ctx.clip();
  drawOrbit(ctx, m, cam);
  ctx.restore();
  drawStrands(ctx, st, f, t, sh, m, cam);
  const bill = (sh.prev === "Tower" ? 1 - ease(sh.since / TUNE.morph) : 0) + (sh.to === "Tower" ? ease(sh.since / TUNE.morph) : 0);
  drawCore(ctx, m, cam, breathV, Math.min(1, bill));
  drawReadout(ctx, sh.cur, az, el, liftV);
  drawPanel(ctx, st, f, t);
}
