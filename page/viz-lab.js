import { prepare, draw as shapesDraw, TUNE, W, H, STRAND_COUNT } from '/vz-engine.js';
import { simulate, draw as particleDraw } from '/particles.js';

const INK = (a) => `rgba(28,26,22,${a})`, EMBER = (a) => `rgba(210,80,47,${a})`, PAPER = '#f1ebe1';
const SANS = '"Helvetica Neue", Helvetica, Arial, sans-serif', MONO = 'Menlo, "SF Mono", monospace';

export function load(track) {
  const lanes = [...new Set(track.notes.map((n) => n[1]))];
  const notes = track.notes.map(([t, lane, midi, dur, vel]) => ({ t, lane: lanes.indexOf(lane), midi, dur, vel }));
  const lo = Math.min(...notes.map((n) => n.midi)), hi = Math.max(...notes.map((n) => n.midi));
  const bar = 240 / (track.tempo || 120);
  const beats = track.beats.map((f) => f / track.fps);
  const breaks = track.parts.filter((p) => p.kind === 'break');
  return { track, lanes, notes, lo, hi, bar, beats, breaks, duration: track.duration, shapes: null };
}

const sounding = (n, t) => t >= n.t && t < n.t + Math.max(n.dur, 0.12);
const onsets = (s) => s.onsets ??= s.notes.reduce((o, n) => { const last = o.at(-1); if (last && n.t - last.t < 0.035) last.vel = Math.max(last.vel, n.vel); else o.push({ t: n.t, vel: n.vel }); return o; }, []);
const flash = (n, t) => (t >= n.t ? Math.exp(-(t - n.t) / 0.18) : 0);
const inBreak = (s, t) => s.breaks.some((b) => t >= b.t0 && t < b.t1);

function frame(ctx, title, s, t) {
  ctx.fillStyle = PAPER; ctx.fillRect(0, 0, W, H);
  ctx.fillStyle = INK(0.85); ctx.font = `600 30px ${SANS}`; ctx.fillText('techguyver', 72, 92);
  ctx.font = `400 22px ${MONO}`; ctx.textAlign = 'right';
  ctx.fillText(`T+ ${String(Math.floor(t / 60)).padStart(2, '0')}:${(t % 60).toFixed(1).padStart(4, '0')}`, W - 72, 92);
  ctx.textAlign = 'left'; ctx.fillStyle = INK(0.45); ctx.font = `400 20px ${MONO}`;
  ctx.fillText(title, 72, H - 72);
  const prog = Math.min(1, t / s.duration);
  ctx.fillStyle = INK(0.12); ctx.fillRect(72, H - 50, W - 144, 3);
  ctx.fillStyle = EMBER(0.9); ctx.fillRect(72, H - 50, (W - 144) * prog, 3);
  for (const b of s.breaks) { ctx.fillStyle = INK(0.35); ctx.fillRect(72 + (W - 144) * (b.t0 / s.duration), H - 56, (W - 144) * ((b.t1 - b.t0) / s.duration), 1.5); }
}

