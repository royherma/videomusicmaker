"""Composed lines over the bar chords: a motif that returns, is sequenced and answered, and phrases that breathe and cadence."""
import zlib

import numpy as np

CELLS = {
    'lyrical': [[2, 2], [3, 1], [1, 1, 2], [1.5, 0.5, 2], [2, 1, 1], [1, 3]],
    'flowing': [[1, 1, 1, 1], [0.5, 0.5, 1, 2], [1, 0.5, 0.5, 2], [1.5, 0.5, 1, 1], [1, 1, 2]],
    'swing': [[0.5] * 8, [1, 0.5, 0.5, 1, 1], [0.5, 0.5, 1, 0.5, 0.5, 1], [1.5, 0.5, 0.5, 0.5, 1], [-0.5, 0.5, 0.5, 0.5, 1, 1]],
    'drive': [[0.5] * 8, [1, 0.5, 0.5, 1, 1], [0.5, 0.5, 1, 0.5, 0.5, 1], [0.25] * 4 + [0.5] * 6],
}
CADENCE = {'lyrical': [3, -1], 'flowing': [2, 1, -1], 'swing': [1, 2, -1], 'drive': [1, 1, 1.5, -0.5]}
STEPS = [-2, -1, -1, -1, 1, 1, 1, 2, 0, 3, -3, 4]


def rng_for(*key):
    return np.random.default_rng(zlib.crc32('|'.join(map(str, key)).encode()))


def motif(rng, style, bars=2):
    rhythm = [d for _ in range(bars) for d in CELLS[style][rng.integers(len(CELLS[style]))]]
    steps, last = [], 0
    for _ in rhythm:
        s = int(rng.choice(STEPS))
        if abs(last) >= 3:
            s = -int(np.sign(last)) * int(rng.integers(1, 3))
        steps.append(s)
        last = s
    return rhythm, steps


def nearest(m, pcs, lo, hi):
    best = min((c for c in range(lo, hi + 1) if c % 12 in pcs), key=lambda c: abs(c - m), default=m)
    return best


def periods(nbars):
    """Phrase plan for a block: the theme from its first bar, the cadence on its last; an odd bar rests before the cadence."""
    slots, odd = nbars // 2, nbars % 2
    if not slots:
        return ['rest1'] * odd
    plan = [['A', 'A2', 'B', 'C'][i % 4] for i in range(slots - 1)]
    if plan and plan[-1] == 'C':
        plan[-1] = 'B'
    return plan + ['rest1'] * odd + ['C']


def line(bar_chords, key_pc, scale, beats, lo, hi, style, seed, energy=0):
    """[(beat, dur_beats, midi, vel)]: theme, theme moved up, contrast, theme's opening + cadence, ending on the last bar."""
    rng = rng_for(*seed)
    pcs_scale = {(key_pc + s) % 12 for s in scale}
    a_rhythm, a_steps = motif(rng, style)
    b_rhythm, b_steps = motif(rng, style, 1)
    head = int(round(len(a_rhythm) / 2))
    root0, tones0 = bar_chords[0]
    cur = nearest((lo + hi) // 2 - 3, {(root0 + t) % 12 for t in tones0}, lo, hi)
    notes, bar, phrase = [], 0, -1
    for seg in periods(beats // 4):
        if seg.startswith('rest'):
            bar += 1 if seg == 'rest1' else 2
            continue
        if seg == 'A':
            phrase += 1
        lift = 2 * (phrase % 2) + energy
        rhythm, steps, shift = {'A': (a_rhythm, a_steps, 0), 'A2': (a_rhythm, a_steps, 2 + lift),
                                'B': (b_rhythm + b_rhythm, b_steps + [-x for x in b_steps], lift),
                                'C': (a_rhythm[:head] + CADENCE[style], a_steps[:head] + [-1, -1, 0, 0], -2 - lift)}[seg]
        cur = step_scale(cur, shift, pcs_scale, lo, hi) if shift else cur
        pos, last = bar * 4, max(i for i, d in enumerate(rhythm) if d > 0)
        for i, d in enumerate(rhythm):
            if d < 0:
                pos += -d
                continue
            if pos >= beats - 1e-6:
                break
            root, tones = bar_chords[min(int(pos // 4), len(bar_chords) - 1)]
            chord_pcs = {(root + t) % 12 for t in tones}
            cur = step_scale(cur, steps[i % len(steps)], pcs_scale, lo, hi)
            if abs(pos % 2) < 1e-6 or d >= 1.5:
                cur = nearest(cur, chord_pcs, lo, hi)
            if seg == 'C' and i == last:
                cur = nearest(cur, {root % 12, (root + tones[1]) % 12}, lo, hi)
            vel = 0.72 + 0.18 * np.sin(np.pi * (pos % 32) / 32) + (0.08 if abs(pos % 4) < 1e-6 else 0) + rng.uniform(-0.04, 0.04)
            notes.append((pos, min(d, beats - pos), int(cur), round(float(vel), 2)))
            pos += d
        bar += 2
    return notes


def step_scale(m, k, pcs, lo, hi):
    """Move k scale steps from midi m, bouncing off the instrument's range."""
    d = 1 if k > 0 else -1
    for _ in range(abs(k)):
        n = m + d
        while n % 12 not in pcs:
            n += d
        if n < lo or n > hi:
            d = -d
            n = m + d
            while n % 12 not in pcs:
                n += d
        m = n
    return m


def walk(bar_chords, beats, octave, seed):
    """Walking bass, one note a beat: root on 1, chord tones through the bar, a half-step into the next root."""
    rng = rng_for(*seed)
    base = 12 * (octave + 1)
    notes = []
    for b in range(beats // 4 + (1 if beats % 4 else 0)):
        root, tones = bar_chords[min(b, len(bar_chords) - 1)]
        nxt = bar_chords[min(b + 1, len(bar_chords) - 1)][0]
        r = base + root
        third, fifth = r + tones[1], r + tones[2]
        path = [r, third if rng.random() < 0.6 else fifth, fifth if rng.random() < 0.6 else r + 12]
        target = min((base + nxt + o for o in (-12, 0, 12)), key=lambda m: abs(m - path[-1]))
        path.append(target + (1 if rng.random() < 0.5 else -1))
        for i, m in enumerate(path):
            pos = b * 4 + i
            if pos >= beats:
                break
            notes.append((pos, 1, m, 0.9 if i == 0 else 0.78))
    return notes
