"""Physical voice after fofrAI's Argon recipe: syllables -> LF glottal pulse + breath -> 5 cascaded resonators, min-jerk moves."""
import numpy as np
from numba import njit

from .dsp import SR, curve, filt

VOWELS = {
    'bass': {'a': ([600, 1040, 2250, 2450, 2750], [60, 70, 110, 120, 130]),
             'e': ([400, 1620, 2400, 2800, 3100], [40, 80, 100, 120, 120]),
             'i': ([250, 1750, 2600, 3050, 3340], [60, 90, 100, 120, 120]),
             'o': ([400, 750, 2400, 2600, 2900], [40, 80, 100, 120, 120]),
             'u': ([350, 600, 2400, 2675, 2950], [40, 80, 100, 120, 120])},
    'tenor': {'a': ([650, 1080, 2650, 2900, 3250], [80, 90, 120, 130, 140]),
              'e': ([400, 1700, 2600, 3200, 3580], [70, 80, 100, 120, 120]),
              'i': ([290, 1870, 2800, 3250, 3540], [40, 90, 100, 120, 120]),
              'o': ([400, 800, 2600, 2800, 3000], [40, 80, 100, 120, 120]),
              'u': ([350, 600, 2700, 2900, 3300], [40, 60, 100, 120, 120])},
    'alto': {'a': ([800, 1150, 2800, 3500, 4950], [80, 90, 120, 130, 140]),
             'e': ([400, 1600, 2700, 3300, 4950], [60, 80, 120, 150, 200]),
             'i': ([350, 1700, 2700, 3700, 4950], [50, 100, 120, 150, 200]),
             'o': ([450, 800, 2830, 3500, 4950], [70, 80, 100, 130, 135]),
             'u': ([325, 700, 2530, 3500, 4950], [50, 60, 170, 180, 200])},
    'soprano': {'a': ([800, 1150, 2900, 3900, 4950], [80, 90, 120, 130, 140]),
                'e': ([350, 2000, 2800, 3600, 4950], [60, 100, 120, 150, 200]),
                'i': ([270, 2140, 2950, 3900, 4950], [60, 90, 100, 120, 120]),
                'o': ([450, 800, 2830, 3800, 4950], [70, 80, 100, 130, 135]),
                'u': ([325, 700, 2700, 3800, 4950], [50, 60, 170, 180, 200])},
}
MALE = {'E': [500, 1500, 2500, 3300, 3750], 'A': [660, 1720, 2410, 3300, 3750], 'O': [570, 840, 2410, 3300, 3750],
        'M': [250, 1000, 2200, 3300, 3750]}
FEMALE = {'E': [550, 1700, 2800, 3900, 4500], 'A': [860, 2050, 2850, 3900, 4500], 'O': [590, 920, 2710, 3900, 4500],
          'M': [300, 1100, 2600, 3900, 4500]}
for part, extra in (('bass', MALE), ('tenor', MALE), ('alto', FEMALE), ('soprano', FEMALE)):
    for v, F in extra.items():
        VOWELS[part][v] = (F, [200, 220, 250, 280, 300] if v == 'M' else [80, 90, 120, 150, 200])
VOWEL_KEYS = 'aeiouEAOM'
# onset/coda consonants: formant targets F1-F3 (None = the vowel's), voicing, aspiration, length, frication band, closure
CONS = {
    'l': dict(F=(360, 1300, 2900), av=0.7, dur=0.07),
    'r': dict(F=(400, 1350, 2300), av=0.5, dur=0.03),
    'm': dict(F=(250, 1000, 2200), av=0.3, dur=0.08, b1=150),
    'n': dict(F=(250, 1600, 2600), av=0.3, dur=0.07, b1=150),
    'w': dict(F=(300, 650, 2200), av=0.6, dur=0.06),
    'y': dict(F=(260, 2100, 3000), av=0.6, dur=0.05),
    'v': dict(F=(300, 1300, 2400), av=0.4, dur=0.06, fric=(1500, 7000), af=0.08),
    'h': dict(F=None, av=0.0, ah=0.45, dur=0.07),
    's': dict(F=None, av=0.0, dur=0.1, fric=(4500, 10000), af=0.35),
    'S': dict(F=None, av=0.0, dur=0.12, fric=(1800, 6500), af=0.45),
    'f': dict(F=None, av=0.0, dur=0.09, fric=(1200, 9000), af=0.15),
    'z': dict(F=(300, 1500, 2500), av=0.3, dur=0.08, fric=(4000, 9000), af=0.2),
    'k': dict(F=(300, 1900, 2600), av=0.0, dur=0.1, closure=0.05, fric=(1500, 3500), af=0.5, ah=0.6),
    'g': dict(F=(300, 1900, 2600), av=0.08, dur=0.07, closure=0.045, fric=(1500, 3500), af=0.25),
    't': dict(F=(300, 1700, 2700), av=0.0, dur=0.09, closure=0.045, fric=(3500, 9000), af=0.45, ah=0.5),
    'd': dict(F=(300, 1700, 2700), av=0.08, dur=0.06, closure=0.04, fric=(3000, 8000), af=0.2),
    'p': dict(F=(250, 800, 2200), av=0.0, dur=0.09, closure=0.05, fric=(300, 2500), af=0.4, ah=0.5),
    'b': dict(F=(250, 800, 2200), av=0.08, dur=0.06, closure=0.045, fric=(300, 2500), af=0.2),
}