export function flight(ctx, s, t) {
  frame(ctx, 'FLIGHT  a tunnel of every note ahead, flying forward at tempo', s, t);
  const L = Math.max(1, s.lanes.length), ahead = 5, d = 0.5, F = 300;
  const sway = Math.sin(t * 0.4) * 0.12, roll = t * 0.12;
  const cx = 540 + Math.sin(t * 0.27) * 30, cy = 640;
  const P = (a, r, z) => { const k = F / (z + d); return [cx + (Math.cos(a + roll) * r + sway) * k, cy + Math.sin(a + roll) * r * k, k]; };
  const where = (n) => [((n.lane + 0.08 + 0.84 * (n.midi - s.lo) / Math.max(1, s.hi - s.lo)) / L) * Math.PI * 2, 1];
  ctx.save(); ctx.beginPath(); ctx.rect(40, 130, W - 80, H - 260); ctx.clip();
  s.beats.forEach((b, i) => {
    const z = b - t; if (z < -0.2 || z > ahead || inBreak(s, b)) return;
    const bar = i % 4 === 0, n = bar ? 72 : 24;
    for (let j = 0; j < n; j++) { const [x, y, k] = P((j / n) * Math.PI * 2, 1.25, z), r = Math.max(2.5, k / 70); ctx.fillStyle = INK(Math.min(bar ? 0.6 : 0.3, 0.1 + k / 600)); ctx.fillRect(x - r / 2, y - r / 2, r, r); }
  });
  for (const n of s.notes) {
    const z0 = n.t - t; if (z0 > ahead || z0 + n.dur < -0.25) continue;
    const [a, r] = where(n), on = sounding(n, t), fl = flash(n, t);
    for (let z = Math.max(z0, -0.25); z <= Math.min(z0 + Math.max(n.dur, 0.05), ahead); z += 0.04) {
      const [x, y, k] = P(a, r, z), q = Math.max(4, (k / 22) * (0.5 + n.vel));
      ctx.fillStyle = on ? EMBER(0.95) : INK(Math.min(0.9, 0.35 + k / 500)); ctx.fillRect(x - q / 2, y - q / 2, q, q);
    }
    if (fl > 0.03 && z0 > -0.25) { const [x, y, k] = P(a, r, Math.max(z0, 0.02)); ctx.strokeStyle = EMBER(fl * 0.9); ctx.lineWidth = 2; ctx.beginPath(); ctx.arc(x, y, (k / 18) * (1 + (1 - fl) * 1.5), 0, Math.PI * 2); ctx.stroke(); }
  }
  ctx.restore();
}

export function bloom(ctx, s, t) {
  frame(ctx, 'BLOOM  the whole track grows into one shape, a new one per song', s, t);
  const cx = W / 2, cy = 620, R0 = 70, R = 420, turn = s.bar * 2;
  const ang = (x) => (x / turn) * Math.PI * 2, rot = -ang(t) * 0.25 - Math.PI / 2;
  const pos = (n) => { const a = ang(n.t) + rot, r = R0 + (n.t / s.duration) * R + (n.midi - (s.lo + s.hi) / 2) * 1.6 + n.lane * 6; return [cx + Math.cos(a) * r, cy + Math.sin(a) * r]; };
  for (const n of s.notes) {
    const [x, y] = pos(n);
    if (n.t > t) { ctx.fillStyle = INK(0.16); ctx.fillRect(x - 2, y - 2, 4, 4); continue; }
    const fl = flash(n, t), r = 3.5 + n.vel * 3.5 + fl * 16;
    ctx.fillStyle = fl > 0.05 ? EMBER(0.35 + fl * 0.6) : INK(0.75);
    ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fill();
  }
  const a = ang(t) + rot, r = R0 + (t / s.duration) * R;
  ctx.strokeStyle = EMBER(inBreak(s, t) ? 0.3 : 0.8); ctx.lineWidth = 2;
  ctx.beginPath(); ctx.moveTo(cx + Math.cos(a) * (r - 30), cy + Math.sin(a) * (r - 30)); ctx.lineTo(cx + Math.cos(a) * (r + 30), cy + Math.sin(a) * (r + 30)); ctx.stroke();
  ctx.fillStyle = INK(0.85); ctx.beginPath(); ctx.arc(cx, cy, 6, 0, Math.PI * 2); ctx.fill();
}

const FORWARD = {
  kick(s, F, fps) {
    const cruise = FORWARD.rush(s, F, fps), az = new Float32Array(F);
    let extra = 0, eased = 0, k = 0;
    for (let f = 0; f < F; f++) {
      while (k < onsets(s).length && onsets(s)[k].t * fps < f + 1) extra += 1.5 + 2 * onsets(s)[k++].vel;
      eased += (extra - eased) * 0.3; az[f] = cruise[f] * 0.6 + eased;
    }
    return az;
  },
  ratchet(s, F, fps) {
    const az = new Float32Array(F);
    let target = 0, a = 0, k = 0;
    for (let f = 0; f < F; f++) {
      while (k < onsets(s).length && onsets(s)[k].t * fps < f + 1) target += 3 + 4 * onsets(s)[k++].vel;
      target += 2 / fps; a += (target - a) * 0.32; az[f] = a;
    }
    return az;
  },
  rush(s, F, fps) {
    const per = new Float32Array(F), az = new Float32Array(F);
    for (const n of s.notes) { const f = Math.floor(n.t * fps); if (f >= 0 && f < F) per[f] += 1; }
    let a = 0, v = 0, ahead = 0;
    for (let f = 0; f < fps && f < F; f++) ahead += per[f];
    for (let f = 0; f < F; f++) {
      const t = f / fps, stop = s.breaks.find((b) => t >= b.t0 - 0.6 && t < b.t1);
      const want = stop ? (t >= stop.t0 ? 0 : 6 * (stop.t0 - t)) : 6 + 3.2 * ahead;
      v += (want - v) * (want > v ? 0.12 : 0.06);
      if (s.breaks.some((b) => Math.abs(t - b.t1) < 0.5 / fps)) v = 6 + 3.2 * ahead + 60;
      a += v / fps; az[f] = a;
      ahead += (per[f + fps] ?? 0) - per[f];
    }
    return az;
  },
};

