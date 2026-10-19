"""DSP for the physical (code-made) instruments: phrase curves, additive voices, plucked strings, struck modes, bowed strings."""
import numpy as np
from numba import njit
from scipy.signal import butter, fftconvolve, sosfilt

SR = 48000
CR = 64
NAMES = {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11}


def midi(n):
    if not isinstance(n, str):
        return float(n)
    n = n.rstrip('~')
    rest, acc = n[1:], 0
    while rest and rest[0] in '#b':
        acc += 1 if rest[0] == '#' else -1
        rest = rest[1:]
    return 12 * (int(rest) + 1) + NAMES[n[0]] + acc


def hz(m):
    return 440.0 * 2 ** ((np.asarray(m) - 69) / 12)


def seq(text, bpm, vel=0.8):
    """'C5 1, D5 .5 0.6, r .5, C4+E4 2, E5~ 1' -> lines of (start, dur, midi, vel, slide); '+' stacks a chord, '~' slides in."""
    beat, t, out = 60 / bpm, 0.0, []
    for tok in text.replace('\n', ' ').split(','):
        p = tok.split()
        if not p:
            continue
        b = float(p[1]) * beat
        v = float(p[2]) if len(p) > 2 else vel
        if p[0] != 'r':
            for n in p[0].split('+'):
                out.append((t, b, midi(n), v, n.endswith('~')))
        t += b
    return out


def end_of(notes):
    return max(s + d for s, d, *_ in notes)


def filt(x, kind, cut, order=2):
    return sosfilt(butter(order, np.clip(np.array(cut) / (SR / 2), 1e-4, 0.999), btype=kind, output='sos'), x)


def peak(x, f0, db, q=0.9):
    a, w = 10 ** (db / 40), 2 * np.pi * f0 / SR
    al = np.sin(w) / (2 * q)
    b = np.array([1 + al * a, -2 * np.cos(w), 1 - al * a]) / (1 + al / a)
    aa = np.array([1, -2 * np.cos(w) / (1 + al / a), (1 - al / a) / (1 + al / a)])
    return sosfilt(np.concatenate([b, aa])[None, :], x)