def parse(syl):
    """'kri' -> (['k', 'r'], ['i'], []); 'hei' -> (['h'], ['e', 'i'], []); '-' holds the previous vowel."""
    if syl == '-':
        return None
    syl = syl.replace('sh', 'S')
    i = 0
    on = []
    while i < len(syl) and syl[i] not in VOWEL_KEYS:
        on.append(syl[i])
        i += 1
    vs = []
    while i < len(syl) and syl[i] in VOWEL_KEYS:
        vs.append(syl[i])
        i += 1
    return on, vs or ['a'], list(syl[i:])


def minjerk(u):
    u = np.clip(u, 0, 1)
    return u ** 3 * (10 - 15 * u + 6 * u ** 2)


def tracks(notes, sylls, part, total, rate=1000):
    """Segments (start, params, move time) -> per-ms tracks; each change eases in on a minimum-jerk curve."""
    segs = []
    silent = lambda v: dict(F=VOWELS[part][v][0], B=VOWELS[part][v][1], av=0.0, ah=0.0)
    first = parse(next(s for s in sylls if s != '-'))[1][0]
    segs.append((0.0, silent(first), 0.02))
    fric = []
    prev_v = first
    for (s, d, _, vel, _), syl in zip(notes, sylls):
        p = parse(syl)
        if p is None:
            continue
        on, vs, coda = p
        vF, vB = VOWELS[part][vs[0]]
        lead = sum(CONS[c]['dur'] for c in on)
        t = s - lead
        for c in on:
            cs = CONS[c]
            F = list(cs['F']) + vF[3:] if cs['F'] else vF
            B = list(vB)
            if 'b1' in cs:
                B[0] = cs['b1']
            if 'closure' in cs:
                segs.append((t, dict(F=F, B=B, av=cs['av'] * vel, ah=0.0), 0.015))
                tb = t + cs['closure']
                fric.append((tb, 0.015, cs['fric'], cs['af'] * vel))
                if cs.get('ah'):
                    segs.append((tb + 0.012, dict(F=vF, B=vB, av=0.0, ah=cs['ah'] * vel), 0.02))
            else:
                segs.append((t, dict(F=F, B=B, av=cs['av'] * vel, ah=cs.get('ah', 0.0) * vel), 0.03))
                if 'fric' in cs:
                    fric.append((t, cs['dur'], cs['fric'], cs['af'] * vel))
            t += cs['dur']
        segs.append((s, dict(F=vF, B=vB, av=vel, ah=0.04 * vel), 0.05 if on else 0.08))
        if len(vs) > 1:
            F2, B2 = VOWELS[part][vs[1]]
            segs.append((s + d * 0.55, dict(F=F2, B=B2, av=vel * 0.9, ah=0.04 * vel), d * 0.3))
        end = s + d
        tc = end
        for c in coda[::-1]:
            tc -= CONS[c]['dur']
        for c in coda:
            cs = CONS[c]
            F = list(cs['F']) + vF[3:] if cs['F'] else vF
            segs.append((tc, dict(F=F, B=list(vB), av=cs['av'] * vel, ah=cs.get('ah', 0.0) * vel), 0.04))
            if 'fric' in cs:
                fric.append((tc, cs['dur'], cs['fric'], cs['af'] * vel))
            tc += cs['dur']
        segs.append((end, silent(vs[-1]), 0.06))
        prev_v = vs[-1]
    segs.sort(key=lambda x: x[0])
    n = int(total * rate)
    tt = np.arange(n) / rate
    keys = ['F0', 'F1', 'F2', 'F3', 'F4', 'B0', 'B1', 'B2', 'B3', 'B4', 'av', 'ah']
    flat = lambda d: [*d['F'], *d['B'], d['av'], d['ah']]
    out = np.zeros((len(keys), n))
    cur = np.array(flat(segs[0][1]), float)
    out[:] = cur[:, None]
    for k, (t0, d, move) in enumerate(segs):
        t1 = segs[k + 1][0] if k + 1 < len(segs) else total
        i0, i1 = max(0, int(t0 * rate)), min(n, int(t1 * rate))
        if i1 <= i0:
            continue
        start = out[:, i0].copy() if i0 < n else cur
        tgt = np.array(flat(d), float)
        w = minjerk((tt[i0:i1] - t0) / max(move, 1e-3))
        out[:, i0:i1] = start[:, None] + (tgt - start)[:, None] * w[None, :]
        if i1 < n:
            out[:, i1:] = out[:, i1 - 1:i1]
    return out, fric