function gatherCurve(s, push, F, fps) {
  const g = new Float32Array(F), secs = s.track.sections;
  let v = 0;
  for (let f = 0; f < F; f++) {
    const t = f / fps, sec = secs.find((x) => t >= x.start && t < x.end) ?? secs.at(-1);
    const a = push[Math.min(F - 1, Math.floor(sec.start * fps))], z = push[Math.min(F - 1, Math.floor(sec.end * fps) - 1)];
    const want = sec.name === 'Break' ? 0 : Math.max(0, Math.min(1, (push[f] - a) / Math.max(1e-6, z - a)));
    v += (want - v) * (want > v ? 0.2 : 0.08); g[f] = v;
  }
  return g;
}

function story(opts) {
  return (ctx, s, t) => {
    const key = `story_${JSON.stringify(opts)}`;
    if (!s[key]) {
      const st = prepare(s.track), F = st.F, fps = s.track.fps, push = FORWARD.rush(s, F, fps);
      for (let f = 0; f < F; f++) { st.az[f] = ((push[f] % 360) + 360) % 360; st.breath[f] = 0; st.flip[f] = 0; st.rot[f] = 0; st.lift[f] = 0; }
      st.push = push; st.flow = push; st.gather = gatherCurve(s, push, F, fps);
      s[key] = st;
    }
    const saved = { ...TUNE }; Object.assign(TUNE, opts);
    shapesDraw(ctx, s[key], Math.min(t, s.duration - 0.01), { title: 'techguyver' });
    Object.assign(TUNE, saved);
  };
}
export const gather = story({ gather: 0.45, flow: 1 }), morphing = story({ slowMorph: 1, flow: 1 }), both = story({ gather: 0.4, slowMorph: 1, flow: 1 });

function forwardShapes(kind) {
  return (ctx, s, t) => {
    const key = `shapes_${kind}`;
    if (!s[key]) {
      const st = prepare(s.track), F = st.F, fps = s.track.fps;
      const az = FORWARD[kind](s, F, fps);
      for (let f = 0; f < F; f++) { st.az[f] = ((az[f] % 360) + 360) % 360; st.breath[f] = 0; st.flip[f] = 0; st.rot[f] = 0; st.lift[f] = 0; }
      s[key] = st;
    }
    shapesDraw(ctx, s[key], Math.min(t, s.duration - 0.01), { title: 'techguyver' });
  };
}
export const kick = forwardShapes('kick'), ratchet = forwardShapes('ratchet'), rush = forwardShapes('rush');