def smooth_noise(n, hz_cut, seed):
    m = max(8, n // 48)
    sos = butter(2, min(0.99, hz_cut / 500), btype='low', output='sos')
    w = sosfilt(sos, np.random.default_rng(seed).standard_normal(m + 2000))[2000:]
    w = (w - w.mean()) / (w.std() + 1e-9)
    return np.interp(np.arange(n), np.linspace(0, n - 1, m), w)


def movavg(x, n):
    n = max(1, int(n))
    if n == 1:
        return x
    p = np.concatenate([np.full(n // 2, x[0]), x, np.full(n - n // 2 - 1, x[-1])])
    c = np.cumsum(np.insert(p, 0, 0.0))
    return (c[n:] - c[:-n]) / n


@njit(cache=True)
def follow(x, a_coef, r_coef):
    y = np.empty_like(x)
    s = 0.0
    for i in range(len(x)):
        c = a_coef if x[i] > s else r_coef
        s += c * (x[i] - s)
        y[i] = s
    return y


def coef(tau):
    return 1 - np.exp(-1 / (max(tau, 1e-4) * SR))


def curve(notes, total, glide=0.03, vib=(5.5, 0.0, 0.3), drift=0.04, scoop=(0.0, 0.06), attack=0.02, release=0.1,
          artic=0.3, legato=1.0, amp_vib=0.0, seed=0, slide_t=0.18):
    """One monophonic line -> per-sample frequency (Hz), amplitude envelope and time since the note started."""
    n = int(total * SR)
    t = np.arange(n) / SR
    m = np.full(n, np.nan)
    a = np.zeros(n)
    starts = np.full(n, np.nan)
    slid = np.zeros(n, bool)
    prev = None
    for s, d, mm, v, slide in notes:
        i0, i1 = int(s * SR), min(n, int((s + d * legato) * SR))
        m[i0:i1] = mm
        a[i0:i1] = v
        if slide and prev is not None:
            k = min(i1 - i0, int(slide_t * SR))
            m[i0:i0 + k] = np.linspace(prev, mm, k)
            slid[i0:i1] = True
        else:
            starts[i0] = s
        prev = mm
    first = notes[0][2]
    m[:int(notes[0][0] * SR)] = first
    idx = np.where(~np.isnan(m), np.arange(n), 0)
    np.maximum.accumulate(idx, out=idx)
    m = m[idx]
    m[np.isnan(m)] = first
    sidx = np.where(~np.isnan(starts), np.arange(n), 0)
    np.maximum.accumulate(sidx, out=sidx)
    st = starts[sidx]
    st[np.isnan(st)] = 0
    os = t - st
    m = movavg(m, glide * SR)
    ramp = np.clip((os - vib[2]) / 0.35, 0, 1)
    rate = vib[0] * (1 + 0.06 * smooth_noise(n, 1.5, seed + 1))
    phase = 2 * np.pi * np.cumsum(rate) / SR
    sc = np.where(slid, 0, -scoop[0] * np.exp(-os / scoop[1]))
    pitch = m + vib[1] * ramp * np.sin(phase) + drift * smooth_noise(n, 3, seed + 2) + sc
    dip = np.where(slid, 1, 1 - artic * np.exp(-os / 0.03))
    env = follow(a * dip, coef(attack), coef(release))
    if amp_vib:
        env *= 1 + amp_vib * ramp * np.sin(phase)
    return hz(pitch), env, os


def reson(f, F, B):
    return 1 / np.sqrt(1 + ((f - F) / (B / 2)) ** 2)


def cnoise(n, cut, rng, rate=SR / CR):
    w = sosfilt(butter(2, min(0.99, cut / (rate / 2)), btype='low', output='sos'), rng.standard_normal(n + 400))[400:]
    return w / (w.std() + 1e-9)


def harmonic(f, env, spec, kmax=48, seed=0, jitter=0.0, shimmer=0.0, rough=0.0, rough_cut=40):
    """Additive voice: harmonic k gets spec(k, k*f, env) at control rate, so its loudness follows pitch and dynamics.
    jitter/shimmer: fast pitch/level wobble (fraction); rough: each harmonic's level wobbles on its own (bow, breath)."""
    n = len(f)
    rng = np.random.default_rng(seed)
    idx = np.arange(0, n, CR)
    if jitter:
        f = f * (1 + jitter * np.interp(np.arange(n), idx, cnoise(len(idx), 70, rng)))
    ph = 2 * np.pi * np.cumsum(f) / SR
    fc, ec = f[idx], env[idx]
    if shimmer:
        ec = ec * (1 + shimmer * cnoise(len(idx), 60, rng))
    ta = np.arange(n)
    out = np.zeros(n)
    for k in range(1, kmax + 1):
        fk = k * fc
        if fk.min() > 0.44 * SR:
            break
        amp = spec(k, fk, ec) * np.clip((0.44 * SR - fk) / 1500, 0, 1)
        if amp.max() < 1e-6:
            continue
        if rough:
            amp = amp * np.clip(1 + rough * min(1.0, 0.3 + k / 8) * cnoise(len(idx), rough_cut, rng), 0, None)
        out += np.interp(ta, idx, amp) * np.sin(k * ph + rng.uniform(0, 2 * np.pi))
    return out


def airy(tone, level, bw=300, seed=0):
    """Breath that sits on the pitch: the tone times narrow noise puts a noise band around every harmonic."""
    nz = filt(np.random.default_rng(seed).standard_normal(len(tone)), 'low', bw)
    return tone * nz * level / (nz.std() + 1e-9)


def random_modes(n, fmin, fmax, q=(12, 35), gain=(0.2, 1.0), seed=0):
    rng = np.random.default_rng(seed)
    F = np.exp(rng.uniform(np.log(fmin), np.log(fmax), n))
    return [(f, f / rng.uniform(*q), rng.uniform(*gain)) for f in F]


def body_ir(modes, seconds=0.4, seed=0, direct=0.3):
    """Impulse response of a wooden body: decaying sines at each mode (F, Q-derived decay, gain)."""
    t = np.arange(int(seconds * SR)) / SR
    rng = np.random.default_rng(seed)
    ir = np.zeros_like(t)
    for F, B, g in modes:
        ir += g * np.exp(-np.pi * B * t) * np.sin(2 * np.pi * F * t + rng.uniform(0, 6.28))
    ir /= np.sqrt((ir ** 2).sum()) + 1e-9
    ir[0] += direct
    return ir


def through(x2, ir, wet=1.0):
    y = np.stack([fftconvolve(c, ir)[:x2.shape[1]] for c in x2])
    y *= np.sqrt((x2 ** 2).mean() / ((y ** 2).mean() + 1e-12))
    return x2 * (1 - wet) + y * wet


def breath(env, os, level, band, seed, burst=0.0, burst_t=0.04):
    nz = filt(np.random.default_rng(seed).standard_normal(len(env)), 'band', band)
    return nz * env * (level + burst * np.exp(-os / burst_t))


@njit(cache=True)
def ks_core(excite, D, damp, s, buzz):
    n = len(D)
    y = np.zeros(n)
    ne = len(excite)
    for i in range(n):
        d = D[i]
        if buzz > 0.0 and i > 0:
            d = d * (1.0 - buzz * min(1.0, abs(y[i - 1])))
        p = i - d
        j = int(np.floor(p))
        fr = p - j
        v0 = 0.0
        v1 = 0.0
        if j >= 1:
            v0 = y[j] * (1 - fr) + y[j + 1] * fr
            v1 = y[j - 1] * (1 - fr) + y[j] * fr
        y[i] = (excite[i] if i < ne else 0.0) + damp[i] * ((1 - s) * v0 + s * v1)
    return y


def pluck(f, dur, vel=0.8, t60=2.0, bright=0.5, pos=0.2, soft=4000, buzz=0.0, seed=0, f_curve=None, mute_at=None,
          shape=0.0, twang=0.003, planes=True):
    """Karplus-Strong string: an initial shape into a tuned delay loop; bright 0..1 sets how slowly the highs die.
    shape: 0 = noise (pick, quill), 1 = smooth triangle (finger). twang: pitch starts this much sharp (string stretch).
    planes: a second, slightly detuned copy (the string's other vibration plane) so the decay beats like a real one."""
    n = int(dur * SR)
    fq = f_curve if f_curve is not None else np.full(n, float(f))
    fq = fq * (1 + twang * vel * np.exp(-np.arange(n) / SR / 0.05))
    if planes:
        a = _pluck(fq, n, vel, t60, bright, pos, soft, buzz, seed, mute_at, shape)
        b = _pluck(fq * 1.0007, n, vel, t60 * 0.8, bright * 0.9, pos * 1.1, soft, buzz, seed + 7, mute_at, shape)
        return 0.62 * a + 0.38 * b
    return _pluck(fq, n, vel, t60, bright, pos, soft, buzz, seed, mute_at, shape)


def _pluck(fq, n, vel, t60, bright, pos, soft, buzz, seed, mute_at, shape):
    s = 0.5 * (1 - bright) + 0.02
    P = SR / fq
    D = P - s
    rng = np.random.default_rng(seed)
    L = int(P[0])
    k = max(1, int(pos * L))
    tri = np.concatenate([np.linspace(0, 1, k, endpoint=False), np.linspace(1, 0, L - k)])
    tri -= tri.mean()
    e = (shape * tri * 2 + (1 - shape) * filt(rng.uniform(-1, 1, L), 'low', soft, 1)) * vel
    if shape < 1:
        e[k:] -= e[:-k] * 0.9 * (1 - shape)
    damp = 10 ** (-3 / (fq * t60))
    if mute_at is not None:
        i = int(mute_at * SR)
        damp = damp.copy()
        damp[i:] = 10 ** (-3 / (fq[i:] * 0.06))
    return ks_core(e.astype(np.float64), D.astype(np.float64), damp.astype(np.float64), s, buzz)


def modal(f, partials, dur, vel=0.8, noise=0.0, noise_band=(500, 4000), noise_t=0.01, bend=0.0, bend_t=0.05, seed=0):
    """Struck object: decaying sines at partial ratios (ratio, amp, t60), plus a strike noise."""
    t = np.arange(int(dur * SR)) / SR
    rng = np.random.default_rng(seed)
    warp = 1 + bend * np.exp(-t / bend_t)
    x = np.zeros_like(t)
    for r, a, t60 in partials:
        fr = f * r
        if fr > 0.44 * SR:
            continue
        ph = 2 * np.pi * fr * np.cumsum(warp) / SR + rng.uniform(0, 6.28)
        x += a * np.exp(-6.9 * t / t60) * np.sin(ph)
    x *= np.minimum(1, t / 0.0008)
    if noise:
        x += filt(rng.standard_normal(len(t)), 'band', noise_band) * np.exp(-t / noise_t) * noise
    return x * vel


def pan(x, p=0.0):
    a = (p + 1) * np.pi / 4
    return np.stack([x * np.cos(a), x * np.sin(a)])


def place(buf, x, start, p=0.0):
    i = int(start * SR)
    if x.ndim == 1:
        x = pan(x, p)
    j = min(buf.shape[1], i + x.shape[1])
    if j > i:
        buf[:, i:j] += x[:, :j - i]


def blank(seconds):
    return np.zeros((2, int(seconds * SR)))


def room(seconds, seed=5, pre=0.018, bright=6000):
    rng = np.random.default_rng(seed)
    t = np.arange(int(seconds * SR)) / SR
    ir = rng.standard_normal((2, len(t))) * np.exp(-6.9 * t / seconds)
    ir = np.stack([filt(c, 'low', bright) for c in ir])
    ir[:, :int(pre * SR)] = 0
    return ir / np.sqrt((ir ** 2).sum(axis=1, keepdims=True))


def verb(x, seconds=2.0, wet=0.25, bright=6000):
    ir = room(seconds, bright=bright)
    w = np.stack([fftconvolve(x[0], ir[0])[:x.shape[1]], fftconvolve(x[1], ir[1])[:x.shape[1]]])
    return x * (1 - wet) + w * wet * 1.4


def finish(x, tail=1.0):
    x = np.concatenate([x, np.zeros((2, int(tail * SR)))], axis=1)
    x = x - x.mean(axis=1, keepdims=True)
    blk = x.mean(axis=0)[: len(x[0]) // 4800 * 4800].reshape(-1, 4800)
    r = np.sqrt((blk ** 2).mean(axis=1))
    loud = r[r > r.max() * 0.1]
    x *= 10 ** (-17 / 20) / (np.sqrt((loud ** 2).mean()) + 1e-9)
    pk = np.abs(x).max()
    if pk > 0.9:
        x = np.tanh(x / 0.9 * 1.0) * 0.9 if pk < 1.6 else x * 0.9 / pk
    fade = int(0.3 * SR)
    x[:, -fade:] *= np.linspace(1, 0, fade)
    return x.astype(np.float32)


@njit(cache=True)
def _read(buf, w, d):
    n = len(buf)
    p = w - d
    i0 = int(np.floor(p))
    fr = p - i0
    return buf[i0 % n] * (1 - fr) + buf[(i0 + 1) % n] * fr


@njit(cache=True)
def bow_core(f, bowv, slope, beta, pole, rosin, seed):
    """Bowed string as two delay lines (bridge side, nut side) meeting at the bow, which sticks and slips by a friction curve."""
    np.random.seed(seed)
    n = len(f)
    neck = np.zeros(8192)
    bridge = np.zeros(8192)
    out = np.zeros(n)
    lp = 0.0
    w = 0
    for i in range(n):
        base = 48000.0 / f[i] - 1.5
        nl = _read(neck, w, base * (1 - beta))
        bl = _read(bridge, w, base * beta)
        lp = 0.95 * (1 - pole) * bl + pole * lp
        bref = -lp
        nref = -nl
        vd = bowv[i] - (bref + nref) + rosin * np.random.randn() * abs(bowv[i])
        t = abs(vd * slope[i]) + 0.75
        t = t ** -4.0
        if t > 1.0:
            t = 1.0
        nv = vd * t
        neck[w % 8192] = bref + nv
        bridge[w % 8192] = nref + nv
        w += 1
        out[i] = bl
    return out
