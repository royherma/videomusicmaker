"""Mix mode: each part of the video from a different genre. Every genre starts every part on its own downbeat, so the cuts land on the beat."""
import hashlib

import numpy as np
import soundfile as sf

from .common import WORK, read_json
from .mix import write_try

XF = 0.02
SWELL = 1.6


def stitch(slug, ids):
    out = read_json(WORK / slug / 'outline.json')
    parts = out['parts']
    plays = [i for i, p in enumerate(parts) if p['kind'] == 'play']
    if len(ids) != len(plays):
        raise SystemExit(f'{len(plays)} parts need a genre each, got {len(ids)}')
    tries = {i: read_json(WORK / slug / 'tries' / i / 'try.json') for i in set(ids)}
    for i, t in tries.items():
        if [round(p['t0'], 2) for p in t['parts']] != [round(p['t0'], 2) for p in parts]:
            raise SystemExit(f'{i} was made on an older plan: make it again first')
    beds, sr = {}, None
    for i, t in tries.items():
        x, sr = sf.read(WORK / slug / 'tries' / i / 'bed.wav', always_2d=True)
        beds[i] = x.T * 10 ** ((-16 - t['lufs']) / 20)
    owner = {j: ids[k] for k, j in enumerate(plays)}
    segs = []
    for j, p in enumerate(parts):
        if p['kind'] == 'play':
            segs.append([p['t0'], p['t1'], owner[j]])
            continue
        before = owner.get(max([q for q in plays if q < j], default=-1), owner[plays[0]])
        after = owner.get(min([q for q in plays if q > j], default=-1), before)
        mid = max(p['t0'], p['t1'] - SWELL)
        segs += [[p['t0'], mid, before], [mid, p['t1'], after]]
    n = min(b.shape[1] for b in beds.values())
    segs[-1][1] = n / sr
    bed = np.zeros((2, n))
    x = int(XF * sr)
    for a, b, i in segs:
        s, e = max(0, int(a * sr) - x), min(n, int(b * sr) + x)
        if e <= s:
            continue
        w = np.ones(e - s)
        if s > 0:
            w[:2 * x] = np.linspace(0, 1, 2 * x)
        if e < n:
            w[-2 * x:] = np.minimum(w[-2 * x:], np.linspace(1, 0, 2 * x))
        bed[:, s:e] += beds[i][:, s:e] * w
    bed *= 10 ** (-1.5 / 20) / (np.abs(bed).max() or 1)
    grid_parts, bars = [], []
    for j, p in enumerate(parts):
        src = tries[owner[j]] if j in owner else None
        q = {**p, 'theme': owner.get(j)}
        if src:
            sp = src['parts'][j]
            q['bpm'], q['beats'] = sp.get('bpm'), sp.get('beats')
            q['beatTimes'] = [b for b in src['bars'] if p['t0'] - 1e-3 <= b < p['t1']]
            bars += q['beatTimes']
        grid_parts.append(q)
    played = [(q['t1'] - q['t0'], q['bpm']) for q in grid_parts if q.get('bpm')]
    grid = {'parts': grid_parts, 'bars': bars, 'bpm': round(sum(d * b for d, b in played) / sum(d for d, _ in played), 2), 'maxDriftPct': max(t['score']['maxDriftPct'] for t in tries.values())}
    names = []
    for i in ids:
        if not names or names[-1] != tries[i]['name']:
            names.append(tries[i]['name'])
    tid = 'mix-' + hashlib.sha1(','.join(ids).encode()).hexdigest()[:6]
    meta = {'kind': 'mix', 'name': 'Your mix', 'about': ' → '.join(names), 'key': 'mixed', 'under': tries[ids[0]]['under'], 'layers': {}, 'mix': ids, 'composeSeconds': 0}
    t = write_try(slug, tid, bed.astype(np.float32), meta, grid, out)
    print(f"{tid}: {meta['about']}, cue error {t['score']['cueErrorMs']} ms", flush=True)
    return t
