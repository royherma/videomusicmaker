import { prepare as vzPrepare, draw as vzDraw } from '/mm/engine.js';
import { load as vzLoad, glow as vzGlow } from '/viz-lab.js';
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);
const day = (ms) => { const d = new Date(ms), n = new Date(), y = new Date(n - 864e5); return d.toDateString() === n.toDateString() ? 'Today' : d.toDateString() === y.toDateString() ? 'Yesterday' : d.toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric' }); };
const clock = (t) => `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, '0')}`;
const store = { get: (k, d) => { try { return JSON.parse(localStorage.getItem(k)) ?? d; } catch { return d; } }, set: (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch {} } };
const LEVEL = ['#e9e1d3', '#f3c9b6', '#eda184', '#e2764f', '#c9472a'];
const HUE = ['#c9472a', '#1f6f6b', '#b98a1e', '#5b4fa8', '#2e8f57', '#a8326b', '#3a6ea5', '#7a5c2e', '#4d4d4d'];
const KEYS = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'];
const PLAY = '<svg viewBox="0 0 14 14"><path d="M3 1.5v11l9.5-5.5z" fill="currentColor"/></svg>', PAUSE = '<svg viewBox="0 0 14 14"><path d="M3 1.5h3v11H3zM8 1.5h3v11H8z" fill="currentColor"/></svg>';

let S = { videos: [], themes: [], build: { steps: [] } }, rev = '', slug = new URLSearchParams(location.search).get('v') ?? store.get('slug', null), sel = store.get('sel', {}), hear = 'both', hover = null;
let custom = store.get('custom', false), mixes = store.get('mix', {}), part = 0, draft = null, draftOf = '';
const video = () => S.videos.find((v) => v.slug === slug) ?? S.videos[0];
const isRef = (v) => !!v?.ref;

/* ---------- sound: Web Audio is the clock, the picture follows it ---------- */
const AC = new AudioContext(), cache = new Map(), gV = AC.createGain(), gM = AC.createGain();
if (navigator.audioSession) navigator.audioSession.type = 'playback'; // iPhone silent switch mutes Web Audio otherwise
const limiter = AC.createDynamicsCompressor();
limiter.threshold.value = -3; limiter.knee.value = 0; limiter.ratio.value = 20; limiter.attack.value = 0.003; limiter.release.value = 0.1;
limiter.connect(AC.destination); gV.connect(limiter); gM.connect(limiter);
const aV = AC.createAnalyser(), aM = AC.createAnalyser(), wave = new Float32Array(1024);
aV.fftSize = aM.fftSize = 1024; gV.connect(aV); gM.connect(aM);
const meter = (a) => { a.getFloatTimeDomainData(wave); let s = 0; for (const v of wave) s += v * v; const db = 10 * Math.log10(s / wave.length + 1e-12); return Math.max(0, Math.min(100, (db + 54) * 2.2)); };
const P = { playing: false, start: 0, offset: 0, voice: null, music: null };
const decode = (url) => { if (!cache.has(url)) cache.set(url, fetch(url).then((r) => { if (!r.ok) throw new Error(url); return r.arrayBuffer(); }).then((b) => AC.decodeAudioData(b))); return cache.get(url); };
const now = () => (P.playing ? AC.currentTime - P.start : P.offset);

function bed(v = video()) {
  if (!v) return null;
  if (isRef(v)) return { url: `/work/${v.slug}/music.opus`, lufs: v.ref.musicLufs, voiceLufs: v.ref.voiceLufs, under: v.ref.under, level: v.ref.level, med: v.levels?.musicMedian };
  return tryBed(v, sel[v.slug]);
}
function tryBed(v, id) {
  const t = v.tries.find((x) => x.id === id) ?? null;
  return t && { url: `/work/${v.slug}/${t.file}?m=${t.mtime}`, lufs: t.lufs, voiceLufs: t.voiceLufs, under: t.under, level: t.level, med: t.levelMedian, t };
}
const plays = (v) => (v.outline?.parts ?? []).map((p, j) => ({ ...p, j })).filter((p) => p.kind === 'play');
const inPlan = (v, t) => !!(t && v.outline && t.parts?.length === v.outline.parts.length && t.parts.every((p, i) => Math.abs(p.t0 - v.outline.parts[i].t0) < 0.02));
const FAMILIES = [['violin', 'pizz', 'wonder', 'cinematic', 'strings', 'cello'], ['combo', 'sax', 'jazz', 'lofi'], ['band', 'keys', 'folk', 'flute'], ['drive', 'pulse', 'stadium', 'focus'], ['mariachi', 'island', 'band', 'folk']];
const syllables = (w) => Math.max(1, (w.toLowerCase().match(/[aeiouy]+/g) ?? []).length);
function fifths(a, b) {
  const pc = (k) => { const [n, m] = (k ?? '').split(' '), i = KEYS.indexOf(n); return i < 0 ? null : (((m === 'minor' ? i + 3 : i) * 7) % 12); };
  const x = pc(a), y = pc(b);
  return x == null || y == null ? 3 : Math.min(Math.abs(x - y), 12 - Math.abs(x - y));
}
function paces(v) {
  return plays(v).map((p) => {
    const ws = v.speech.words.filter((w) => w.t >= p.t0 && w.t < p.t1), span = ws.length ? ws.at(-1).t + ws.at(-1).d - ws[0].t : 0;
    return { syl: ws.reduce((n, w) => n + syllables(w.w), 0), span };
  });
}
function targets(v) {
  const pc = paces(v), mean = pc.reduce((n, p) => n + p.syl, 0) / (pc.reduce((n, p) => n + p.span, 0) || 1);
  return pc.map((p) => (mean ? Math.min(132, Math.max(70, (104 * (p.span ? p.syl / p.span : mean)) / mean)) : 104));
}
function matchIds(v, anchor) {
  const pool = [...new Set(FAMILIES.filter((f) => f.includes(anchor)).flat())];
  const ready = v.tries.filter((t) => pool.includes(t.id) && t.passed && inPlan(v, t));
  if (!ready.some((t) => t.id === anchor) || ready.length < 2) return null;
  const target = targets(v);
  const js = plays(v).map((p) => p.j), cost = (t, k) => Math.abs(Math.log((t.parts[js[k]].bpm ?? t.bpm) / target[k]));
  const step = (a, b) => (a.id === b.id ? 0 : 0.06 + 0.03 * fifths(a.key, b.key));
  let rows = ready.flatMap((t) => [0, 1].map((has) => ({ t, has, c: has === +(t.id === anchor) ? cost(t, 0) : Infinity, path: [t.id] })));
  for (let k = 1; k < js.length; k++) {
    rows = ready.flatMap((t) => [0, 1].map((has) => {
      const from = rows.filter((r) => (t.id === anchor ? has === 1 : r.has === has));
      const best = from.reduce((m, r) => { const c = r.c + step(r.t, t); return c < m.c ? { c, r } : m; }, { c: Infinity, r: null });
      return { t, has, c: best.c + cost(t, k), path: best.r ? [...best.r.path, t.id] : [] };
    }));
  }
  const win = rows.filter((r) => r.has === 1).reduce((m, r) => (r.c < m.c ? r : m), { c: Infinity });
  return win.path?.length === js.length ? win.path : null;
}
let match = store.get('match', false);
function mixIds(v) {
  const m = mixes[v.slug], base = sel[v.slug];
  if (match && !isRef(v) && base) { const ids = matchIds(v, base); if (ids?.some((id) => id !== base)) return ids; }
  if (isRef(v) || !m || !base) return null;
  const ids = plays(v).map((_, k) => (m[k] && v.tries.some((t) => t.id === m[k] && inPlan(v, t)) ? m[k] : base));
  return ids.some((id) => id !== base) ? ids : null;
}
function segments(v) {
  if (isRef(v)) return [{ a: 0, b: 1e9, b0: bed(v) }];
  const ids = mixIds(v);
  if (!ids) { const b = bed(v); return b ? [{ a: 0, b: 1e9, b0: b }] : []; }
  const parts = v.outline.parts, owner = {}, out = [];
  plays(v).forEach((p, k) => { owner[p.j] = ids[k]; });
  parts.forEach((p, j) => {
    if (p.kind === 'play') return out.push({ a: p.t0, b: p.t1, id: owner[j] });
    const before = owner[Object.keys(owner).map(Number).filter((q) => q < j).pop()] ?? ids[0], after = owner[Object.keys(owner).map(Number).find((q) => q > j)] ?? before, mid = Math.max(p.t0, p.t1 - 1.6);
    out.push({ a: p.t0, b: mid, id: before }, { a: mid, b: p.t1, id: after });
  });
  out[0].a = 0; out[out.length - 1].b = 1e9;
  return out.map((s) => ({ ...s, b0: tryBed(v, s.id) }));
}
const tids = new Map();
function mixTid(ids) {
  const k = ids.join(',');
  if (!tids.has(k)) { tids.set(k, null); crypto.subtle.digest('SHA-1', new TextEncoder().encode(k)).then((b) => { tids.set(k, `mix-${[...new Uint8Array(b)].map((x) => x.toString(16).padStart(2, '0')).join('').slice(0, 6)}`); render(); }); }
  return tids.get(k);
}
const outId = (v = video()) => { const ids = v && mixIds(v); return ids ? mixTid(ids) : bed()?.t?.id; };
const idAt = (v, t) => { const s = segments(v).find((q) => t >= q.a && t < q.b); return s?.b0?.t?.id ?? null; };
const voiceDb = () => Number($('vvol').value);
const muted = () => voiceDb() <= Number($('vvol').min);
function under() { return -Number($('vol').value) + (muted() ? 0 : voiceDb()); }
const gainOf = (b) => Math.pow(10, (b.voiceLufs + Number($('vol').value) - b.lufs) / 20);
function setGains() {
  const b = bed(), at = AC.currentTime, ramp = (g, x) => { g.gain.cancelScheduledValues(at); g.gain.setTargetAtTime(x, at, 0.025); };
  ramp(gV, hear === 'music' || muted() ? 0 : Math.pow(10, voiceDb() / 20));
  ramp(gM, hear === 'voice' ? 0 : 1);
  for (const [g, bb] of P.lv ?? []) ramp(g, gainOf(bb));
  $('volOut').textContent = !b ? '' : muted() ? 'voice muted' : (under() >= 0 ? `${under().toFixed(1)} dB under voice` : `${(-under()).toFixed(1)} dB over voice`);
  $('vvolOut').textContent = muted() ? 'Muted' : `${voiceDb() > 0 ? '+' : ''}${voiceDb().toFixed(1)} dB`;
}
async function loadMusic(v) {
  const segs = segments(v), urls = [...new Set(segs.map((s) => s.b0?.url).filter(Boolean))];
  const bufs = await Promise.all(urls.map((u) => decode(u).catch(() => null)));
  return { segs, buf: Object.fromEntries(urls.map((u, i) => [u, bufs[i]])) };
}
function startMusic({ segs, buf }, t, when, fade = 0) {
  const bus = AC.createGain(), lv = new Map(), srcs = [], X = 0.015;
  bus.connect(gM); bus.gain.setValueAtTime(fade ? 0 : 1, when); if (fade) bus.gain.linearRampToValueAtTime(1, when + fade);
  P.lv = new Map();
  for (const s of segs) {
    const b = s.b0, data = b && buf[b.url];
    if (!data) continue;
    const a = Math.max(s.a, t), z = Math.min(s.b, data.duration);
    if (z <= a) continue;
    if (!lv.has(b.url)) { const g = AC.createGain(); g.gain.value = gainOf(b); g.connect(bus); lv.set(b.url, g); P.lv.set(g, b); }
    const env = AC.createGain(), src = AC.createBufferSource(), at = when + (a - t);
    env.connect(lv.get(b.url)); src.buffer = data; src.connect(env);
    env.gain.setValueAtTime(a > t ? 0 : 1, at); if (a > t) env.gain.linearRampToValueAtTime(1, at + X);
    if (s.b < data.duration) { env.gain.setValueAtTime(1, at + (z - a) - X); env.gain.linearRampToValueAtTime(0, at + (z - a)); }
    src.start(at, a, z - a + 0.001); srcs.push(src);
  }
  return { bus, srcs };
}
function stopMusic(m, at = AC.currentTime, fade = 0) {
  if (!m) return;
  m.bus.gain.cancelScheduledValues(at); m.bus.gain.setValueAtTime(m.bus.gain.value, at); m.bus.gain.linearRampToValueAtTime(0, at + fade);
  m.srcs.forEach((s) => { try { s.stop(at + fade + 0.02); } catch {} });
}
const span = (v) => (v.loop && v.outline?.loop ? v.outline.seconds : v.seconds);
function startVoice(voice, t, when, v) {
  if (!voice || t >= voice.duration) return null;
  const s = AC.createBufferSource(); s.buffer = voice; s.connect(gV);
  if (v.loop) s.start(when, t, Math.max(0, span(v) - t)); else s.start(when, t);
  return s;
}
function queueLoop(v) {
  const when = P.start + span(v);
  P.next = { voice: startVoice(P.bufs.voice, 0, when, v), music: startMusic(P.bufs.music, 0, when) };
}
function stopSources() { try { P.voice?.stop(); } catch {} try { P.next?.voice?.stop(); } catch {} P.voice = null; stopMusic(P.music); stopMusic(P.next?.music); P.music = null; P.next = null; }
async function play() {
  const v = video();
  if (!v) return;
  await AC.resume();
  const [voice, music] = await Promise.all([decode(`/work/${v.slug}/voice.opus`), loadMusic(v)]);
  stopSources();
  const t = P.offset, when = AC.currentTime + 0.05;
  P.bufs = { voice, music }; P.next = null;
  P.voice = startVoice(voice, t, when, v);
  P.music = startMusic(music, t, when);
  P.start = when - t; P.playing = true; setGains();
  const el = $('video'); if (Math.abs(el.currentTime - t) > 0.05) el.currentTime = t; el.play().catch(() => {});
  $('play').innerHTML = PAUSE;
}
async function swapMusic() {
  const v = video(), token = (P.swap = (P.swap ?? 0) + 1);
  const music = await loadMusic(v);
  if (!P.playing || token !== P.swap) return;
  const when = AC.currentTime + 0.03, F = 0.08;
  stopMusic(P.music, when, F);
  P.music = startMusic(music, when - P.start, when, F);
  if (P.bufs) P.bufs.music = music;
  if (P.next) { stopMusic(P.next.music); P.next.music = startMusic(music, 0, P.start + span(v)); }
  setGains();
}
function pause() { P.offset = now(); stopSources(); P.playing = false; $('video').pause(); $('play').innerHTML = PLAY; $('mV').style.width = $('mM').style.width = '0'; }
function seek(t) { const was = P.playing; if (was) stopSources(); P.playing = false; P.offset = Math.max(0, Math.min(t, video()?.seconds ?? 0)); $('video').currentTime = P.offset; if (was) play(); else { draw(); vzFrame(); } }
$('play').innerHTML = PLAY;
$('play').onclick = () => (P.playing ? pause() : play());
const restart = () => { seek(0); if (!P.playing) play(); };
$('back').onclick = restart;
document.addEventListener('keydown', (e) => { if (/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)) return; if (e.code === 'Space') { e.preventDefault(); P.playing ? pause() : play(); } else if (e.code === 'Home') { e.preventDefault(); restart(); } });
$('hear').onclick = (e) => { const b = e.target.closest('button'); if (!b) return; hear = b.dataset.h; [...$('hear').children].forEach((x) => x.classList.toggle('on', x === b)); setGains(); };
$('vol').oninput = () => { setGains(); mp4Buttons(); store.set(`under:${slug}`, -Number($('vol').value)); draw(); };
$('vvol').oninput = () => { setGains(); mp4Buttons(); store.set(`voice:${slug}`, voiceDb()); draw(); };