@njit(cache=True)
def _lf_params(rd):
    ra = (-1 + 4.8 * rd) / 100
    rk = (22.4 + 11.8 * rd) / 100
    rg = 0.25 * rk / (0.11 * rd / (0.5 + 1.2 * rk) - ra)
    tp = 1 / (2 * rg)
    te = min(tp * (1 + rk), 0.97)
    ta = max(ra, 0.002)
    tc = 1 - te
    eps = 1 / ta
    for _ in range(40):
        eps = (1 - np.exp(-eps * tc)) / ta
    w = np.pi / tp
    iret = -(1 / (eps * ta)) * ((1 - np.exp(-eps * tc)) / eps - tc * np.exp(-eps * tc))
    lo, hi = -20.0, 60.0
    a = 0.0
    for _ in range(60):
        a = 0.5 * (lo + hi)
        e0 = -1 / (np.exp(a * te) * np.sin(w * te))
        iopen = e0 * (np.exp(a * te) * (a * np.sin(w * te) - w * np.cos(w * te)) + w) / (a * a + w * w)
        if iopen + iret > 0:
            lo = a
        else:
            hi = a
    e0 = -1 / (np.exp(a * te) * np.sin(w * te))
    return te, ta, tc, eps, w, a, e0


@njit(cache=True)
def synth(f0, rd, av, ah, F, B, jitter, shimmer, seed):
    """Per sample: LF glottal-flow derivative (+ breath while the folds are open) through 5 resonators in series."""
    np.random.seed(seed)
    n = len(f0)
    y = np.zeros(n)
    z1 = np.zeros(5)
    z2 = np.zeros(5)
    ph = 1.0
    T0 = 1.0
    te, ta, tc, eps, w, a, e0 = _lf_params(1.0)
    amp = 1.0
    nz_lp = 0.0
    for i in range(n):
        if ph >= 1.0:
            ph -= 1.0
            T0 = (1.0 / max(f0[i], 40.0)) * (1 + jitter * np.random.randn())
            te, ta, tc, eps, w, a, e0 = _lf_params(min(2.6, max(0.35, rd[i])))
            amp = 1 + shimmer * np.random.randn()
        t = ph
        if t <= te:
            e = e0 * np.exp(a * t) * np.sin(w * t)
            open_ = 1.0
        else:
            e = -(1 / (eps * ta)) * (np.exp(-eps * (t - te)) - np.exp(-eps * tc))
            open_ = 0.25
        ph += 1.0 / (T0 * SR)
        nz_lp = 0.6 * nz_lp + 0.4 * np.random.randn()
        x = e * av[i] * amp * 0.12 + nz_lp * ah[i] * open_ * 0.08
        for j in range(5):
            bw = B[j, i] + (60.0 * open_ if j == 0 else 0.0)
            r = np.exp(-np.pi * bw / SR)
            c = -r * r
            b = 2 * r * np.cos(2 * np.pi * F[j, i] / SR)
            aa = 1 - b - c
            out = aa * x + b * z1[j] + c * z2[j]
            z2[j] = z1[j]
            z1[j] = out
            x = out
        y[i] = x
    return y


def voice(notes, sylls, part, total=None, seed=0, rd=1.0, breath=1.0, jitter=0.005, shimmer=0.05, shift=1.0, ring=False,
          fall=0.0, **kw):
    pad = 0.25
    notes = [(s + pad, d, m, v, sl) for s, d, m, v, sl in notes]
    total = (total or max(s + d for s, d, *_ in notes) + 0.5) + pad
    kw = {'vib': (5.5, 0.18, 0.25), 'glide': 0.06, 'drift': 0.06, **kw}
    f0, env, os = curve(notes, total, seed=seed, **kw)
    if fall:
        dur = np.full(len(f0), 1.0)
        for s0, d, *_ in notes:
            dur[int(s0 * SR):int((s0 + d) * SR) + int(0.2 * SR)] = d
        f0 = f0 * 2 ** (fall / 12 * np.clip(os / dur, 0, 1.3) ** 1.5)
    tr, fric = tracks(notes, sylls, part, total)
    n = len(f0)
    up = lambda r: np.interp(np.arange(n), np.arange(len(r)) * SR / 1000, r)
    F = np.stack([up(tr[j]) * shift for j in range(5)])
    if ring:
        F[2:] = np.array([2800.0, 3200.0, 3700.0])[:, None] * shift
    B = np.stack([up(tr[5 + j]) for j in range(5)])
    av, ah = up(tr[10]), up(tr[11]) * breath
    rdv = rd + 0.5 * (1 - np.clip(av, 0, 1))
    y = synth(f0, rdv, av, ah, F, B, jitter, shimmer, seed)
    rng = np.random.default_rng(seed + 99)
    for t0, dur, band, amp in fric:
        i0, m = int(t0 * SR), int(dur * SR)
        if i0 < 0 or m <= 0 or i0 + m > n:
            continue
        nz = filt(rng.standard_normal(m + 400), 'band', band)[400:] * amp * 0.05
        nz *= np.sin(np.linspace(0, np.pi, m)) ** 0.5
        y[i0:i0 + m] += nz
    return y
