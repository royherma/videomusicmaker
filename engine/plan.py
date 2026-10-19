"""Where the music changes (outline, same for every genre) and the beat grid that makes each change land on its word (fit, per genre)."""
import math

import numpy as np

from .common import WORK, read_json, write_json

LONG_GAP, MIN_PLAY = 1.5, 4


def outline(speech, max_breaks=None, edits=None, loop=False):
    sents, length = speech['sentences'], speech['seconds']
    end = sents[-1]['end'] if sents else length
    max_breaks = max_breaks or max(1, min(3, round(length / 35)))
    chosen = []
    for i in sorted((i for i, s in enumerate(sents[:-1]) if s.get('pivot')), key=lambda i: (-sents[i]['pivot'], sents[i]['t'])):
        s = sents[i]
        if s['t'] < min(6, length * 0.2) or s['t'] > end - min(8, length * 0.25) or any(abs(s['t'] - sents[j]['t']) < 18 for j in chosen):
            continue
        chosen.append(i)
        if len(chosen) == max_breaks:
            break
    forced = (edits or {}).get('breaks', {})
    key = lambda s: f"{s['t']:.2f}"
    chosen = [i for i in chosen if forced.get(key(sents[i])) is not False]
    chosen += [i for i, s in enumerate(sents[:-1]) if forced.get(key(s)) is True and i not in chosen]
    breaks = [(sents[i]['t'] - 0.04, sents[i + 1]['t'], sents[i]['text'], sents[i + 1]['text']) for i in sorted(chosen)]
    for g in sorted(speech.get('pauses', []), key=lambda g: -g['d']):
        a, z = g['t'], g['t'] + g['d']
        if g['d'] < LONG_GAP or not sents or a < sents[0]['t'] + 2 or z > end - 2 or forced.get(f'{a:.2f}') is False:
            continue
        if not any(abs(s['t'] - z) < 0.3 for s in sents[1:]):
            continue  # a pause inside a sentence is a breath, not a turn
        if all(z + MIN_PLAY <= b[0] or a >= b[1] + MIN_PLAY for b in breaks):
            breaks.append((a, z, next((s['text'] for s in reversed(sents) if s['t'] < a), ''), next((s['text'] for s in sents if s['t'] >= z - 0.05), '')))
    breaks.sort()

    marks = [(0.0, 'Hook', 'open', 2)]
    for a, z, said, nxt in breaks:
        marks += [(a, said, 'break', 0), (z, nxt, 'back', None)]
    for s in speech.get('sections', [])[1:]:
        if all(abs(s['t'] - m[0]) >= 6 for m in marks) and s['t'] < end - 4:
            marks.append((s['t'], s['name'], 'section', s.get('level')))
    marks.sort(key=lambda m: m[0])
    while True:
        starts = [m[0] for m in marks] + [end]
        long = next(((i, starts[i], starts[i + 1]) for i in range(len(marks)) if marks[i][2] != 'break' and starts[i + 1] - starts[i] > 30), None)
        if not long:
            break
        i, a, z = long
        mid = min((s['t'] for s in sents if a + 10 < s['t'] < z - 10), key=lambda t: abs(t - (a + z) / 2), default=None)
        if mid is None:
            break
        marks.insert(i + 1, (mid, '', 'turn', None))

    parts, level, variant = [], 2, 'a'
    for i, (t, label, kind, lv) in enumerate(marks):
        t1 = marks[i + 1][0] if i + 1 < len(marks) else end
        if kind == 'break':
            parts.append({'t0': round(t, 3), 't1': round(t1, 3), 'kind': 'break', 'level': 0, 'label': label})
            continue
        if kind == 'back':
            level = min(4, level + 1)
        elif kind == 'section' and lv:
            level = max(level, min(4, lv))
        elif kind == 'turn':
            level = min(4, level + 1)
        variant = 'b' if variant == 'a' and i else 'a'
        if i == len(marks) - 1 and t1 - t > 3 and level < 4 and len(marks) > 3:
            level = min(4, level + 1)
        parts.append({'t0': round(t, 3), 't1': round(t1, 3), 'kind': 'play', 'level': level, 'variant': variant, 'label': label if kind == 'section' else ('Back in' if kind == 'back' else label or 'Lift')})
    merged = []
    for p in parts:
        prev = merged[-1] if merged else None
        if prev and p['kind'] == 'play' and prev['kind'] == 'play' and (p['t1'] - p['t0'] < 7 or prev['t1'] - prev['t0'] < 5):
            prev.update(t1=p['t1'], level=max(prev['level'], p['level']))
            continue
        merged.append(p)
    parts = merged
    for p in parts:
        lv = (edits or {}).get('levels', {}).get(f"{p['t0']:.2f}")
        if lv and p['kind'] == 'play':
            p['level'] = int(lv)
    anchors = [{'t': p['t0'], 'kind': 'change', 'label': p['label']} for p in parts if p['kind'] == 'play' and p['t0'] > 0]
    if loop:
        parts[-1].update(t1=round(length, 3), level=parts[0]['level'])
    anchors.append({'t': round(length if loop else end, 3), 'kind': 'end', 'label': 'Loop point' if loop else 'Last word'})
    return {'seconds': length, 'speechEnd': round(end, 3), 'parts': parts, 'anchors': anchors, 'breaks': len(breaks), 'loop': loop}