/* ---------- state ---------- */
let pageAt;
async function poll() {
  try {
    const r = await (await fetch('/api/rev', { cache: 'no-store' })).json();
    if (pageAt && r.page !== pageAt && !P.playing && !document.activeElement?.matches('input,textarea')) return location.reload();  // page code changed: an old tab misreads new server data
    pageAt ??= r.page;
    if (r.rev !== rev) { rev = r.rev; S = await (await fetch('/api/state', { cache: 'no-store' })).json(); S.videos.forEach(hideRebuilding); render(); }
  } catch {}
}
function hideRebuilding(v) {
  if (!live(v.run, v)) return;
  const done = new Set(v.run.genres.filter((g) => g.state === 'pass' || g.state === 'fail').map((g) => g.id)), redo = new Set(v.run.genres.map((g) => g.id));
  v.tries = v.tries.filter((t) => !redo.has(t.id) || done.has(t.id));
}
setInterval(poll, 1000); poll();

$('video').addEventListener('loadedmetadata', (e) => e.target.parentElement.style.setProperty('--ar', `${e.target.videoWidth}/${e.target.videoHeight}`));

function choose(s) {
  if (s === slug && $('video').src) return;
  pause(); P.offset = 0; slug = s; store.set('slug', s);
  const v = video();
  history.replaceState(null, '', `?v=${encodeURIComponent(v.slug)}`);
  $('video').src = `/video/${v.slug}`;
  $('vol').value = -store.get(`under:${s}`, isRef(v) ? v.ref.under : 10);
  $('vvol').value = store.get(`voice:${s}`, 0);
  render();
}

