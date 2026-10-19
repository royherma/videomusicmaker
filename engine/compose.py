"""A genre (engine/themes/<id>.json) played over a fitted grid: chords per bar, a pattern per layer, layers in or out by level."""
import json, re

import numpy as np

from . import melody as mel
from . import synth as sy
from .common import NOTES, THEMES

SR = sy.SR
SCALES = {'major': [0, 2, 4, 5, 7, 9, 11], 'minor': [0, 2, 3, 5, 7, 8, 10]}
ROMAN = ['I', 'II', 'III', 'IV', 'V', 'VI', 'VII']
RHYTHM = {'bar': 4, 'half': 2, 'beat': 1, '8': 0.5, '16': 0.25, 'triplet8': 1 / 3, 'dotted8': 0.75}
HITS = {'kick', 'snare', 'clap', 'hat', 'openhat', 'shaker', 'rim', 'tom'}


def themes():
    return {t['id']: t for t in (json.loads(p.read_text()) for p in sorted(THEMES.glob('*.json')))}


def chord(symbol, key, mode):
    """'VI', 'iv', 'IVmaj7', 'ii7', 'i9', 'Vsus2' -> pitch classes from the root, plus the root's pitch class."""
    m = re.match(r'^(b?)([ivIV]+)(.*)$', symbol)
    flat, num, ext = m.groups()
    degree = ROMAN.index(num.upper())
    root = (NOTES.index(key) + SCALES[mode][degree] - (1 if flat else 0)) % 12
    minor = num.islower()
    tones = [0, 3 if minor else 4, 7]
    if 'sus2' in ext:
        tones[1] = 2
    if 'maj7' in ext:
        tones.append(11)
    elif '7' in ext or '9' in ext:
        tones.append(10)
    if '9' in ext or 'add9' in ext:
        tones.append(14)
    return root, tones


def voicing(root, tones, octave, prev):
    base = 12 * (octave + 1) + root
    options = []
    for inv in range(len(tones)):
        v = sorted(base + t + (12 if i < inv else 0) for i, t in enumerate(tones))
        options += [v, [n - 12 for n in v]]
    if prev is None:
        return options[0]
    return min(options, key=lambda v: sum(abs(a - b) for a, b in zip(v, prev)) + abs(len(v) - len(prev)))


def steps_of(pattern):
    return [(i, {'x': 1.0, 'X': 1.25, 'o': 0.6, '-': 0.35}[c]) for i, c in enumerate(pattern.replace(' ', '')) if c in 'xXo-']


def with_edits(theme, e):
    """A genre with the user's changes: fixed tempo, another key, layers switched off."""
    t = {**theme, 'layers': {k: v for k, v in theme['layers'].items() if k not in (e.get('mute') or [])}}
    if e.get('bpm'):
        t['bpm'] = [float(e['bpm']), float(e['bpm'])]
    if e.get('key'):
        t['key'] = e['key']
    return t


def key_shift(theme, seed):
    shift = int(mel.rng_for('key', theme['id'], *seed).integers(-2, 3))
    if len(seed) == 2 and seed[1] > 1 and shift == key_shift(theme, (seed[0], seed[1] - 1)):
        shift = (shift + 3) % 5 - 2
    return shift


def take_key(theme, seed):
    return {**theme, 'key': NOTES[(NOTES.index(theme['key']) + key_shift(theme, seed)) % 12]}


def take_arp(seq, seed):
    rest = list(seq[1:])
    mel.rng_for(*seed).shuffle(rest)
    return [seq[0], *rest]