def beats_for(dur, bpm):
    f = dur * bpm / 60
    best = None
    for n in {max(4, round(f / 4) * 4), max(4, math.floor(f / 4) * 4), max(4, math.ceil(f / 4) * 4), max(2, round(f / 2) * 2), max(2, round(f))}:
        cost = abs(n / f - 1) + (0 if n % 4 == 0 else 0.006 if n % 2 == 0 else 0.014)
        if best is None or cost < best[0]:
            best = (cost, n)
    return best[1]


def fit(out, bpm_range, step=0.25):
    """Each part gets a whole number of beats; its tempo moves a few percent so its first downbeat is its spoken cue."""
    plays = [p for p in out['parts'] if p['kind'] == 'play']
    best = None
    for bpm in np.arange(bpm_range[0], bpm_range[1] + 1e-6, step):
        cost = 0
        for p in plays:
            dur = p['t1'] - p['t0']
            n = beats_for(dur, bpm)
            drift = abs(n * 60 / dur / bpm - 1)
            cost += dur * (drift + (0 if n % 4 == 0 else 0.004 if n % 2 == 0 else 0.01)) + (dur * 5 if drift > 0.03 else 0)
        cost += abs(bpm - sum(bpm_range) / 2) * 0.02
        if best is None or cost < best[0]:
            best = (cost, float(bpm))
    bpm = best[1]
    parts, bars, beats = [], [], []
    for p in out['parts']:
        q = dict(p)
        if p['kind'] == 'play':
            dur = p['t1'] - p['t0']
            n = beats_for(dur, bpm)
            q.update(beats=n, bpm=round(n * 60 / dur, 3))
            spb = dur / n
            q['beatTimes'] = [round(p['t0'] + k * spb, 4) for k in range(n)]
            beats += q['beatTimes']
            lead = n % 4
            bars += ([q['beatTimes'][0]] if lead else []) + q['beatTimes'][lead::4]
        parts.append(q)
    drift = max(abs(p['bpm'] / bpm - 1) for p in parts if p['kind'] == 'play') * 100
    return {'bpm': round(bpm, 2), 'parts': parts, 'bars': [round(b, 3) for b in bars], 'maxDriftPct': round(drift, 2)}


def load_outline(slug):
    speech = read_json(WORK / slug / 'speech.json')
    out = outline(speech)
    write_json(WORK / slug / 'outline.json', out)
    return speech, out