function render() {
  document.documentElement.style.setProperty('--clk', `-${Date.now() % 60000}ms`);
  if (!S.videos.length) { $('genres').innerHTML = '<div class="empty">Nothing read yet. The engine writes here as it goes.</div>'; renderBuild(); return; }
  if (!video() || !$('video').src) { slug = video()?.slug ?? S.videos[0].slug; return choose(slug); }
  const v = video();
  renderPicker(v);
  const ready = v.tries.length, steps = [['Speech', !!v.speech], ['Fit', !!v.outline || isRef(v)], ['Compose', ready > 0 || isRef(v)], ['Mix', v.tries.some((t) => t.score) || isRef(v)], ['Pick', !!v.pick]];
  $('flow').innerHTML = steps.map(([n, ok], i) => `<b class="${ok ? 'ok' : v.job?.running && !ok && steps.slice(0, i).every((x) => x[1]) ? 'run' : ''}">${n}</b>`).join('<span>›</span>');
  if (isRef(v)) renderFacts(v); else renderGenres(v);
  $('loop').checked = !!v.loop; $('loop').disabled = !!v.job?.stopping || isRef(v);
  $('match').checked = match; $('match').disabled = isRef(v);
  $('custom').checked = custom; $('build').hidden = custom; $('edit').hidden = !custom;
  renderBuild(); if (custom) renderEdit(v); setGains(); draw(); vzFrame();
}

function renderPicker(v) {
  const name = (x) => esc(x.title?.replace(/ \(reference\)$/, ''));
  const coming = (S.adding ?? []).find((a) => a.slug === waitFor && a.running);
  $('pickName').innerHTML = coming ? `Adding ${esc(coming.title)}...` : `${name(v)}${isRef(v) ? ' <em>reference</em>' : ''}`;
  const at = (x) => new Date(x.added).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false });
  const row = (x) => `<div class="item ${x.slug === v.slug ? 'on' : ''} ${x.job?.running ? 'busy' : ''}" data-s="${x.slug}"><b>${name(x)}</b><small>${x.job?.running ? esc(x.job.line).slice(0, 34) : isRef(x) ? clock(x.seconds) : `${at(x)} · ${x.tries.length} tracks · ${clock(x.seconds)}`}</small></div>`;
  const mine = S.videos.filter((x) => !isRef(x)).sort((a, b) => b.added - a.added), refs = S.videos.filter(isRef);
  const days = Map.groupBy(mine, (x) => day(x.added));
  const adding = (S.adding ?? []).map((a) => `<div class="item busy ${a.slug === waitFor ? 'on' : ''}"><b>${esc(a.title)}</b><small>${a.failed ? 'failed: ' : ''}${esc(a.line ?? '').slice(0, 28)} · ${Math.round((Date.now() - a.startedAt) / 1000)}s</small></div>`).join('');
  $('menuList').innerHTML = `${adding ? `<h4>Adding now</h4>${adding}` : ''}${[...days].map(([d, xs]) => `<h4>${d}</h4>${xs.map(row).join('')}`).join('')}${refs.length ? `<h4>References</h4>${refs.map(row).join('')}` : ''}`;
  if (waitFor && S.videos.some((x) => x.slug === waitFor)) { const s = waitFor; waitFor = null; $('addMsg').textContent = ''; menu(false); choose(s); }
}
let waitFor = null;
const menu = (open) => { $('menu').hidden = !(open ?? $('menu').hidden); };
$('pickBtn').onclick = (e) => { e.stopPropagation(); menu(); };
document.addEventListener('mousedown', (e) => { if (!e.target.closest('#picker')) menu(false); });
const added = async (r) => { const j = await r.json(); if (!r.ok) { $('addMsg').textContent = j.error; return; } waitFor = j.slug; $('addMsg').textContent = 'Reading the speech. The video opens here when that is done; genres fill in after.'; menu(true); rev = ''; poll(); };
$('addForm').onsubmit = (e) => { e.preventDefault(); const path = $('addPath').value.trim(); if (path) fetch('/api/add', { method: 'POST', body: JSON.stringify({ path }) }).then(added); };
addEventListener('dragover', (e) => { if ([...e.dataTransfer.items].some((i) => i.kind === 'file')) { e.preventDefault(); document.body.classList.add('dropping'); } });
addEventListener('dragleave', (e) => { if (!e.relatedTarget) document.body.classList.remove('dropping'); });
addEventListener('drop', (e) => { e.preventDefault(); document.body.classList.remove('dropping'); const f = [...e.dataTransfer.files].find((x) => /video|audio/.test(x.type) || /\.(mp4|mov|m4v|webm|mkv|mp3|wav|m4a)$/i.test(x.name)); if (!f) return; menu(true); $('addMsg').textContent = `Uploading ${f.name}...`; fetch(`/api/upload?name=${encodeURIComponent(f.name)}`, { method: 'POST', body: f }).then(added); });

const cardState = new Map(), landedAt = new Map(), LAND_MS = 1500;
const nth = (n) => (n === 1 ? 'Up next' : `${n}${['th', 'st', 'nd', 'rd'][(n % 100 > 10 && n % 100 < 14) || n % 10 > 3 ? 0 : n % 10]} in line`);
const pips = (gates, cls, labels) => `<div class="pips ${cls}">${Array.from({ length: gates?.length || 6 }, (_, i) => `<i class="${gates?.[i] ? (gates[i].ok ? 'ok' : 'no') : ''}" style="--i:${i}" title="${esc(gates?.[i]?.label ?? labels?.[i] ?? '')}"></i>`).join('')}</div>`;
function renderGenres(v) {
  $('genres').hidden = false; $('facts').hidden = true; $('deck').style.display = '';
  const cards = S.themes.map((t) => ({ theme: t, tr: v.tries.find((x) => x.id === t.id) }));
  v.tries.filter((x) => !S.themes.some((t) => t.id === x.id)).forEach((tr) => cards.push({ theme: { id: tr.id, name: tr.name, about: tr.about }, tr }));
  if ((!sel[v.slug] || !v.tries.some((t) => t.id === sel[v.slug])) && v.tries[0]) sel[v.slug] = (v.pick && v.tries.find((t) => t.id === v.pick.theme)?.id) || v.tries[0].id;
  $('midh').firstChild.textContent = 'Genres ';
  $('midn').textContent = `${v.tries.length} of ${cards.length} made${v.job?.running && !live(v.run, v) ? ` · ${v.job.line}` : ''}`;
  $('genres').classList.toggle('dense', cards.length > 6);
  $('genres').classList.toggle('auto', auto && !custom);
  $('genres').style.setProperty('--el', `${-(Date.now() - autoAt)}ms`);
  const labels = v.tries.find((t) => t.gates)?.gates.map((g) => g.label), queue = live(v.run, v) ? v.run.genres.filter((g) => g.state === 'queued') : [];
  $('genres').innerHTML = cards.map(({ theme, tr }) => {
    const rg = live(v.run, v) ? v.run.genres.find((g) => g.id === theme.id) : null, busy = rg && ['write', 'check', 'retry'].includes(rg.state), waiting = rg?.state === 'queued';
    const making = !rg && v.job?.running && (v.job.args[2] === theme.id || v.job.args[2] === 'all') && !tr, old = tr && v.outline && !inPlan(v, tr);
    const key = `${v.slug}/${theme.id}`, now = tr && !busy ? 'ready' : busy || waiting || making ? 'busy' : 'none', prev = cardState.get(key);
    cardState.set(key, now); if (now === 'ready' && prev && prev !== 'ready') landedAt.set(key, Date.now());
    const la = landedAt.get(key), landing = now === 'ready' && la && Date.now() - la < LAND_MS;
    const passN = tr?.gates ? `${tr.gates.filter((g) => g.ok).length}/${tr.gates.length}` : '';
    const badge = v.pick?.theme === theme.id ? '<em>Your pick</em>' : old ? `<em style="color:var(--gold)">Old plan</em>` : tr?.gates && !busy ? `<em class="${tr.passed ? 'pass' : 'fail'}" title="${esc(gateText(tr.gates))}">${tr.passed ? `Passed ${passN}` : `Failed ${passN}`}</em>` : tr?.edited ? '<em style="color:var(--teal)">Edited</em>' : '';
    const missed = rg?.state === 'retry' ? (rg.gates ?? labels?.map((l) => ({ label: l, ok: !rg.failed?.includes(l) }))) : null;
    const since = rg?.startedAt ? `<time data-since="${rg.startedAt}">${(Date.now() / 1000 - rg.startedAt).toFixed(1)}s</time>` : '';
    const stage = busy || making ? `<div class="prog ${rg?.state ?? 'write'}"><div class="state">${rg?.state === 'retry' ? `<span class="ring"></span><span class="lbl" title="Missed ${esc(rg.failed?.join(', ') ?? 'a check')}, rewriting">Missed “${esc(rg.failed?.[0] ?? 'a check')}” · try ${rg.attempt}</span>` : `<span class="ring"></span><span class="lbl">${rg?.state === 'check' ? 'Checking it against 6 tests' : `Writing the music${rg?.attempt > 1 ? ` · try ${rg.attempt}` : ''}`}</span>`}${since}</div>${pips(missed, rg?.state ?? 'write', labels)}</div>`
      : waiting ? `<div class="prog wait"><div class="state wait"><span class="dot"></span>${nth(queue.indexOf(rg) + 1)}<button class="btn make now" data-make="${theme.id}" title="Stop the run and write only this one now">Make it now</button></div>${pips(null, 'idle', labels)}</div>` : '';
    const n = (val) => `<b ${landing ? `data-to="${val}"` : ''}>${val}</b>`;
    const nums = tr?.score ? `<div class="nums"><span style="--i:0">${n(tr.bpm)} BPM</span><span style="--i:1">${esc(tr.key)}</span>${tr.score.cueErrorMs != null ? `<span style="--i:2" title="Biggest gap between a spoken cue and the music change">${n(tr.score.cueErrorMs)} ms</span>` : ''}${tr.score.attackMs != null ? `<span style="--i:3" title="After a full stop, time for the music to reach full level again">${n(tr.score.attackMs)} ms back in</span>` : ''}</div>` : '';
    return `<div class="g ${tr && !busy ? '' : 'off'} ${busy || making ? 'busy' : ''} ${waiting ? 'wait' : ''} ${landing ? `landing ${tr.passed === false ? 'bad' : ''}` : ''} ${tr && !busy && sel[v.slug] === tr.id ? 'on' : ''}" data-id="${tr && !busy ? tr.id : ''}" ${landing ? `data-la="${la}" style="--ld:-${Date.now() - la}ms"` : ''}>
      <h3 title="${esc(tr?.about ?? theme.about)}">${esc(theme.name)}${badge}</h3><p>${esc(tr?.about ?? theme.about)}</p>
      ${tr && !busy ? `<a class="dl" href="/work/${v.slug}/tries/${tr.id}/bed.wav?dl=${encodeURIComponent(`${v.title} - ${theme.name}`.replace(/[\/:]/g, '-') + '.wav')}" download="${esc(`${v.title} - ${theme.name}`.replace(/[\/:]/g, '-'))}.wav" title="Download this music (WAV)"><svg viewBox="0 0 14 14"><path d="M7 1.5v8M3.5 6.5 7 10l3.5-3.5M2 12.5h10" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg></a>` : ''}
      ${stage || (tr ? `${nums}<canvas data-spark="${tr.id}"></canvas>${landing && tr.gates ? pips(tr.gates, 'land') : ''}` : `<button class="btn make" data-make="${theme.id}">Make it</button>`)}</div>`;
  }).join('');
  $('genres').querySelectorAll('[data-spark]').forEach((c) => spark(c, v.tries.find((t) => t.id === c.dataset.spark)?.level ?? []));
  cardTick();
  const job = v.job;
  $('export').textContent = job?.running && ['export', 'mix'].includes(job.args[0]) ? 'Making the mp4...' : job && !job.running && job.args[0] === 'export' ? (job.failed ? 'Failed - see log' : 'mp4 done ✓') : 'Make the mp4';
  mp4Buttons(v);
  $('pick').disabled = !bed();
}