def compose(theme, grid, seconds, seed=()):
    """Returns (stems {layer: stereo array}, layers {layer: [[t0, t1]]}, events for the score)."""
    rng, arps = mel.rng_for(theme['id'], *seed), {}
    n = int((seconds + 2.5) * SR)
    mono = {name: np.zeros(n, np.float32) for name in theme['layers']}
    spans = {name: [] for name in theme['layers']}
    voices, events, lines = {}, [], {}
    key, mode = theme['key'], theme['mode']

    def put(name, x, t, inst=''):
        i = int(round((t - (sy.lead_in(x) if inst.startswith(('sf:', 'phys:')) else 0)) * SR))
        if i >= n or i + len(x) <= 0:
            return
        j = min(n, i + len(x))
        mono[name][max(0, i):j] += x[max(0, -i):j - i]

    plays = [p for p in grid['parts'] if p['kind'] == 'play']
    for pi, p in enumerate(plays):
        spb, n_beats = (p['t1'] - p['t0']) / p['beats'], p['beats']
        final = pi + 1 == len(plays)
        back = any(q['kind'] == 'break' and abs(q['t1'] - p['t0']) < 1e-3 for q in grid['parts'])
        variant = 'a' if back else p.get('variant', 'a')
        prog = theme['chords'].get(variant) or theme['chords']['a']
        lead = n_beats % 4
        said = [(t + 0.3 - p['t0']) / spb for t in grid.get('sentences', []) if p['t0'] + 4 * spb < t + 0.3 < p['t1'] - 8 * spb]
        target = (said[0] if back else min(said, key=lambda b: abs(b - n_beats / 2))) if said else n_beats / 2
        cut = int(min(max(0, 4 * round((target - lead) / 4)), (n_beats - lead) // 4 * 4))
        seam = cut + lead if back or lead else 0
        bars = [(4 * j, 4) for j in range(cut // 4)] + ([(cut, lead)] if lead else []) + [(cut + lead + 4 * j, 4) for j in range((n_beats - cut - lead) // 4)]
        cycle = lambda m: [prog[i % len(prog)] for i in range(m)]
        block = lambda m, tail: cycle(m) if m <= len(tail) else cycle(m - len(tail)) + tail
        first = sum(1 for b0, _ in bars if b0 < seam)
        names = block(first, [prog[-1]]) + block(len(bars) - first, [prog[-1], prog[0]] if final and not grid.get('loop') else [prog[-1]])
        bar_chords = [chord(c, key, mode) for c in names]
        blocks = [(bars[i][0], [bar_chords[j] for j in range(i, k)], sum(bars[j][1] for j in range(i, k))) for i, k in ((0, first), (first, len(bars))) if k > i]
        active = {k: L for k, L in theme['layers'].items() if L.get('from', 1) <= p['level'] <= L.get('to', 4)}
        struck = lambda L: L['inst'] in HITS or sy.is_hit(L['inst']) or not sy.slow(L['inst'])
        core = min((L.get('from', 1) for L in active.values()), default=1)
        anchor = lambda L: L.get('rhythm') in ('bar', 'half') and struck(L) and not (L['inst'] in HITS or sy.is_hit(L['inst']))
        light = {k for k, L in active.items() if L.get('from', 1) <= core or (L.get('notes') == 'melody' and not L.get('copy')) or anchor(L)}
        if back and not any(struck(active[k]) and active[k].get('notes') != 'melody' and not anchor(active[k]) for k in light):
            light.add(min((k for k, L in active.items() if struck(L) and L.get('notes') != 'melody' and not (L['inst'] in HITS or sy.is_hit(L['inst']))), key=lambda k: active[k].get('from', 1), default=next(iter(active), None)))
        stops = any(q['kind'] == 'break' and abs(q['t0'] - p['t1']) < 1e-3 for q in grid['parts'])
        button = bars[-1][0] + 2 if stops and bars[-1][1] == 4 else None
        end_of = p['t1'] if final or plays[pi + 1]['t0'] != p['t1'] else p['t1'] + 0.05
        let_go = p['t1'] - (0.5 if stops else 0)
        for name, L in theme['layers'].items():
            if p['level'] < L.get('from', 1) or p['level'] > L.get('to', 4) or (L.get('variant') and L['variant'] != p.get('variant')):
                continue
            entry = seam if back and name not in light else 0
            spans[name].append([p['t0'] + entry * spb, p['t1']])
            hit_layer = L['inst'] in HITS or sy.is_hit(L['inst'])
            if L.get('notes') in ('melody', 'walk'):
                line_seed = (theme['id'], name, variant, *seed)
                if L.get('copy'):
                    written = lines.get((L['copy'], pi), [])
                elif L['notes'] == 'walk':
                    written = [(b0 + q, d, m, v) for b0, ch, nb in blocks for q, d, m, v in mel.walk(ch, nb, L.get('octave', 1), line_seed)]
                    if button is not None:
                        root = bar_chords[-1][0] + 12 * (L.get('octave', 1) + 1)
                        written = [w for w in written if w[0] < button - 1e-6] + [(button, 2, root, 0.95)]
                else:
                    written = []
                    for b0, ch, nb in blocks:
                        full = [c for c, (x0, bl) in zip(ch, [b for b in bars if b0 <= b[0] < b0 + nb]) if bl == 4]
                        written += [(b0 + q, d, m, v) for q, d, m, v in mel.line(full, NOTES.index(key), SCALES[mode], 4 * len(full), *L['range'], L.get('style', 'lyrical'), line_seed, max(0, p['level'] - L.get('from', 1)))] if full else []
                lines[(name, pi)] = written
                for pos, d, m, v in written:
                    t = p['t0'] + pos * spb + ((L['swing'] - 0.5) * spb if L.get('swing') and abs(pos % 1 - 0.5) < 1e-6 else 0)
                    dur = min(d * spb * L.get('legato', 0.95), (let_go if stops else end_of) - t)
                    vel = v * L.get('vel', 0.85) * (1.12 if back and seam and abs(pos - seam) < 1e-6 else 1)
                    if dur >= 0.03 and pos >= entry - 1e-6:
                        put(name, sy.note(L['inst'], int(m + L.get('shift', 0)), round(dur, 2), round(min(1.2, vel), 2)), t + rng.uniform(-0.006, 0.006), L['inst'])
                        events.append(('note', t, min(1.0, vel), name, int(m + L.get('shift', 0)), round(dur, 2)))
                continue
            step = RHYTHM[L.get('rhythm', 'beat')] if L.get('rhythm') != 'steps' else 0.25
            if L.get('rhythm') == 'steps':
                per_bar = len(L['steps'].replace(' ', ''))
                slots = [(s * 4 / per_bar, acc, s) for s, acc in steps_of(L['steps'])]
            elif L.get('rhythm') == 'bar':
                slots = [(0, 1.0, 0)]
            else:
                slots = [(x * step, 1.0, x) for x in range(int(round(4 / step)))]
            events_at = [(b0 + ib, acc, s, j, b0, blen, False) for j, (b0, blen) in enumerate(bars) for ib, acc, s in slots
                         if ib < blen - 1e-6 and (button is None or b0 + ib < button - 1e-6)]
            if button is not None and L.get('rhythm') != 'bar' and (not hit_layer or L['inst'].split(':')[-1] in ('kick', 'tom')):
                events_at.append((button, 1.1, 0, len(bars) - 1, bars[-1][0], 4, True))
            for k, (pos, accent, slot, bar_i, b0, blen, is_button) in enumerate(events_at, 1):
                t = p['t0'] + pos * spb
                if L.get('swing') and slot % 2 == 1:
                    t += (L['swing'] - 0.5) * (0.5 if L.get('rhythm') == 'steps' else 2 * step) * spb
                root, tones = bar_chords[bar_i]
                vel = accent * L.get('vel', 0.85) * (1 + rng.uniform(-0.07, 0.07))
                if L.get('accent_first') and abs(pos - b0) < 1e-6:
                    vel *= 1.2
                if pos < entry - 1e-6:
                    continue
                if back and seam and abs(pos - seam) < 1e-6:
                    vel *= 1.12
                if hit_layer:
                    put(name, sy.hit(L['inst'], round(min(1.3, vel), 1)), t)
                    events.append((L['inst'].split(':')[-1], t, min(1.0, vel)))
                    continue
                if is_button:
                    dur = let_go - t
                elif L.get('pedal'):
                    dur = p['t0'] + (b0 + blen) * spb + 0.05 - t
                elif L.get('rhythm') == 'bar':
                    dur = L.get('len', 0.9) * blen * spb
                else:
                    dur = (L['hold'] * spb) if L.get('hold') else L.get('len', 0.9) * step * spb
                dur = min(dur, (let_go if stops else end_of) - t)
                if dur < 0.03:
                    continue
                notes = L.get('notes', 'root')
                octave = L.get('octave', 3)
                if notes == 'root':
                    pitches = [12 * (octave + 1) + root]
                elif notes == 'fifth':
                    pitches = [12 * (octave + 1) + root + (7 if k % 2 == 1 and not is_button else 0)]
                else:
                    v = voicing(root, tones, octave, voices.get(name))
                    voices[name] = v
                    if notes == 'chord' or is_button:
                        pitches = [v[0] - 12] + v + [v[0] + 12] if L.get('wide') else v
                    else:
                        seq = arps.get(name) or arps.setdefault(name, take_arp(L.get('arp', [0, 1, 2, 1]), (theme['id'], name, *seed)))
                        idx = seq[(k - 1) % len(seq)]
                        ext = ([v[0] - 12] if L.get('wide') else []) + v + [x + 12 for x in v]
                        pitches = [ext[idx % len(ext)]]
                jitter = 0 if L.get('tight') else rng.uniform(-0.004, 0.004)
                if L.get('strum') and abs(pos % 1) > 1e-6:
                    pitches, vel = pitches[::-1], vel * 0.8
                strum = 0.003 if back and pos < 1e-6 else L.get('strum', 0)
                for i, m in enumerate(pitches):
                    put(name, sy.note(L['inst'], int(m), round(dur, 2), round(min(1.2, vel), 2)), t + jitter + i * strum, L['inst'])
                    events.append(('note', t + jitter + i * strum, min(1.0, vel), name, int(m), round(dur, 2)))

    stems, rev_in, dly_in = {}, np.zeros(n, np.float32), np.zeros(n, np.float32)
    kicks = None
    if theme.get('duck'):
        kick_layer = theme['duck']['by']
        env = np.ones(n, np.float32)
        if kick_layer in mono:
            idx = np.flatnonzero(np.diff((np.abs(mono[kick_layer]) > 0.05).astype(np.int8)) == 1)
            tail = 1 - theme['duck']['depth'] * np.exp(-np.arange(int(0.3 * SR)) / (0.11 * SR))
            for i in idx:
                env[i:i + len(tail)] = np.minimum(env[i:i + len(tail)], tail[:n - i])
        kicks = env
    quiet = np.ones(n, np.float32)
    room_fade = quiet.copy()
    for q in grid['parts']:
        if q['kind'] == 'break':
            a, b = int(q['t0'] * SR), min(n, int(q['t1'] * SR))
            r = min(int(0.15 * SR), a)
            quiet[a - r:a] = np.linspace(1, 0, r)
            quiet[a:b] = 0
            r = min(int(0.5 * SR), a)
            room_fade[a - r:a] = np.minimum(room_fade[a - r:a], np.linspace(1, 0, r) ** 2)
    for name, L in theme['layers'].items():
        x = mono[name] * 10 ** (L.get('gain', 0) / 20) * quiet
        if L.get('hp'):
            x = sy.filt(x, 'high', L['hp']).astype(np.float32)
        if L.get('lp'):
            x = sy.filt(x, 'low', L['lp']).astype(np.float32)
        if kicks is not None and name in theme['duck'].get('layers', []):
            x = x * kicks
        if L.get('duckVoice') and grid.get('voice') is not None:
            talk = np.interp(np.arange(n) / SR, np.arange(len(grid['voice'])) / 100, grid['voice'])
            x = x * (10 ** (-L['duckVoice'] * talk / 20)).astype(np.float32)
        pan = L.get('pan', 0)
        st = np.stack([x * np.sqrt((1 - pan) / 2) * 1.41, x * np.sqrt((1 + pan) / 2) * 1.41])
        stems[name] = st
        rev_in += x * L.get('send', 0)
        dly_in += x * L.get('delay', 0)
    fx = theme.get('fx', {})
    bus = sy.reverb(rev_in, fx.get('room', 2.2)) * fx.get('wet', 1.0)
    if dly_in.any():
        bus += sy.delay(dly_in, 0.75 * 60 / grid['bpm'], 0.38)
    stems['space'] = bus * quiet * room_fade

    hits = np.zeros(n, np.float32)
    for i, p in enumerate(plays):
        if i == 0 and fx.get('open') and fx.get('impact', 0):
            x = sy.hit('impact', 1.0) * fx['impact']
            a = int(p['t0'] * SR)
            hits[a:a + len(x)] += x[:n - a]
            events.append(('impact', p['t0'], 1.0))
    end = grid['speechEnd'] if 'speechEnd' in grid else plays[-1]['t1']
    root, tones = chord((theme['chords'].get(plays[-1].get('variant', 'a')) or theme['chords']['a'])[0], key, mode)
    ring = sum(sy.note(theme.get('end', 'pad'), int(12 * (theme.get('endOctave', 3) + 1) + root + t), 2.0, 0.9) for t in tones)
    a = int(end * SR)
    if not grid.get('loop'):
        hits[a:a + len(ring)] += (ring * 1.4)[:n - a]
    if fx.get('impact') and not grid.get('loop'):
        x = sy.hit('impact', 0.8) * fx['impact'] * 0.7
        hits[a:a + len(x)] += x[:n - a]
    stems['moments'] = np.stack([hits, hits]) + sy.reverb(hits * 0.25, 2.8)
    if fx.get('vinyl'):
        v = sy.vinyl(n) * fx['vinyl'] * quiet * room_fade
        stems['moments'] += np.stack([v, np.roll(v, 37)])
    if grid.get('loop'):
        stems = {k: wrap(x, int(round(seconds * SR))) for k, x in stems.items()}
    return stems, {k: v for k, v in spans.items() if v}, events


def wrap(x, length):
    """Whatever rings past the loop point is added onto the start, so the end flows into the first second."""
    x = x.copy()
    over = x[..., length:]
    x[..., :over.shape[-1]] += over[..., :length]
    return x[..., :length]
