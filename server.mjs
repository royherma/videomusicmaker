#!/usr/bin/env node
// VideoMusicMaker page on :4812. Reads what the engine writes under work/ and research/; the page polls /api/rev and redraws.
import { spawn } from 'node:child_process';
import { createHash } from 'node:crypto';
import { appendFileSync, createReadStream, createWriteStream, existsSync, mkdirSync, readdirSync, readFileSync, statSync, writeFileSync } from 'node:fs';
import { createServer } from 'node:http';
import { basename, extname, join, normalize, relative, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
const TOOL_UI = existsSync(new URL('./scripts/tool-ui/chat-bar.mjs', import.meta.url));
const { chatBar, chatRoutes } = TOOL_UI ? await import('./scripts/tool-ui/chat-bar.mjs') : { chatBar: () => '', chatRoutes: () => false };
const NAV = TOOL_UI ? '<script src="http://127.0.0.1:4800/nav.js" defer></script>' : '';

const ROOT = fileURLToPath(new URL('.', import.meta.url));
const PORT = Number(process.env.PORT ?? 4812);
const TYPES = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.mp4': 'video/mp4', '.opus': 'audio/ogg', '.wav': 'audio/wav', '.png': 'image/png', '.svg': 'image/svg+xml' };
const jobs = new Map();
const WEB_ORIGINS = new Set(['https://tools.techguyverlabs.org', 'http://localhost:4920', 'http://127.0.0.1:4920']);
const LOCAL_HOST = /^(([\w-]+\.)*localhost|127\.0\.0\.1|\[::1\])(:\d+)?$/;

function guard(req, res) {
  if (!LOCAL_HOST.test(req.headers.host || '')) return res.writeHead(403).end('bad host'), false;
  const o = req.headers.origin;
  if (!o) return true;
  if (!WEB_ORIGINS.has(o) && !LOCAL_HOST.test(o.replace(/^https?:\/\//, ''))) return res.writeHead(403).end('origin not allowed'), false;
  res.setHeader('Access-Control-Allow-Origin', o);
  res.setHeader('Vary', 'Origin');
  res.setHeader('Access-Control-Allow-Private-Network', 'true');
  res.setHeader('Access-Control-Allow-Headers', 'content-type, range');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Access-Control-Expose-Headers', 'Content-Length, Content-Range, Accept-Ranges, Content-Disposition');
  if (req.method === 'OPTIONS') return res.writeHead(204).end(), false;
  return true;
}

const readJson = (file, fallback) => { try { return JSON.parse(readFileSync(file, 'utf8')); } catch { return fallback; } };
const dirs = (dir) => (existsSync(dir) ? readdirSync(dir).filter((n) => statSync(join(dir, n)).isDirectory()) : []);

function engineFiles(dir = join(ROOT, 'engine')) {
  return readdirSync(dir).flatMap((n) => { const f = join(dir, n); return statSync(f).isDirectory() ? (n === '__pycache__' ? [] : engineFiles(f)) : [f]; });
}
const stampCache = { key: '', value: null };
function stamps() {
  const all = engineFiles(), rel = (f) => relative(ROOT, f).split(sep).join('/');
  const key = all.map((f) => `${rel(f)}:${statSync(f).mtimeMs}`).join('|');
  if (key === stampCache.key) return stampCache.value;
  const hash = (files) => { const h = createHash('sha1'); for (const f of files.sort((a, b) => (rel(a) < rel(b) ? -1 : 1))) { h.update(`${rel(f)}\0`); h.update(readFileSync(f)); } return h.digest('hex').slice(0, 10); };
  const value = { track: hash(all.filter((f) => f.endsWith('.py') || /engine\/themes\/[^/]+\.json$/.test(f))), reader: hash(all.filter((f) => rel(f) === 'engine/speech.py')) };
  Object.assign(stampCache, { key, value });
  return value;
}

const jobView = (job) => (job ? (({ child, ...rest }) => rest)(job) : null);

function exportsFor(slug) {
  const f = join(ROOT, 'library/exports.jsonl'), rows = existsSync(f) ? readFileSync(f, 'utf8').split('\n').filter(Boolean).map((l) => JSON.parse(l)) : [];
  return Object.fromEntries(rows.filter((r) => r.slug === slug && existsSync(r.file)).map((r) => [r.try, { file: r.file, at: r.at, under: r.under }]));
}

function state() {
  const picks = existsSync(join(ROOT, 'library/picks.jsonl')) ? readFileSync(join(ROOT, 'library/picks.jsonl'), 'utf8').split('\n').filter(Boolean).map((l) => JSON.parse(l)) : [];
  const videos = dirs(join(ROOT, 'work')).filter((slug) => existsSync(join(ROOT, 'work', slug, 'speech.json'))).map((slug) => {
    const dir = join(ROOT, 'work', slug), speech = readJson(join(dir, 'speech.json'), {});
    const tries = dirs(join(dir, 'tries')).map((id) => { const f = join(dir, 'tries', id, 'try.json'), t = readJson(f, null); return t && { ...t, mtime: Math.round(statSync(f).mtimeMs) }; }).filter(Boolean);
    const added = Math.round(statSync(dir).birthtimeMs || statSync(join(dir, 'speech.json')).mtimeMs);
    return { slug, title: speech.title, seconds: speech.seconds, added, speech, ref: readJson(join(ROOT, 'research', slug, 'ref.json'), null), outline: readJson(join(dir, 'outline.json'), null), levels: readJson(join(dir, 'levels.json'), null), run: readJson(join(dir, 'run.json'), null), edits: readJson(join(dir, 'edits.json'), {}), tries, pick: picks.findLast((p) => p.slug === slug) ?? null, job: jobView(jobs.get(slug)), exports: exportsFor(slug), loop: !!readJson(join(dir, 'mode.json'), {}).loop };
  });
  const themes = existsSync(join(ROOT, 'engine/themes')) ? readdirSync(join(ROOT, 'engine/themes')).filter((f) => f.endsWith('.json')).map((f) => readJson(join(ROOT, 'engine/themes', f), null)).filter(Boolean).map(({ id, name, about, bpm, key, mode, order, layers }) => ({ id, name, about, bpm, key, mode, order, layers: Object.keys(layers ?? {}) })) : [];
  const wins = (id) => picks.filter((p) => p.theme === id).length;
  const adding = [...jobs.entries()].filter(([s, j]) => j.adding && (j.running || j.failed) && !videos.some((v) => v.slug === s)).map(([slug, j]) => ({ slug, title: j.title, line: j.line, running: j.running, failed: j.failed, startedAt: j.startedAt }));
  return { build: readJson(join(ROOT, 'work/build.json'), { steps: [] }), adding, videos, stamps: stamps(), themes: themes.map((t) => ({ ...t, wins: wins(t.id) })).sort((a, b) => b.wins - a.wins || (a.order ?? 9) - (b.order ?? 9)), picks: picks.slice(-30), watermark: process.env.VMM_WATERMARK ?? readJson(join(ROOT, 'brand.json'), {}).watermark ?? '' };
}

function rev() {
  let newest = 0;
  const walk = (dir, depth) => { if (!existsSync(dir)) return; for (const n of readdirSync(dir)) { const f = join(dir, n), s = statSync(f); if (s.isDirectory()) { if (depth < 3 && n !== 'stems') walk(f, depth + 1); } else if (/\.jsonl?$/.test(n)) newest = Math.max(newest, s.mtimeMs); } };
  for (const d of ['work', 'research', 'library', 'engine/themes']) walk(join(ROOT, d), 0);
  return `${Math.round(newest)}-${[...jobs.values()].map((j) => j.line).join('|')}`;
}

function sendFile(req, res, file) {
  if (!existsSync(file) || !statSync(file).isFile()) { res.writeHead(404).end('not found'); return; }
  const size = statSync(file).size, type = TYPES[extname(file)] ?? 'application/octet-stream', range = /bytes=(\d*)-(\d*)/.exec(req.headers.range ?? '');
  if (!range) { res.writeHead(200, { 'Content-Type': type, 'Content-Length': size, 'Accept-Ranges': 'bytes', 'Cache-Control': 'no-store' }); createReadStream(file).pipe(res); return; }
  const start = range[1] ? Number(range[1]) : Math.max(0, size - Number(range[2])), end = range[1] && range[2] ? Math.min(Number(range[2]), size - 1) : size - 1;
  res.writeHead(206, { 'Content-Type': type, 'Content-Length': end - start + 1, 'Content-Range': `bytes ${start}-${end}/${size}`, 'Accept-Ranges': 'bytes', 'Cache-Control': 'no-store' });
  createReadStream(file, { start, end }).pipe(res);
}

const body = (req) => new Promise((ok) => { let s = ''; req.on('data', (c) => { s += c; }); req.on('end', () => { try { ok(JSON.parse(s || '{}')); } catch { ok({}); } }); });
const json = (res, code, data) => { res.writeHead(code, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' }); res.end(JSON.stringify(data)); };
const safe = (s) => String(s ?? '').replace(/[^a-z0-9-]/gi, '');

const slugify = (s) => s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 48);
const MEDIA = /\.(mp4|mov|m4v|webm|mkv|mp3|wav|m4a)$/i;

function addVideo(path) {
  const stem = basename(path).replace(/\.[^.]+$/, ''), cam = stem.match(/^phonecam-\d{8}-(\d\d)(\d\d)\d\d$/);
  const title = cam ? `Phonecam take ${cam[1]}:${cam[2]}` : stem, slug = slugify(stem);
  if (jobs.get(slug)?.running) return slug;
  jobs.set(slug, { adding: true, title, running: true, startedAt: Date.now() });
  engine(slug, ['speech', path, '--slug', slug, '--title', title], () => engine(slug, ['make', slug, 'all']));
  return slug;
}

function engine(slug, args, then) {
  const job = jobs.get(slug)?.running ? jobs.get(slug) : { startedAt: Date.now() };
  Object.assign(job, { args, line: args[0] === 'speech' ? 'Reading the speech' : 'Starting', running: true, failed: false });
  jobs.set(slug, job);
  const child = spawn(join(ROOT, 'bin/soundtrack'), args, { cwd: ROOT });
  job.child = child;
  const say = (chunk) => { const lines = String(chunk).split('\n').filter(Boolean); if (lines.length) job.line = lines.at(-1).slice(0, 200); };
  child.stdout.on('data', say); child.stderr.on('data', say);
  child.on('close', (code) => {
    if (job.stopping) return Object.assign(job, { running: false, stopping: false, stopped: true, failed: false, line: 'Stopped' });
    if (code === 0 && then) return then();
    if (code === 0 && args[0] === 'export') { job.file = exportsFor(slug)[args[2]]?.file; if (job.file) spawn('open', ['-R', job.file]); }
    job.running = false; job.failed = code !== 0; job.seconds = (Date.now() - job.startedAt) / 1000; });
}

function stopJob(slug) {
  const job = jobs.get(slug);
  if (!job?.running || !job.child) return Promise.resolve();
  return new Promise((done) => {
    Object.assign(job, { stopping: true, line: 'Stopping after the track being written' });
    job.child.once('close', () => done());
    job.child.kill('SIGTERM');
    setTimeout(() => { if (job.running) job.child.kill('SIGKILL'); }, 20000);
  });
}

createServer(async (req, res) => {
  if (!guard(req, res)) return;
  const url = new URL(req.url, 'http://x'), path = decodeURIComponent(url.pathname);
  if (path === '/api/hello') return json(res, 200, { app: 'videomusicmaker', version: 1 });
  if (chatRoutes('soundtrack', req, res, url)) return;
  if (path === '/') { res.writeHead(200, { 'Content-Type': TYPES['.html'], 'Cache-Control': 'no-store' }); res.end(readFileSync(join(ROOT, 'page/index.html'), 'utf8').replace('<!--chat-->', chatBar('soundtrack')).replace('<!--nav-->', NAV)); return; }
  if (path === '/viz-lab') { res.writeHead(200, { 'Content-Type': TYPES['.html'], 'Cache-Control': 'no-store' }); res.end(readFileSync(join(ROOT, 'page/viz-lab.html'), 'utf8').replace('<!--chat-->', chatBar('soundtrack'))); return; }
  if (path === '/api/rev') return json(res, 200, { rev: rev(), page: Math.max(...readdirSync(join(ROOT, 'page')).filter((n) => !n.startsWith('viz-lab')).map((n) => statSync(join(ROOT, 'page', n)).mtimeMs)) });
  if (path === '/mm/engine.js') return sendFile(req, res, join(ROOT, 'page/vz-engine.js'));
  if (path === '/api/state') return json(res, 200, state());
  if (path.startsWith('/video/')) { const speech = readJson(join(ROOT, 'work', safe(path.slice(7)), 'speech.json'), null); return speech ? sendFile(req, res, speech.video) : res.writeHead(404).end(); }
  if (req.method === 'POST' && path === '/api/pick') {
    const b = await body(req);
    mkdirSync(join(ROOT, 'library'), { recursive: true });
    appendFileSync(join(ROOT, 'library/picks.jsonl'), `${JSON.stringify({ at: new Date().toISOString(), slug: safe(b.slug), theme: safe(b.theme), under: Number(b.under) || null, why: String(b.why ?? '').slice(0, 400), others: (b.others ?? []).map(safe) })}\n`);
    console.log(`PICK ${safe(b.slug)} ${safe(b.theme)} under=${b.under} why=${b.why ?? ''}`);
    return json(res, 200, { ok: true });
  }
  if (req.method === 'POST' && path === '/api/note') {
    const b = await body(req);
    appendFileSync(join(ROOT, 'library/notes.jsonl'), `${JSON.stringify({ at: new Date().toISOString(), slug: safe(b.slug), theme: safe(b.theme), t: Number(b.t) || 0, text: String(b.text ?? '').slice(0, 600) })}\n`);
    console.log(`NOTE ${safe(b.slug)} ${safe(b.theme)} at ${Number(b.t).toFixed(1)}s | ${b.text}`);
    return json(res, 200, { ok: true });
  }
  if (req.method === 'POST' && path === '/api/add') {
    const file = String((await body(req)).path ?? '').trim().replace(/^['"]|['"]$/g, '').replace(/^~/, process.env.HOME);
    if (!existsSync(file) || !statSync(file).isFile()) return json(res, 400, { error: `No file at ${file}` });
    if (!MEDIA.test(file)) return json(res, 400, { error: 'That is not a video or sound file' });
    return json(res, 200, { slug: addVideo(file) });
  }
  if (req.method === 'POST' && path === '/api/upload') {
    const name = basename(url.searchParams.get('name') ?? 'video.mp4').replace(/[^\w.-]+/g, '-');
    if (!MEDIA.test(name)) return json(res, 400, { error: 'That is not a video or sound file' });
    mkdirSync(join(ROOT, 'work/uploads'), { recursive: true });
    const dest = join(ROOT, 'work/uploads', name);
    req.pipe(createWriteStream(dest)).on('finish', () => json(res, 200, { slug: addVideo(dest) }));
    return;
  }
  if (req.method === 'POST' && path === '/api/edits') {
    const b = await body(req), slug = safe(b.slug);
    if (!existsSync(join(ROOT, 'work', slug, 'speech.json'))) return json(res, 404, { error: 'No such video' });
    await stopJob(slug);
    writeFileSync(join(ROOT, 'work', slug, 'edits.json'), JSON.stringify(b.edits ?? {}, null, 1));
    engine(slug, ['make', slug, safe(b.which) || 'all']);
    return json(res, 200, { ok: true });
  }
  if (req.method === 'POST' && path === '/api/mix') {
    const b = await body(req), slug = safe(b.slug);
    if (jobs.get(slug)?.running) return json(res, 409, { error: 'Still making the last change' });
    const ids = (b.ids ?? []).map(safe).join(','), tid = `mix-${createHash('sha1').update(ids).digest('hex').slice(0, 6)}`;
    engine(slug, ['mix', slug, ids], b.export ? () => engine(slug, ['export', slug, tid, ...(b.under != null ? ['--under', String(Number(b.under))] : [])]) : undefined);
    return json(res, 200, { ok: true });
  }
  if (path === '/api/mp4') {
    const slug = safe(url.searchParams.get('slug')), file = exportsFor(slug)[safe(url.searchParams.get('theme'))]?.file;
    if (!file) return json(res, 404, { error: 'No mp4 made for this genre yet' });
    if (req.method === 'POST') { spawn('open', ['-R', file]); return json(res, 200, { ok: true, file }); }
    res.setHeader('Content-Disposition', `attachment; filename="${basename(file)}"`);
    return sendFile(req, res, file);
  }
  if (req.method === 'POST' && path === '/api/loop') {
    const b = await body(req), slug = safe(b.slug);
    if (!existsSync(join(ROOT, 'work', slug, 'speech.json'))) return json(res, 404, { error: 'No such video' });
    await stopJob(slug);
    writeFileSync(join(ROOT, 'work', slug, 'mode.json'), JSON.stringify({ loop: !!b.on }));
    engine(slug, ['make', slug, 'all', '--fresh', ...(b.first ? ['--first', safe(b.first)] : [])]);
    return json(res, 200, { ok: true });
  }
  if (req.method === 'POST' && path === '/api/reread') {
    const slug = safe((await body(req)).slug), speech = readJson(join(ROOT, 'work', slug, 'speech.json'), null);
    if (!speech) return json(res, 404, { error: 'No such video' });
    await stopJob(slug);
    engine(slug, speech.concept ? ['speech', speech.concept] : ['speech', speech.video, '--slug', slug, '--title', speech.title ?? slug], () => engine(slug, ['make', slug, 'all', '--fresh']));
    return json(res, 200, { ok: true });
  }
  if (req.method === 'POST' && path === '/api/stop') {
    const slug = safe((await body(req)).slug);
    await stopJob(slug);
    return json(res, 200, { ok: true });
  }
  if (req.method === 'POST' && path === '/api/run') {
    const b = await body(req), slug = safe(b.slug);
    await stopJob(slug);
    engine(slug, ['make', slug, 'all', '--fresh', ...(b.first ? ['--first', safe(b.first)] : [])]);
    return json(res, 200, { ok: true });
  }
  if (req.method === 'POST' && path === '/api/make') {
    const b = await body(req), slug = safe(b.slug);
    if (jobs.get(slug)?.running && (b.export || jobs.get(slug).args[0] === 'export')) return json(res, 409, { error: 'Already making one' });
    await stopJob(slug);
    if (b.song) { engine(slug, ['make', slug, '--song', String(b.song)]); return json(res, 200, { ok: true }); }
    engine(slug, b.export ? ['export', slug, safe(b.theme), ...(b.under != null ? ['--under', String(Number(b.under))] : [])] : ['make', slug, safe(b.theme) || 'all', ...(b.under != null ? ['--under', String(Number(b.under))] : [])]);
    return json(res, 200, { ok: true });
  }
  const file = normalize(join(ROOT, path.startsWith('/work/') || path.startsWith('/research/') ? path : join('page', path)));
  if (!file.startsWith(ROOT)) { res.writeHead(403).end(); return; }
  const dl = url.searchParams.get('dl');
  if (dl) res.setHeader('Content-Disposition', `attachment; filename="${dl.replace(/["\\\r\n]/g, '')}"; filename*=UTF-8''${encodeURIComponent(dl)}`);
  sendFile(req, res, file);
}).listen(PORT, process.env.HOST ?? '127.0.0.1', () => console.log(`VideoMusicMaker: http://${process.env.HOST ?? 'soundtrack.localhost'}:${PORT}/`));