function mp4Buttons(v = video()) {
  const job = v?.job;
  const id = outId(v), t = v?.tries.find((x) => x.id === id), made = !job?.running && t && v.exports?.[id], fresh = made && Date.parse(made.at) >= t.mtime && made.under === under();
  $('mp4').hidden = !fresh; $('export').hidden = !!fresh;
  $('export').disabled = !bed() || !!job?.running || muted(); $('export').title = muted() ? 'The mp4 keeps your voice. Music on its own: the download arrow on each genre' : '';
  if (fresh) { $('mp4dl').href = `/api/mp4?slug=${v.slug}&theme=${id}`; $('reveal').title = made.file; }
}
function renderFacts(v) {
  $('genres').hidden = true; $('facts').hidden = false; $('deck').style.display = 'none';
  const r = v.ref, run = r.chords.filter((c, i) => c !== r.chords[i - 1]);
  $('midh').firstChild.textContent = 'What this music does ';
  $('midn').textContent = `measured from the video, ${clock(r.seconds)}`;
  const stops = r.breaks.map((b) => `${clock(b.t)} for ${b.d.toFixed(1)} s, back ${b.off >= 0 ? '+' : ''}${b.off.toFixed(2)} s from "${b.line.split(' ').slice(0, 5).join(' ')}..."`);
  const f = [
    [`${r.bpm} BPM`, 'Tempo'], [r.key, `Key (fit ${r.keyFit})`], [run.slice(0, 5).join(' → '), 'Chords, bar by bar'],
    [`${r.under} LU`, 'Music under the voice. Rundown runs 15-18'], [`${r.breaks.length} full stops`, stops.join(' · ') || 'None'],
    [`${Math.round(r.share.drums * 100)}% drums`, `bass ${Math.round(r.share.bass * 100)}%, the rest ${Math.round(r.share.other * 100)}%`],
    [`${Math.round((r.bands['150-400'] + r.bands['0-150']) * 100)}% under 400 Hz`, `${Math.round((r.bands['1000-2500'] + r.bands['2500-6000']) * 100)}% in the voice band 1-6 kHz`],
    [`${r.notesPerSecond} notes/s`, 'How busy it is'],
  ];
  $('facts').innerHTML = f.map(([b, s]) => `<div><b>${esc(b)}</b><span>${esc(s)}</span></div>`).join('');
}

const ICON = { ok: '<svg viewBox="0 0 10 10"><path d="M2 5.2l2 2 4-4.4" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>', fail: '<svg viewBox="0 0 10 10"><path d="M3 3l4 4M7 3l-4 4" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>' };
const STAGE = { queued: 'in line', write: 'writing', check: 'checking', retry: 'rewriting' };
const live = (run, v) => run && !run.done && !run.stoppedAt && !v.job?.stopped && (v.job?.running || Date.now() / 1000 - run.at < 90);
const gateText = (gates) => (gates ?? []).map((g) => `${g.ok ? 'Pass' : 'FAIL'}  ${g.label}${g.value != null ? ` (${g.value} ${g.unit}, limit ${g.limit})` : ''}`).join('\n');
function runClock() {
  const v = video(), run = v?.run, el = document.querySelector('#runSum time');
  if (!run || !el) return;
  el.textContent = clock((live(run, v) ? Date.now() / 1000 : run.at) - run.startedAt);
}
setInterval(runClock, 500);