const BOOST = { breathAmp: 0.14, flipAmp: 0.22, hatsJitter: 0.09, hitRelease: 0.88, hitAttack: 0.45 };
export function shapes(ctx, s, t) {
  if (!s.shapes) {
    const tr = s.track, F = tr.frames, hits = { kick: new Array(F).fill(0), snare: new Array(F).fill(0), hats: new Array(F).fill(0) };
    const put = (k, time, v) => { const f = Math.floor(time * tr.fps); if (f >= 0 && f < F) hits[k][f] = Math.max(hits[k][f], v); };
    for (const [time, k, v] of tr.drums) put(k, time, v);
    for (const n of s.notes) put(n.midi < 52 ? 'kick' : n.midi < 72 ? 'snare' : 'hats', n.t, n.vel * (n.midi < 52 ? 1 : 0.8));
    s.shapes = prepare({ ...tr, hits, hitFrames: Object.fromEntries(Object.entries(hits).map(([k, v]) => [k, v.flatMap((x, i) => (x > 0.05 ? [i] : []))])) });
  }
  const saved = { ...TUNE }; Object.assign(TUNE, BOOST);
  shapesDraw(ctx, s.shapes, Math.min(t, s.duration - 0.01), { title: 'techguyver' });
  Object.assign(TUNE, saved);
  ctx.setTransform(ctx.canvas.width / W, 0, 0, ctx.canvas.height / H, 0, 0); ctx.textAlign = 'left';
  ctx.fillStyle = PAPER; ctx.fillRect(40, H - 96, W - 80, 40);
  ctx.fillStyle = INK(0.45); ctx.font = `400 20px ${MONO}`; ctx.fillText('SHAPES  today\'s look, every note pulses it, shape per spoken line', 72, H - 72);
}

function particles(opt, label) {
  return (ctx, s, t) => {
    const key = `p_${label}`;
    s[key] ??= simulate(s, opt);
    particleDraw(ctx, s, s[key], Math.min(t, s.duration - 0.01), label);
  };
}
export const calm = particles({ k: 6, cruise: 55, gather: 0.25, flow: 0.35, kick: 0.9 }, 'D1 PARTICLES  calm');
export const lively = particles({ k: 10, cruise: 70, gather: 0.35, flow: 0.8, kick: 1.8 }, 'D2 PARTICLES  lively');

function noteMarks(st, s) {
  const F = st.F, fps = s.track.fps, N = STRAND_COUNT, L = Math.max(1, s.lanes.length), act = new Float32Array(F * N), age = new Float32Array(F * N).fill(9);
  const span = Math.max(1, s.hi - s.lo), hold = Math.round(0.4 * fps);
  for (const n of s.notes) {
    const f0 = Math.round(n.t * fps), c = Math.floor(((n.lane + 0.15 + 0.7 * (n.midi - s.lo) / span) / L) * N);
    for (let d = -2; d <= 2; d++) {
      const i = (((c + d * 3) % N) + N) % N, w = n.vel * (1 - Math.abs(d) * 0.2);
      for (let k = 0; k <= hold; k++) {
        const f = f0 + k; if (f < 0 || f >= F) continue;
        const v = w * Math.exp(-k / fps / 0.18);
        if (v > act[f * N + i]) { act[f * N + i] = v; age[f * N + i] = k / fps; }
      }
    }
  }
  st.act = act; st.age = age;
  const hits = {}, rows = s.lanes.slice(0, 5).map((name, li) => {
    const h = new Array(F).fill(0);
    for (const n of s.notes) if (n.lane === li) { const f = Math.floor(n.t * fps); if (f >= 0 && f < F) h[f] = Math.max(h[f], n.vel); }
    hits[`lane${li}`] = h;
    return { key: `lane${li}`, name: name[0].toUpperCase() + name.slice(1), to: 'marks', kind: 'hits' };
  });
  st.track = { ...st.track, hits: { ...st.track.hits, ...hits } };
  st.rows = [{ key: 'vocal', name: 'Voice', to: 'speed', kind: 'curve' }, ...rows];
}

function marked(mode) {
  return (ctx, s, t, title = 'techguyver') => {
    const key = `mark_${mode}`;
    if (!s[key]) {
      const st = prepare(s.track), F = st.F, fps = s.track.fps, az = FORWARD.rush(s, F, fps);
      for (let f = 0; f < F; f++) { st.az[f] = ((az[f] % 360) + 360) % 360; st.breath[f] = 0; st.flip[f] = 0; st.rot[f] = 0; st.lift[f] = 0; }
      noteMarks(st, s);
      s[key] = st;
    }
    const saved = TUNE.marks; TUNE.marks = mode;
    shapesDraw(ctx, s[key], Math.min(t, s.duration - 0.01), { title });
    TUNE.marks = saved;
  };
}
export const glow = marked('glow'), bead = marked('bead'), spark = marked('spark');
