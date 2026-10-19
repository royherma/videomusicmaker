import signal, sys, time

import numpy as np
import soundfile as sf

from .common import WORK, loudness, read_json, video_seconds, write_json
from .compose import compose, take_key, themes, with_edits
from .mix import master, write_levels, write_try
from .plan import fit, outline


def prepare(slug):
    speech, loop = read_json(WORK / slug / 'speech.json'), bool(read_json(WORK / slug / 'mode.json', {}).get('loop'))
    if loop:
        speech['seconds'] = round(video_seconds(speech['video']), 3)
    out = outline(speech, edits=read_json(WORK / slug / 'edits.json', {}), loop=loop)
    out['voiceLufs'] = -18.0 if speech.get('noVoice') else loudness(WORK / slug / 'voice.wav')[0]  # no voice: music sits as if under a typical one
    write_json(WORK / slug / 'outline.json', out)
    write_levels(slug)
    return speech, out


def talking(slug):
    """0..1 per 10 ms: how much the voice is speaking, fast to rise, slow to let go, so a solo comes up in breaths."""
    y, sr = sf.read(WORK / slug / 'voice.wav', always_2d=True)
    y = y.mean(axis=1)
    hop = sr // 100
    if not np.abs(y).max() > 1e-3:
        return np.zeros(len(y) // hop)
    db = 20 * np.log10(np.maximum(np.sqrt(np.mean(y[:len(y) // hop * hop].reshape(-1, hop) ** 2, axis=1)), 1e-6))
    raw = np.clip((db - (np.percentile(db, 95) - 32)) / 12, 0, 1)
    out, v = np.zeros_like(raw), 0.0
    for i, r in enumerate(raw):
        v += (r - v) * (0.35 if r > v else 0.1)
        out[i] = v
    return out


class Run:
    """work/<slug>/run.json: one row per genre, rewritten at every stage so the page can show the run live."""

    def __init__(self, slug, ids, names, out, keep=False):
        self.file = WORK / slug / 'run.json'
        plan, last = {'parts': len(out['parts']), 'stops': out['breaks']}, read_json(WORK / slug / 'run.json', None)
        if keep and last and last.get('plan') == plan:
            self.data = {**last, 'done': False, 'stoppedAt': None}
            for i in ids:
                row = next((g for g in self.data['genres'] if g['id'] == i), None)
                if row is None:
                    self.data['genres'].append(row := {'id': i})
                row.clear()
                row.update(id=i, name=names[i], state='queued')
        else:
            self.data = {'startedAt': time.time(), 'done': False, 'plan': plan, 'genres': [{'id': i, 'name': names[i], 'state': 'queued'} for i in ids]}
        self.save()

    def stop(self):
        """Stopped from the page: what is written stays, the rest is marked so nothing looks like it is still coming."""
        for g in self.data['genres']:
            if g['state'] not in ('pass', 'fail'):
                g['state'] = 'stopped'
        self.data['stoppedAt'] = time.time()
        self.save()
        print('Stopped', flush=True)
        sys.exit(0)

    def save(self):
        self.data['at'] = time.time()
        write_json(self.file, self.data)

    def set(self, tid, **kw):
        next(g for g in self.data['genres'] if g['id'] == tid).update(kw)
        self.save()


def windows(bpm):
    """Tempo ranges to try in turn: the genre's own range, then its slow half, then its fast half."""
    lo, hi = bpm
    mid = round((lo + hi) / 2 * 4) / 4
    return [bpm, [lo, mid], [mid, hi]]


def archive(slug):
    """Moves the last run's tracks to runs/<time>/ so a fresh run starts on an empty grid. Nothing is deleted."""
    tries = WORK / slug / 'tries'
    if tries.exists() and any(tries.iterdir()):
        dest = WORK / slug / 'runs' / time.strftime('%Y%m%d-%H%M%S')
        dest.mkdir(parents=True)
        tries.rename(dest / 'tries')
        return dest


STOP = []


def make(slug, which='all', song=None, under=None, fresh=False, first=None):
    signal.signal(signal.SIGTERM, lambda *_: STOP.append(1))
    take = read_json(WORK / slug / 'take.json', {'n': 0})['n']
    if fresh or not take:
        moved = fresh and archive(slug)
        if moved:
            print(f'Last run moved to {moved}', flush=True)
        take += 1
        write_json(WORK / slug / 'take.json', {'n': take})
    seed = (slug, take)
    speech, out = prepare(slug)
    print(f"Outline: {len(out['parts'])} parts, {out['breaks']} full stops", flush=True)
    if song:
        from .retrack import retrack
        return retrack(slug, song, speech, out)
    edits = read_json(WORK / slug / 'edits.json', {}).get('genres', {})
    voice = talking(slug)
    todo = sorted((t for t in themes().values() if which in ('all', t['id'])), key=lambda t: (t['id'] != first, t.get('order', 99)))
    run = Run(slug, [t['id'] for t in todo], {t['id']: t['name'] for t in todo}, out, keep=which != 'all')
    for theme in todo:
        theme = with_edits(take_key(theme, seed), edits.get(theme['id'], {}))
        tries = [(theme, w, (*seed, i) if i else seed) for i, w in enumerate(windows(theme['bpm']))]
        started, best = time.time(), None
        for attempt, (theme, bpm, line_seed) in enumerate(tries, 1):
            if STOP:
                run.stop()
            run.set(theme['id'], state='write', attempt=attempt, startedAt=started)
            print(f"Writing {theme['name']} (try {attempt})", flush=True)
            grid = {**fit(out, bpm), 'speechEnd': out['speechEnd'], 'loop': out['loop'], 'voice': voice, 'sentences': [x['t'] for x in speech['sentences']]}
            stems, layers, events = compose(theme, grid, speech['seconds'], line_seed)
            bed = master(stems, theme, speech['seconds'], out['loop'])
            run.set(theme['id'], state='check')
            meta = {'kind': 'code', 'name': theme['name'], 'about': theme['about'], 'key': f"{theme['key']} {theme['mode']}", 'under': under or theme.get('under', 10),
                    'layers': dict(layers), 'composeSeconds': round(time.time() - started, 1), 'edited': bool(edits.get(theme['id'])), 'attempt': attempt, 'take': take}
            t = write_try(slug, theme['id'], bed, meta, grid, out, events)
            fails = [g for g in t['gates'] if not g['ok']]
            if best is None or len(fails) < best[1]:
                best = (attempt, len(fails), bpm, line_seed)
            if not fails or all(g.get('unchecked') for g in fails):
                break
            run.set(theme['id'], state='retry', failed=[g['label'] for g in fails])
            print(f"{theme['name']} failed: {', '.join(g['label'] for g in fails)}", flush=True)
        if not t['passed'] and best[0] != attempt:
            grid = {**fit(out, best[2]), 'speechEnd': out['speechEnd'], 'loop': out['loop'], 'voice': voice, 'sentences': [x['t'] for x in speech['sentences']]}
            stems, layers, events = compose(theme, grid, speech['seconds'], best[3])
            t = write_try(slug, theme['id'], master(stems, theme, speech['seconds'], out['loop']), {**meta, 'layers': dict(layers), 'attempt': best[0]}, grid, out, events)
        s = t['score']
        run.set(theme['id'], state='pass' if t['passed'] else 'fail', seconds=round(time.time() - started, 1), bpm=t['bpm'], cueErrorMs=s['cueErrorMs'],
                gates=[{k: g[k] for k in ('label', 'ok')} for g in t['gates']], failed=[g['label'] for g in t['gates'] if not g['ok'] and not g.get('unchecked')],
                unchecked=[f"{g['label']}: {g['unchecked']}" for g in t['gates'] if g.get('unchecked')])
        print(f"{theme['name']}: {'passed' if t['passed'] else 'FAILED'} {sum(g['ok'] for g in t['gates'])}/{len(t['gates'])} checks, {t['bpm']} BPM", flush=True)
    run.data['done'] = all(g['state'] in ('pass', 'fail') for g in run.data['genres'])
    run.save()