function renderBuild() {
  const v = video(), run = v && !isRef(v) ? v.run : null;
  $('newRun').hidden = !v || isRef(v);
  const job = v?.job, busy = job?.running && job.args?.[0] !== 'export';
  $('newRun').textContent = busy ? (job.stopping ? 'Stopping...' : 'Stop') : 'New run';
  $('newRun').title = busy ? 'Stop after the track being written. What is written stays; Make it on any card writes just that one.' : 'Write every genre again from scratch for this video. The last run is kept in work/<video>/runs/';
  $('newRun').classList.toggle('stop', !!busy);
  $('newRun').disabled = !!job?.stopping || job?.args?.[0] === 'export';
  if (!run) {
    $('buildn').textContent = ''; $('runBar').innerHTML = '';
    $('runSum').innerHTML = job?.failed ? `<span class="why">Run failed: ${esc((job.line ?? '').replace(/^FAILED:\s*/, ''))}</span>` : v && !isRef(v) ? '<span>No run on this video yet. <b>New run</b> writes every genre and checks each one.</span>' : '<span>Reference video: measured, not written.</span>';
    $('steps').innerHTML = ''; $('stale').innerHTML = ''; return;
  }
  const gs = run.genres, passed = gs.filter((g) => g.state === 'pass').length, failed = gs.filter((g) => g.state === 'fail').length, going = live(run, v), stopped = !run.done && !going;
  $('buildn').textContent = '';
  $('runBar').innerHTML = gs.map((g) => `<i class="${g.state}" title="${esc(g.name)}: ${esc(STAGE[g.state] ?? g.state)}"></i>`).join('');
  $('runSum').innerHTML = `<b>${passed} of ${gs.length}</b><span>${run.done ? `passed every check${failed ? `, ${failed} failed` : ''}` : stopped ? 'stopped before the end' : 'written and checked'}</span><time></time>`;
  const words = v.speech?.words?.length, sentences = v.speech?.sentences?.length;
  const old = going ? [] : v.tries.filter((t) => t.engine !== S.stamps?.track), oldSpeech = v.speech?.reader !== S.stamps?.reader;
  $('stale').innerHTML = [
    oldSpeech ? `<li class="stale"><span class="ic">!</span><b>Speech was read by older code: pauses and stops may be off</b><button class="btn" data-act="reread" ${v.job?.stopping ? 'disabled' : ''}>Re-read</button></li>` : '',
    old.length ? `<li class="stale"><span class="ic">!</span><b>${old.length === v.tries.length ? 'All' : `${old.length} of ${v.tries.length}`} tracks were made by older engine code${oldSpeech ? '' : ', checks may be out of date'}</b><button class="btn" data-act="rerun" ${v.job?.stopping ? 'disabled' : ''}>New run</button></li>` : '',
  ].join('');
  const rows = [
    `<li class="ok"><span class="ic">${ICON.ok}</span><b>Read what is said</b><small>${v.speech?.noVoice ? 'no voice, music only' : `${words ?? ''} words · ${sentences ?? ''} lines`}</small></li>`,
    `<li class="ok"><span class="ic">${ICON.ok}</span><b>Plan the music</b><small>${run.plan.parts} parts · ${run.plan.stops} stop${run.plan.stops === 1 ? '' : 's'}</small></li>`,
    ...gs.map((g) => {
      const now = ['write', 'check', 'retry'].includes(g.state) && going, done = g.state === 'pass' || g.state === 'fail';
      const right = g.state === 'pass' ? `${g.gates.length}/${g.gates.length} · ${g.seconds}s` : g.state === 'fail' ? `${g.gates.filter((x) => x.ok).length}/${g.gates.length}` : now ? `${STAGE[g.state]}${g.attempt > 1 ? ` · try ${g.attempt}` : ''}` : stopped ? 'not written' : 'in line';
      const why = ((g.state === 'fail' || (g.state === 'retry' && going)) && g.failed?.length ? `<span class="why">${g.state === 'retry' ? 'Missed' : 'Failed'}: ${esc(g.failed.join(', '))}</span>` : '')
        + (g.state === 'fail' && g.unchecked?.length ? `<span class="why unchecked">Couldn't check: ${esc(g.unchecked.join('; '))}</span>` : '');
      return `<li class="${now ? 'now' : g.state}${!now && v.tries.some((t) => t.id === g.id) ? ' go' : ''}" data-g="${g.id}" title="${esc(gateText(v.tries.find((t) => t.id === g.id)?.gates))}"><span class="ic">${done ? ICON[g.state === 'pass' ? 'ok' : 'fail'] : ''}</span><b>${esc(g.name)}</b><small>${right}</small>${why}</li>`;
    }),
    run.done ? `<li class="${v.pick ? 'ok' : 'turn'}"><span class="ic">${v.pick ? ICON.ok : ''}</span><b>${v.pick ? 'Picked' : 'Your turn: listen and pick'}</b><small>${v.pick ? esc(S.themes.find((t) => t.id === v.pick.theme)?.name ?? v.pick.theme) : ''}</small></li>` : '',
  ];
  $('steps').innerHTML = rows.join('');
  $('stale').querySelectorAll('[data-act]').forEach((b) => { b.onclick = async () => { b.disabled = true; await fetch(b.dataset.act === 'reread' ? '/api/reread' : '/api/run', { method: 'POST', body: JSON.stringify({ slug: v.slug }) }); rev = ''; poll(); }; });
  runClock();
  const cur = $('steps').querySelector('li.now') ?? (run.done ? $('steps').lastElementChild : null), ol = $('steps');
  if (cur) { const top = cur.offsetTop - ol.offsetTop, h = cur.offsetHeight; if (top < ol.scrollTop || top + h > ol.scrollTop + ol.clientHeight) ol.scrollTop = top - ol.clientHeight / 2 + h; }
}
$('steps').addEventListener('click', (e) => {
  const id = e.target.closest('li.go')?.dataset.g, v = video();
  if (!id || !$('genres').querySelector(`.g[data-id="${id}"]`)) return;
  autoAt = Date.now(); sel[v.slug] = id; store.set('sel', sel); render(); if (P.playing) swapMusic();
  const card = $('genres').querySelector(`.g[data-id="${id}"]`);
  card.scrollIntoView({ block: 'nearest', inline: 'nearest', behavior: 'smooth' });
  card.animate([{ boxShadow: '0 0 0 4px rgba(210,80,47,.45)' }, { boxShadow: '0 0 0 1px var(--ember)' }], { duration: 900, easing: 'ease-out' });
});
$('newRun').onclick = async () => {
  const v = video(); if (!v) return;
  $('newRun').disabled = true;
  const stop = v.job?.running && v.job.args?.[0] !== 'export';
  await fetch(stop ? '/api/stop' : '/api/run', { method: 'POST', body: JSON.stringify({ slug: v.slug, first: sel[v.slug] }) });
  rev = ''; poll();
};

/* ---------- drag to resize the columns and the score ---------- */
const SIZE = { l: [180, 560], r: [240, 520], sh: [180, 520] };
function setSize(k, px) { const [lo, hi] = SIZE[k]; px = Math.round(Math.max(lo, Math.min(hi, px))); document.querySelector('main').style.setProperty(`--${k}`, `${px}px`); return px; }
const sizes = store.get('sizes', {}); for (const k in sizes) setSize(k, sizes[k]);
for (const [id, k, axis, sign] of [['rzL', 'l', 'x', 1], ['rzR', 'r', 'x', -1], ['rzS', 'sh', 'y', -1]]) {
  $(id).addEventListener('pointerdown', (e) => {
    e.preventDefault();
    const el = $(id), main = document.querySelector('main'), from = parseFloat(getComputedStyle(main).getPropertyValue(`--${k}`)), at = axis === 'x' ? e.clientX : e.clientY;
    el.setPointerCapture(e.pointerId); el.classList.add('drag'); document.body.classList.add('resizing'); document.body.style.cursor = getComputedStyle(el).cursor;
    const move = (m) => { sizes[k] = setSize(k, from + sign * ((axis === 'x' ? m.clientX : m.clientY) - at)); draw(); };
    const up = () => { el.removeEventListener('pointermove', move); el.classList.remove('drag'); document.body.classList.remove('resizing'); document.body.style.cursor = ''; store.set('sizes', sizes); draw(); vzFrame(); };
    el.addEventListener('pointermove', move); el.addEventListener('pointerup', up, { once: true });
  });
  $(id).addEventListener('dblclick', () => { delete sizes[k]; document.querySelector('main').style.removeProperty(`--${k}`); store.set('sizes', sizes); draw(); });
}
new ResizeObserver(() => { const w = $('genres').clientWidth; $('genres').style.setProperty('--gc', w > 760 ? 3 : w > 440 ? 2 : 1); }).observe($('genres'));
new ResizeObserver(() => { const side = $('side'), column = getComputedStyle(side).flexDirection === 'column' && !matchMedia('(max-width:700px)').matches; $('build').classList.toggle('squeezed', column && side.clientHeight - $('vizCard').offsetHeight - 12 < 170); }).observe($('side'));

const hueOf = (id) => { const i = S.themes.findIndex((t) => t.id === id); return HUE[(i < 0 ? S.themes.length + (video()?.tries.findIndex((t) => t.id === id) ?? 0) : i) % HUE.length]; };
const same = (a, b) => JSON.stringify(a ?? {}) === JSON.stringify(b ?? {});
function renderEdit(v) {
  if (isRef(v) || !v.outline) { $('editn').textContent = ''; $('editBody').innerHTML = '<p class="note">References are measured, not made. Pick one of your videos to change its music.</p>'; return; }
  if (draftOf !== v.slug || same(draft, draftSaved) || !draft) { draft = structuredClone(v.edits ?? {}); draftSaved = structuredClone(v.edits ?? {}); draftOf = v.slug; }
  const ps = plays(v), p = ps[Math.min(part, ps.length - 1)] ?? ps[0], base = v.tries.find((t) => t.id === sel[v.slug]), theme = S.themes.find((t) => t.id === base?.id);
  const ready = v.tries.filter((t) => inPlan(v, t)), m = mixes[v.slug] ?? [], cur = m[part] && ready.some((t) => t.id === m[part]) ? m[part] : '';
  const lvKey = p.t0.toFixed(2), lv = draft.levels?.[lvKey] ?? p.level;
  const on = (s) => draft.breaks?.[s.t.toFixed(2)] ?? v.outline.parts.some((q) => q.kind === 'break' && Math.abs(q.t0 - (s.t - 0.04)) < 0.03), turns = v.speech.sentences.slice(0, -1).filter((s) => s.t > 2 && (s.pivot || on(s) || (s.n <= 8 && s.end - s.t <= 3.2)));
  const g = (draft.genres ?? {})[base?.id] ?? {}, bpm = g.bpm ?? base?.bpm, key = g.key ?? theme?.key, mute = g.mute ?? [];
  const dirty = !same(draft, draftSaved), outlineDirty = !same({ b: draft.breaks, l: draft.levels }, { b: draftSaved.breaks, l: draftSaved.levels });
  $('editn').textContent = v.job?.running ? v.job.line.slice(0, 40) : `part ${part + 1} of ${ps.length}`;
  $('editBody').innerHTML = `<div class="ed">
  <h5>Part ${part + 1}: ${esc(p.label)} <span>${clock(p.t0)}-${clock(p.t1)}</span></h5>
  <p class="note" style="margin-bottom:6px">Click a block in the Music plan row to pick a part.</p>
  <select id="edGenre"><option value="">Same as the whole track (${esc(base?.name ?? 'none picked')})</option>${ready.filter((t) => t.id !== base?.id).map((t) => `<option value="${t.id}" ${cur === t.id ? 'selected' : ''}>${esc(t.name)}</option>`).join('')}</select>
  <h5 style="margin-top:8px">Energy <span>${lv === p.level ? 'auto' : 'changed'}</span></h5><div class="seg2" id="edLevel">${[1, 2, 3, 4].map((n) => `<button data-lv="${n}" class="${n === lv ? 'on' : ''}">${['Soft', 'Light', 'Full', 'Peak'][n - 1]}</button>`).join('')}</div></div>
  <div class="ed"><h5>Music stops under <span>${turns.filter(on).length} of ${turns.length}</span></h5>${turns.map((s) => `<label class="turn"><input type="checkbox" data-turn="${s.t.toFixed(2)}" ${on(s) ? 'checked' : ''}><span>${esc(s.text)}</span><small>${clock(s.t)}</small></label>`).join('') || '<p class="note">No short lines in this video.</p>'}</div>
  ${base?.kind === 'code' && theme ? `<div class="ed"><h5>${esc(base.name)} <span>whole track</span></h5>
  <div class="row"><input type="range" id="edBpm" min="${Math.round(theme.bpm[0] * 0.85)}" max="${Math.round(theme.bpm[1] * 1.15)}" step="1" value="${Math.round(bpm)}"><b style="font:600 12px var(--mono);min-width:64px">${Math.round(bpm)} BPM</b></div>
  <div class="row" style="margin-top:6px"><select id="edKey">${KEYS.map((k) => `<option ${k === key ? 'selected' : ''}>${k}</option>`).join('')}</select><span class="note">${esc(theme.mode)}</span></div>
  <h5 style="margin-top:8px">Instruments <span>click to switch off</span></h5><div class="chips">${theme.layers.map((l) => `<button data-layer="${l}" class="${mute.includes(l) ? '' : 'on'}">${l}</button>`).join('')}</div></div>` : base ? `<p class="note">${esc(base.name)} is ${base.kind === 'song' ? 'your song re-cut' : 'a mix'}: tempo, key and instruments come from it.</p>` : ''}
  <div class="acts"><button class="btn go" id="edApply" ${dirty && !v.job?.running ? '' : 'disabled'}>${outlineDirty ? 'Apply to every genre' : 'Apply'}</button>${mixIds(v) ? '<button class="btn" id="edMix">Save this mix as a track</button>' : ''}<button class="btn" id="edReset">Back to auto</button></div>`;
  const setG = (k, val) => { draft.genres = draft.genres ?? {}; draft.genres[base.id] = { ...(draft.genres[base.id] ?? {}), [k]: val }; renderEdit(v); };
  $('edGenre').onchange = (e) => { const arr = plays(v).map((_, k) => (mixes[v.slug] ?? [])[k] ?? null); arr[part] = e.target.value || null; mixes[v.slug] = arr; store.set('mix', mixes); if (P.playing) swapMusic(); renderEdit(v); draw(); vzFrame(); };
  $('edLevel').onclick = (e) => { const b = e.target.closest('[data-lv]'); if (!b) return; draft.levels = { ...(draft.levels ?? {}), [lvKey]: Number(b.dataset.lv) }; if (Number(b.dataset.lv) === p.level && !(v.edits?.levels ?? {})[lvKey]) delete draft.levels[lvKey]; renderEdit(v); };
  $('editBody').querySelectorAll('[data-turn]').forEach((c) => { c.onchange = () => { draft.breaks = { ...(draft.breaks ?? {}), [c.dataset.turn]: c.checked }; renderEdit(v); }; });
  if ($('edBpm')) { $('edBpm').oninput = (e) => { e.target.nextElementSibling.textContent = `${e.target.value} BPM`; }; $('edBpm').onchange = (e) => setG('bpm', Number(e.target.value)); $('edKey').onchange = (e) => setG('key', e.target.value); }
  $('editBody').querySelectorAll('[data-layer]').forEach((b) => { b.onclick = () => { const l = b.dataset.layer; setG('mute', mute.includes(l) ? mute.filter((x) => x !== l) : [...mute, l]); }; });
  $('edApply').onclick = async () => { $('edApply').disabled = true; $('edApply').textContent = 'Writing...'; await fetch('/api/edits', { method: 'POST', body: JSON.stringify({ slug: v.slug, edits: draft, which: outlineDirty ? 'all' : base?.id }) }); draftSaved = structuredClone(draft); };
  if ($('edMix')) $('edMix').onclick = async () => { $('edMix').disabled = true; $('edMix').textContent = 'Stitching...'; await fetch('/api/mix', { method: 'POST', body: JSON.stringify({ slug: v.slug, ids: mixIds(v) }) }); };
  $('edReset').onclick = async () => { delete mixes[v.slug]; store.set('mix', mixes); draft = {}; if (!same(v.edits, {})) await fetch('/api/edits', { method: 'POST', body: JSON.stringify({ slug: v.slug, edits: {}, which: 'all' }) }); draftSaved = {}; renderEdit(v); draw(); };
}
let draftSaved = {};
let auto = store.get('auto', false), autoAt = Date.now();
$('auto').checked = auto;
$('auto').onchange = (e) => { auto = e.target.checked; autoAt = Date.now(); store.set('auto', auto); render(); };
function nextGenre() {
  const v = video();
  if (!v || isRef(v) || custom) return;
  const ready = [...$('genres').querySelectorAll('.g[data-id]')].map((c) => c.dataset.id).filter(Boolean);
  if (ready.length < 2) return;
  const id = ready[(ready.indexOf(sel[v.slug]) + 1) % ready.length];
  sel[v.slug] = id; store.set('sel', sel); autoAt = Date.now(); render();
  if (P.playing) swapMusic();
  const card = $('genres').querySelector(`.g[data-id="${id}"]`), gr = $('genres');
  if (card) gr.scrollTo({ top: card.offsetTop - gr.offsetTop - (gr.clientHeight - card.offsetHeight) / 2, behavior: 'smooth' });
}
setInterval(() => { if (auto && Date.now() - autoAt >= 5000) nextGenre(); }, 250);
$('loop').onchange = async (e) => { const v = video(); e.target.disabled = true; const r = await fetch('/api/loop', { method: 'POST', body: JSON.stringify({ slug: v.slug, on: e.target.checked, first: sel[v.slug] }) }); if (!r.ok) e.target.checked = !e.target.checked; e.target.disabled = false; };
$('match').onchange = (e) => { match = e.target.checked; store.set('match', match); render(); if (P.playing) swapMusic(); };
$('custom').onchange = (e) => { custom = e.target.checked; store.set('custom', custom); render(); };

const VZ = new Map(), vz = $('vz').getContext('2d'), VC = { p: 0, t: 0 };
function vzClock() {
  const real = now(), p = performance.now();
  if (!P.playing) { VC.t = real; VC.p = p; return real; }
  const pred = VC.t + (p - VC.p) / 1000;
  VC.t = Math.abs(pred - real) > 0.15 ? real : pred + (real - pred) * 0.08; VC.p = p;
  return VC.t;
}
function vzUrl(v, t) {
  if (isRef(v)) return `/work/${v.slug}/track.json`;
  const id = idAt(v, t) ?? sel[v.slug], tr = v.tries.find((x) => x.id === id);
  return tr ? `/work/${v.slug}/tries/${id}/track.json?m=${tr.mtime}` : null;
}
function vzFrame() {
  const v = video();
  if (!v) return;
  const t = vzClock(), url = vzUrl(v, t);
  $('vizn').textContent = url ? (isRef(v) ? 'their music' : (v.tries.find((x) => x.id === idAt(v, t))?.name ?? '')) : 'pick a genre';
  if (!url) return;
  const st = VZ.get(url);
  if (st === undefined) { VZ.set(url, null); fetch(url).then((r) => (r.ok ? r.json() : null)).then((tr) => { VZ.set(url, !tr ? false : tr.notes?.length ? { story: vzLoad(tr), track: tr } : vzPrepare(tr)); vzFrame(); }).catch(() => VZ.set(url, false)); return; }
  if (st?.story) vzGlow(vz, st.story, Math.min(t, st.track.duration - 0.01), S.watermark);
  else if (st) vzDraw(vz, st, Math.min(t, st.track.duration - 0.01), { title: S.watermark });
}

document.addEventListener('click', async (e) => {
  const tab = e.target.closest('[data-s]');
  if (tab) { menu(false); return choose(tab.dataset.s); }
  const make = e.target.closest('[data-make]');
  if (make) { make.disabled = true; make.textContent = 'Starting...'; await fetch('/api/make', { method: 'POST', body: JSON.stringify({ slug, theme: make.dataset.make }) }); return; }
  if (e.target.closest('a.dl')) return;
  const g = e.target.closest('.g[data-id]');
  if (g && g.dataset.id) { autoAt = Date.now(); sel[slug] = g.dataset.id; store.set('sel', sel); render(); if (P.playing) swapMusic(); }
});
$('pick').onclick = async () => {
  const v = video(), b = bed();
  if (!b) return;
  await fetch('/api/pick', { method: 'POST', body: JSON.stringify({ slug: v.slug, theme: b.t.id, under: under(), why: $('why').value, others: v.tries.map((t) => t.id).filter((id) => id !== b.t.id) }) });
  $('why').value = ''; $('pick').textContent = 'Picked ✓'; setTimeout(() => { $('pick').textContent = 'Pick this one'; }, 1800);
};
$('reveal').onclick = () => fetch(`/api/mp4?slug=${slug}&theme=${outId()}`, { method: 'POST' });
$('export').onclick = () => { const ids = mixIds(video()); fetch(ids ? '/api/mix' : '/api/make', { method: 'POST', body: JSON.stringify(ids ? { slug, ids, under: under(), export: true } : { slug, theme: bed()?.t?.id, under: under(), export: true }) }); };
window.chatContext = () => `${slug} · ${bed()?.t?.name ?? (isRef(video()) ? 'reference' : 'no track')} · at ${clock(now())} · music ${under()} LU under`;

/* ---------- drawing ---------- */
function fit(c) { const r = c.getBoundingClientRect(), d = devicePixelRatio || 1; if (c.width !== Math.round(r.width * d) || c.height !== Math.round(r.height * d)) { c.width = Math.round(r.width * d); c.height = Math.round(r.height * d); } const x = c.getContext('2d'); x.setTransform(d, 0, 0, d, 0, 0); return [x, r.width, r.height]; }
function spark(c, level) {
  const [x, w, h] = fit(c);
  x.clearRect(0, 0, w, h);
  if (!level?.length) return;
  x.beginPath(); x.moveTo(0, h);
  level.forEach((l, i) => x.lineTo((i / (level.length - 1)) * w, h - Math.max(0, Math.min(1, (l + 24) / 30)) * h));
  x.lineTo(w, h); x.closePath(); x.fillStyle = 'rgba(210,80,47,.22)'; x.fill(); x.strokeStyle = '#d2502f'; x.lineWidth = 1; x.stroke();
}

let ticking = false;
function cardTick() {
  if (ticking) return; ticking = true;
  const step = () => {
    const now = Date.now(), gr = $('genres');
    gr.querySelectorAll('time[data-since]').forEach((t) => { t.textContent = `${(now / 1000 - +t.dataset.since).toFixed(1)}s`; });
    gr.querySelectorAll('.g[data-la] b[data-to]').forEach((b) => {
      const to = +b.dataset.to, d = (String(b.dataset.to).split('.')[1] ?? '').length, k = Math.min(1, Math.max(0, (now - +b.closest('.g').dataset.la - 300) / 650));
      b.textContent = (to * (1 - (1 - k) ** 3)).toFixed(d);
    });
    if (gr.querySelector('time[data-since]') || [...gr.querySelectorAll('.g[data-la]')].some((g) => now - +g.dataset.la < LAND_MS)) requestAnimationFrame(step); else ticking = false;
  };
  requestAnimationFrame(step);
}

const L = 96;
function lanes(h) { const top = 22, said = 40, sec = 16, plan = 30, rest = h - top - said - sec - plan - 30, loud = Math.max(40, rest * 0.5), lay = rest - loud; let y = top + 4; const at = (hh, gap = 6) => { const r = [y, hh]; y += hh + gap; return r; }; return { top, said: at(said), sec: at(sec), plan: at(plan), loud: at(loud, 8), lay: at(lay - 4) }; }
function draw() {
  const v = video(), c = $('tl');
  if (!v) return;
  const [x, w, h] = fit(c), len = v.seconds, X = (t) => L + (t / len) * (w - L - 12), Y = lanes(h), b = bed(v), tr = b?.t, o = tr?.parts ? tr : v.outline;
  x.clearRect(0, 0, w, h);
  x.font = '600 10px system-ui'; x.textBaseline = 'middle';
  const label = (txt, [y, hh]) => { x.fillStyle = '#9a9285'; x.fillText(txt.toUpperCase(), 14, y + hh / 2); };
  const every = [10, 20, 30, 60].find((n) => X(n) - X(0) >= 36) ?? 60;
  for (let s = 0; s <= len; s += 5) { const px = X(s); x.fillStyle = s % 10 ? 'rgba(26,24,21,.08)' : 'rgba(26,24,21,.16)'; x.fillRect(px, 18, 1, h - 18); if (s % every === 0) { x.fillStyle = '#9a9285'; x.font = '500 10px ui-monospace,Menlo'; x.fillText(clock(s), px + 3, 10); } }
  x.font = '600 10px system-ui';
  label('What is said', Y.said); label('Sections', Y.sec); label(isRef(v) ? 'Their music' : 'Music plan', Y.plan); x.fillStyle = '#1f6f6b'; x.fillText('VOICE', 14, Y.loud[0] + Y.loud[1] / 2 - 6); x.fillStyle = '#d2502f'; x.fillText('VS MUSIC', 14, Y.loud[0] + Y.loud[1] / 2 + 7); if (isRef(v) || !Object.keys(tr?.layers ?? {}).length) label(isRef(v) ? 'Drums' : 'Layers', Y.lay);

  for (const s of v.speech.sentences) {
    const a = X(s.t), z = Math.max(a + 2, X(s.end)), [y, hh] = Y.said;
    x.fillStyle = s.pivot ? 'rgba(210,80,47,.85)' : 'rgba(31,111,107,.16)';
    rr(x, a, y, z - a - 1, hh, 4); x.fill();
    if (z - a > 26) { x.save(); x.beginPath(); x.rect(a + 4, y, z - a - 8, hh); x.clip(); x.fillStyle = s.pivot ? '#fff' : '#1f4f4c'; x.font = '500 11px system-ui'; wrap(x, s.text, a + 5, y + 13, z - a - 9, 13, 3); x.restore(); }
  }
  x.fillStyle = 'rgba(31,111,107,.55)';
  for (const wd of v.speech.words) x.fillRect(X(wd.t), Y.said[0] + Y.said[1] - 3, 1, 3);
  if (v.speech.noVoice) { x.fillStyle = '#1f4f4c'; x.font = '500 12px system-ui'; x.fillText('No voice: music plays start to end', L, Y.said[0] + Y.said[1] / 2); }
  const secs = v.speech.sections ?? [];
  secs.forEach((s, i) => { const a = X(s.t), z = X(secs[i + 1]?.t ?? len), [y, hh] = Y.sec; x.fillStyle = i % 2 ? '#e6dfd2' : '#ddd4c4'; rr(x, a, y, z - a - 2, hh, 4); x.fill(); x.fillStyle = '#5e584e'; x.font = '600 10.5px system-ui'; x.save(); x.beginPath(); x.rect(a, y, z - a - 4, hh); x.clip(); x.fillText(s.name, a + 5, y + hh / 2); x.restore(); });

  const [py, ph] = Y.plan;
  if (isRef(v)) {
    level(x, v.ref.level, X, py, ph, len);
    loud(x, v, bed(v), X, Y.loud[0], Y.loud[1], len);
    for (const br of v.ref.breaks) hatch(x, X(br.t), py, X(br.t + br.d) - X(br.t), ph);
    const dr = v.ref.drums, [ly, lh] = Y.lay;
    dr.forEach((d, i) => { const on = Math.max(0, Math.min(1, (d + 66) / 30)); if (on > 0.05) { x.fillStyle = `rgba(26,24,21,${0.12 + on * 0.6})`; x.fillRect(X(i * 0.25), ly + lh / 2 - 6, Math.max(1, X(0.25) - X(0)), 12); } });
  } else if (o?.parts) {
    for (const p of o.parts) {
      const a = X(p.t0), z = X(p.t1);
      if (p.kind === 'break') { hatch(x, a, py, z - a, ph); continue; }
      const hh = ph * (0.25 + 0.75 * (p.level / 4)), mid = mixIds(v) ? idAt(v, (p.t0 + p.t1) / 2) : null, mt = mid && v.tries.find((q) => q.id === mid);
      x.fillStyle = mt ? hueOf(mid) : LEVEL[p.level]; rr(x, a, py + ph - hh, z - a - 1, hh, 5); x.fill();
      if (custom && plays(v)[part]?.t0 === p.t0) { x.strokeStyle = '#1a1815'; x.lineWidth = 2; rr(x, a, py + ph - hh, z - a - 1, hh, 5); x.stroke(); }
      x.fillStyle = mt || p.level >= 3 ? '#fff' : '#5e584e'; x.font = '600 10.5px system-ui';
      if (z - a > 48) x.fillText(mt ? mt.name : `${p.label ?? ''} ${p.bpm ? `${p.bpm.toFixed(1)}` : ''}`.trim(), a + 6, py + ph - hh + 11);
    }
    if (tr?.bars) { x.fillStyle = 'rgba(26,24,21,.28)'; for (const bt of tr.bars) x.fillRect(X(bt), py + ph + 1, 1, 4); }
    loud(x, v, b, X, Y.loud[0], Y.loud[1], len);
    x.strokeStyle = 'rgba(185,138,30,.95)'; x.lineWidth = 1.5; x.setLineDash([3, 3]);
    for (const a of o.anchors ?? []) { x.beginPath(); x.moveTo(X(a.t), Y.said[0]); x.lineTo(X(a.t), py + ph); x.stroke(); }
    x.setLineDash([]);
    const layers = Object.entries(tr?.layers ?? {}), [ly, lh] = Y.lay, rowH = layers.length ? Math.min(14, (lh + 8) / layers.length) : 0;
    layers.forEach(([name, spans], i) => { const y = ly + i * rowH; x.fillStyle = '#9a9285'; x.font = `500 ${Math.min(10, rowH)}px system-ui`; x.textAlign = 'right'; x.fillText(name, L - 8, y + rowH / 2); x.textAlign = 'left'; x.fillStyle = 'rgba(26,24,21,.72)'; for (const [a, z] of spans) { rr(x, X(a), y + 2, Math.max(1, X(z) - X(a) - 1), rowH - 4, 2); x.fill(); } });
    if (!layers.length) { x.fillStyle = '#9a9285'; x.font = '500 11.5px system-ui'; x.fillText(o.parts ? 'Pick a genre to see its layers' : '', L, ly + lh / 2); }
  } else { x.fillStyle = '#9a9285'; x.font = '500 12px system-ui'; x.fillText('Not fitted yet: the plan appears here when the engine has read the speech.', L, py + ph / 2); }

  const t = now(), px = X(t);
  x.fillStyle = '#d2502f'; x.fillRect(px - 1, 14, 2, h - 14); x.beginPath(); x.arc(px, 14, 4, 0, 7); x.fill();
  if (hover) { x.fillStyle = 'rgba(26,24,21,.35)'; x.fillRect(hover.x, 18, 1, h - 18); }
  $('clock').innerHTML = `${clock(t)} <i>/ ${clock(len)}</i>`;
  const ids = !isRef(v) && mixIds(v), names = ids && ids.map((id) => v.tries.find((q) => q.id === id)?.name).filter((n, i, a) => n !== a[i - 1]);
  $('scoreh').textContent = ids ? `${names.join(' → ')}${match ? `: each part matched to how fast you talk (${targets(v).map((b) => Math.round(b)).join(', ')} BPM wanted)` : ''}` : tr?.score ? `${tr.name}: ${tr.bpm} BPM, ${tr.score.cueErrorMs != null ? `every music change within ${tr.score.cueErrorMs} ms of its spoken cue, ` : ''}tempo moves at most ${tr.score.maxDriftPct}%${tr.score.attackMs != null ? `, back to full level ${tr.score.attackMs} ms after each stop` : ''}` : isRef(v) ? `${v.ref.breaks.length} full stops (hatched), level of their music in red` : '';
}
function level(x, lv, X, y, h, len, line) {
  if (!lv?.length) return;
  x.beginPath();
  lv.forEach((l, i) => { const px = X(Math.min(len, i * 0.25)), py = y + h - Math.max(0, Math.min(1, (l + 24) / 30)) * h; i ? x.lineTo(px, py) : x.moveTo(px, py); });
  if (line) { x.strokeStyle = 'rgba(26,24,21,.55)'; x.lineWidth = 1; x.stroke(); return; }
  x.lineTo(X(Math.min(len, (lv.length - 1) * 0.25)), y + h); x.lineTo(X(0), y + h); x.closePath(); x.fillStyle = 'rgba(210,80,47,.25)'; x.fill(); x.strokeStyle = '#d2502f'; x.lineWidth = 1; x.stroke();
}
function loud(x, v, b, X, y, h, len) {
  const voice = v.levels?.voice;
  if (!voice) return;
  const segs = segments(v), said = muted() ? [] : voice.map((d) => d + voiceDb());
  const music = segs.length && b?.level ? b.level.map((_, i) => { const s = segs.find((q) => i * 0.25 >= q.a && i * 0.25 < q.b)?.b0 ?? b; const l = s.level?.[i]; return l == null || s.med == null ? -120 : l + s.med + 20 * Math.log10(gainOf(s)); }) : [];
  const top = Math.max(...voice, ...said, ...music) + 3, span = 42, Yd = (d) => y + Math.max(0, Math.min(1, (top - d) / span)) * h;
  const area = (arr, fill, stroke) => { x.beginPath(); x.moveTo(X(0), y + h); arr.forEach((d, i) => x.lineTo(X(Math.min(len, i * 0.25)), Yd(d))); x.lineTo(X(Math.min(len, (arr.length - 1) * 0.25)), y + h); x.closePath(); x.fillStyle = fill; x.fill(); x.strokeStyle = stroke; x.lineWidth = 1; x.stroke(); };
  if (said.length) area(said, 'rgba(31,111,107,.16)', 'rgba(31,111,107,.55)');
  if (music.length) area(music, 'rgba(210,80,47,.32)', '#d2502f');
  if (!b) { x.fillStyle = '#9a9285'; x.font = '500 11.5px system-ui'; x.fillText('Pick a genre to see the music against your voice', X(1), y + h / 2); }
}
function hatch(x, a, y, w, h) { x.save(); x.beginPath(); x.rect(a, y, w, h); x.clip(); x.strokeStyle = 'rgba(26,24,21,.35)'; x.lineWidth = 1; for (let i = -h; i < w; i += 5) { x.beginPath(); x.moveTo(a + i, y + h); x.lineTo(a + i + h, y); x.stroke(); } x.restore(); }
function rr(x, a, y, w, h, r) { r = Math.max(0, Math.min(r, w / 2, h / 2)); x.beginPath(); x.moveTo(a + r, y); x.arcTo(a + w, y, a + w, y + h, r); x.arcTo(a + w, y + h, a, y + h, r); x.arcTo(a, y + h, a, y, r); x.arcTo(a, y, a + w, y, r); x.closePath(); }
function wrap(x, text, a, y, w, lh, max) { const words = text.split(' '); let line = '', n = 0; for (const wd of words) { if (x.measureText(`${line} ${wd}`).width > w && line) { x.fillText(line, a, y); y += lh; line = wd; if (++n >= max) return; } else line = line ? `${line} ${wd}` : wd; } x.fillText(line, a, y); }

const tl = $('tl');
const timeAt = (e) => { const r = tl.getBoundingClientRect(), v = video(); return Math.max(0, ((e.clientX - r.left - L) / (r.width - L - 12)) * v.seconds); };
tl.onclick = (e) => {
  const r = tl.getBoundingClientRect(), v = video(), Y = lanes(r.height), y = e.clientY - r.top, t = timeAt(e);
  if (e.clientX - r.left <= L) return;
  if (custom && !isRef(v) && y >= Y.plan[0] - 4 && y <= Y.plan[0] + Y.plan[1] + 4) { const k = plays(v).findIndex((p) => t >= p.t0 && t < p.t1); if (k >= 0) { part = k; renderEdit(v); draw(); return; } }
  seek(t);
};
tl.onmousemove = (e) => {
  const v = video(), t = timeAt(e), r = tl.getBoundingClientRect(), s = v?.speech.sentences.find((q) => t >= q.t - 0.05 && t <= q.end + 0.05);
  hover = { x: e.clientX - r.left };
  const p = (bed(v)?.t ?? v.outline)?.parts?.find((q) => t >= q.t0 && t < q.t1);
  const tip = $('tip');
  const lines = [`<b>${clock(t)}</b>`, s ? `"${esc(s.text)}"${s.pivot ? ' <i>(turn: music stops under it)</i>' : ''}` : '', p ? `${p.kind === 'break' ? 'Music stops' : `${esc(p.label ?? '')}, level ${p.level} of 4, ${p.bpm?.toFixed(1)} BPM, ${p.beats} beats`}` : ''].filter(Boolean);
  tip.innerHTML = lines.join('<br>'); tip.style.display = 'block';
  tip.style.left = `${Math.min(r.width - 390, Math.max(8, e.clientX - r.left + 12))}px`; tip.style.top = `${e.clientY - r.top + 30}px`;
  if (!P.playing) draw();
};
tl.onmouseleave = () => { hover = null; $('tip').style.display = 'none'; draw(); };
addEventListener('resize', () => draw());
(function loop() {
  if (P.playing) {
    const t = now(), v = video(), el = $('video');
    if (v?.loop && t >= span(v) && P.next) { Object.assign(P, { voice: P.next.voice, music: P.next.music, start: P.start + span(v), next: null }); setGains(); }
    else if (t >= (v?.seconds ?? 0)) { pause(); P.offset = 0; }
    else if (v?.loop && !P.next && P.bufs && t >= span(v) - 0.3) queueLoop(v);
    else if (Math.abs(el.currentTime - t) > 0.12) el.currentTime = t;
    $('mV').style.width = `${meter(aV)}%`; $('mM').style.width = `${meter(aM)}%`;
    draw(); vzFrame();
  }
  requestAnimationFrame(loop);
})();
