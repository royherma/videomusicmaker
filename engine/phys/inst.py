"""Physical instruments, one note at a time: phys:<name> in a theme layer. Ported from the approved instrument trial."""
import numpy as np
from scipy.signal import fftconvolve

from .dsp import (SR, airy, body_ir, bow_core, breath, curve, harmonic, hz, modal, movavg, peak, pluck, random_modes, reson,
                  smooth_noise)
from .voice import voice

VIOLIN_BODY = [(280, 30, 1.2), (460, 40, 0.9), (530, 50, 1.0), (700, 80, 0.4), (1000, 250, 0.5), (1600, 300, 0.3),
               (2400, 700, 0.9), (3200, 600, 0.5), (4500, 1000, 0.2)] + random_modes(28, 600, 7000, (10, 30), (0.15, 0.8), 11)
CELLO_BODY = [(105, 20, 0.8), (195, 25, 1.0), (290, 35, 1.0), (420, 60, 0.7), (600, 100, 0.4), (1100, 300, 0.4),
              (1800, 500, 0.6), (2800, 700, 0.3)] + random_modes(28, 250, 4500, (10, 30), (0.15, 0.8), 12)
GUITAR_BODY = [(100, 12, 1.0), (195, 15, 0.9), (245, 20, 0.5), (390, 25, 0.6), (480, 30, 0.4)] + random_modes(40, 500, 5000, (8, 25), (0.1, 0.5), 21)
HARP_BODY = [(150, 15, 0.6), (300, 20, 0.8), (600, 30, 0.5)] + random_modes(30, 300, 4000, (8, 25), (0.1, 0.5), 22)
BANJO_BODY = [(380, 20, 1.2), (620, 30, 0.8)] + random_modes(30, 800, 6000, (15, 40), (0.2, 0.8), 23)
SITAR_BODY = [(240, 20, 1.0), (480, 30, 0.6)] + random_modes(30, 600, 6000, (10, 30), (0.2, 0.7), 24)
IR = {}


def ir(name, body, seconds, seed, direct):
    if name not in IR:
        IR[name] = body_ir(body, seconds, seed, direct)
    return IR[name]


def one(midi, dur, vel, tail):
    return [(0.0, dur, float(midi), vel, False)], dur + tail


def body(x, name, modes, seconds=0.35, seed=1, direct=0.2, wet=0.85):
    y = fftconvolve(x, ir(name, modes, seconds, seed, direct))[:len(x)]
    y *= np.sqrt((x ** 2).mean() / ((y ** 2).mean() + 1e-12))
    return x * (1 - wet) + y * wet


def brass_spec(fc0, fcg, hp=250, bell=(1200, 900, 0.8), mute=False):
    def spec(k, fk, e):
        s = e / (1 + (fk / (fc0 + fcg * e ** 2)) ** 2) * fk / (fk + hp)
        s = s * (1 + bell[2] * reson(fk, bell[0], bell[1]))
        if mute:
            s = s * (fk / (fk + 900)) ** 2 * (0.25 + 3 * reson(fk, 1800, 700)) / (1 + (fk / 5000) ** 4)
        return s
    return spec


def brass(midi, dur, vel, fc0, fcg, hp=250, bell=(1200, 900, 0.8), mute=False, **kw):
    notes, total = one(midi, dur, vel, 0.3)
    kw = {'vib': (5.2, 0.12, 0.35), 'scoop': (0.35, 0.04), 'attack': 0.025, 'release': 0.07, **kw}
    f, env, os = curve(notes, total, seed=int(midi), **kw)
    return harmonic(f, env, brass_spec(fc0, fcg, hp, bell, mute), seed=int(midi)) + breath(env, os, 0.004, (1200, 5000), 1, burst=0.05)


def bowed(midi, dur, vel, modes=VIOLIN_BODY, name='violin', bright=2600, players=1, **kw):
    notes, total = one(midi, dur, vel, 0.4)
    out = 0
    for p in range(players):
        seed = int(midi) * 7 + p
        det = [(s, d, m + (p - (players - 1) / 2) * 0.08, v, sl) for s, d, m, v, sl in notes]
        kv = {'vib': (5.8 - 0.4 * p, 0.22, 0.18), 'glide': 0.05, 'attack': 0.08, 'release': 0.12, 'drift': 0.05, **kw}
        f, env, _ = curve(det, total, seed=seed, **kv)
        pressure = 1.5 * (1 + 0.15 * smooth_noise(len(f), 4, seed + 5))
        y = bow_core(np.maximum(f, 40.0), 0.11 * env, pressure, 0.127, 0.35, 0.1, seed)
        out = out + y / (np.abs(y).max() + 1e-9)
    y = body(out, name, modes, direct=0.15, wet=1.0)
    return peak(peak(y, bright, 9.0, 0.7), 4500, 4.5, 0.8)


def spiccato(midi, dur, vel):
    x = bowed(midi, min(dur, 0.2), vel, players=2, attack=0.006, release=0.05, vib=(5.5, 0.05, 0.3), artic=0.0)
    n = int(0.012 * SR)
    bite = np.random.default_rng(int(midi)).standard_normal(n) * np.linspace(1, 0, n) * np.abs(x).max() * 0.6
    x[:n] += bite
    t = np.arange(len(x)) / SR
    return x * np.exp(-t / 0.09) * 2.5


def flute_spec(k, fk, e):
    return e * {1: 1.0, 2: 0.3 * e, 3: 0.14 * e ** 2, 4: 0.06 * e ** 2, 5: 0.03 * e ** 3}.get(k, 0.0 * e)


def clarinet_spec(k, fk, e):
    s = e / k * (1.0 if k % 2 else np.where(fk < 1600, 0.06, 0.45))
    return s / (1 + (fk / (1200 + 3000 * e ** 2)) ** 2) * (1 + 0.5 * reson(fk, 1500, 600))


def sax_spec(k, fk, e):
    s = e / (1 + (fk / (700 + 3500 * e ** 2)) ** 2) * fk / (fk + 200)
    return s * (0.4 + reson(fk, 550, 300) + 0.6 * reson(fk, 1500, 500) + 0.3 * reson(fk, 2800, 800))


def shaku_spec(k, fk, e):
    return e * {1: 1.0, 2: 0.4 * e, 3: 0.2 * e, 4: 0.08 * e}.get(k, 0.0 * e)


def chanter_spec(k, fk, e):
    return e / k ** 0.6 * (0.3 + reson(fk, 1300, 500) + 0.6 * reson(fk, 3000, 900)) * fk / (fk + 400)


def reed_spec(k, fk, e):
    return e * np.abs(np.sin(np.pi * k * 0.22)) / k / (1 + (fk / 3500) ** 2) * (1 + 0.6 * reson(fk, 1100, 500))


def wind(midi, dur, vel, spec, noise=0.01, band=(1500, 8000), burst=0.05, air=0.0, tail=0.3, kmax=48, **kw):
    notes, total = one(midi, dur, vel, tail)
    f, env, os = curve(notes, total, seed=int(midi), **kw)
    x = harmonic(f, env, spec, kmax=kmax, seed=int(midi))
    return x + (airy(x, air, 350, 1) if air else 0) + breath(env, os, noise, band, 1, burst=burst)


def plucked(midi, dur, vel, name, modes, t60, bright, pos, soft, shape, wet=0.85, buzz=0.0, twang=0.003, seconds=0.4):
    x = pluck(hz(midi), dur + min(t60, 2.5), vel, t60=t60, bright=bright, pos=pos, soft=soft, buzz=buzz, seed=int(midi),
              mute_at=dur + min(t60, 2.5) * 0.9, shape=shape, twang=twang)
    return body(x, name, modes, seconds=seconds, wet=wet)


def struck(midi, dur, vel, parts, ring, noise, band, noise_t, bend=0.0, bend_t=0.05):
    f = hz(midi)
    return modal(f, parts(f), max(dur, 0.1) + ring, vel, noise=noise, noise_band=band, noise_t=noise_t, bend=bend, bend_t=bend_t,
                 seed=int(midi))


def membrane(f, dur, vel, t60=1.2, bend=0.15, slap=0.3, seed=0):
    p = [(1, 1.0, t60), (1.59, 0.45, t60 * 0.6), (2.14, 0.3, t60 * 0.4), (2.3, 0.22, t60 * 0.35), (2.65, 0.15, t60 * 0.3),
         (2.92, 0.1, t60 * 0.25)]
    return modal(f, p, dur, vel, noise=slap, noise_band=(150, 1800), noise_t=0.025, bend=bend, bend_t=0.06, seed=seed)


def marimba_parts(f):
    T = 1.0 * (262 / f) ** 0.6
    return [(1, 1.0, T), (3.99, 0.22, T / 3.5), (9.9, 0.06, T / 9)]


def steelpan_parts(f):
    return [(1, 1.0, 1.4), (1.003, 0.4, 1.4), (2.0, 0.6, 0.9), (3.0, 0.3, 0.6), (4.02, 0.12, 0.35), (5.1, 0.05, 0.2)]


def kalimba_parts(f):
    return [(1, 1.0, 2.0), (5.93, 0.12, 0.18), (13.1, 0.04, 0.05)]


def bell_parts(f):
    return [(0.5, 0.5, 9), (0.502, 0.3, 9), (1.0, 0.6, 6), (1.19, 0.6, 5), (1.5, 0.35, 3.5), (2.0, 1.0, 4), (2.003, 0.4, 4),
            (2.51, 0.3, 2.2), (2.66, 0.25, 2), (3.01, 0.2, 1.6), (4.0, 0.15, 1.0), (5.33, 0.08, 0.6)]


def organ(midi, dur, vel):
    notes, total = one(midi, dur, vel, 0.4)
    out = 0
    for rank, mult, g in ((0, 1, 1.0), (1, 2, 0.5), (2, 3, 0.25), (3, 4, 0.2)):
        ln = [(s, d, m + 12 * np.log2(mult) + 0.03 * rank, v, sl) for s, d, m, v, sl in notes]
        f, env, os = curve(ln, total, attack=0.05, release=0.25, vib=(5, 0, 9), drift=0.004, seed=int(midi) * 4 + rank, artic=0)
        x = harmonic(f, env, lambda k, fk, e: e / k ** 1.6 / (1 + (fk / 6000) ** 2), kmax=16, seed=rank)
        out = out + (x + breath(env, os, 0.002, (2000, 7000), rank, burst=0.03, burst_t=0.03)) * g
    return out


def accordion(midi, dur, vel):
    notes, total = one(midi, dur, vel, 0.15)
    swell = 1 + 0.15 * np.sin(2 * np.pi * np.arange(int(total * SR)) / SR / 2.4)
    out = 0
    for det, g in ((0, 1.0), (0.13, 0.8), (-12, 0.4)):
        ln = [(s, d, m + det, v, sl) for s, d, m, v, sl in notes]
        f, env, _ = curve(ln, total, attack=0.02, release=0.05, vib=(5, 0, 9), drift=0.005, seed=int(abs(det) * 100))
        out = out + harmonic(f, env * swell[:len(env)], reed_spec, kmax=30) * g
    return out


def theremin(midi, dur, vel):
    notes, total = one(midi, dur, vel, 0.5)
    f, env, _ = curve(notes, total, vib=(6.2, 0.35, 0.1), attack=0.15, release=0.4, artic=0.0, drift=0.08)
    return harmonic(f, env, lambda k, fk, e: e * {1: 1, 2: 0.1, 3: 0.04}.get(k, 0 * e), kmax=3)


def didgeridoo(midi, dur, vel):
    notes, total = one(midi, dur, vel, 0.4)
    f, env, _ = curve(notes, total, attack=0.15, release=0.4, vib=(5, 0, 9), drift=0.02)
    idx = np.arange(0, len(f), 64)
    tc = idx / SR
    F2 = 900 + 900 * np.sin(np.pi * ((tc / 0.5) % 1)) ** 2
    return harmonic(f, env, lambda k, fk, e: e / k ** 0.75 * (0.03 + reson(fk, 250, 120) + 0.9 * reson(fk, F2, 160) + 0.3 * reson(fk, 2400, 400)),
                    kmax=80)


def sung(midi, dur, vel, syl='a', voices=1, breath=1.0, rd=1.0):
    part = 'soprano' if midi >= 67 else 'alto' if midi >= 58 else 'tenor' if midi >= 50 else 'bass'
    out = 0
    for p in range(voices):
        n = [(0.0, dur, float(midi) + (p - (voices - 1) / 2) * 0.1, vel, False)]
        y = voice(n, [syl], part, dur + 0.4, seed=int(midi) * 5 + p, rd=rd, breath=breath, attack=0.12, release=0.25,
                  vib=(5.0 + 0.4 * p, 0.15, 0.3), shift=1 + 0.02 * (p - (voices - 1) / 2))
        out = out + y[int(0.25 * SR):]
    return out


def shout(midi, dur, vel, syl):
    n = [(0.0, max(dur, 0.25), float(midi), vel, False)]
    y = voice(n, [syl], 'tenor' if midi < 60 else 'alto', max(dur, 0.25) + 0.2, rd=0.45, breath=0.6, jitter=0.012, shimmer=0.08,
              fall=-4, vib=(5, 0, 9), drift=0.06, glide=0.002, seed=int(midi))
    return y[int(0.25 * SR):]


BRASS_TRUMPET = dict(fc0=700, fcg=2600)
TABLE = {
    'trumpet': (70, lambda m, d, v: brass(m, d, v, 700, 2600)),
    'muted-trumpet': (70, lambda m, d, v: brass(m, d, v, 900, 2600, mute=True, scoop=(0.7, 0.07), vib=(5.0, 0.1, 0.4))),
    'horn': (60, lambda m, d, v: brass(m, d, v, 280, 700, hp=150, bell=(500, 400, 0.6), attack=0.06, vib=(4.8, 0.05, 0.6))),
    'trombone': (53, lambda m, d, v: brass(m, d, v, 380, 1500, hp=120, bell=(700, 600, 0.6))),
    'tuba': (36, lambda m, d, v: brass(m, d, v, 180, 650, hp=50, bell=(350, 300, 0.5), scoop=(0.2, 0.05))),
    'violin': (76, lambda m, d, v: bowed(m, d, v)),
    'viola': (64, lambda m, d, v: bowed(m, d, v, bright=2200)),
    'cello': (50, lambda m, d, v: bowed(m, d, v, CELLO_BODY, 'cello', 1600, vib=(5.2, 0.2, 0.2))),
    'contrabass': (38, lambda m, d, v: bowed(m, d, v, CELLO_BODY, 'cello', 1200, vib=(5.0, 0.15, 0.3))),
    'strings': (64, lambda m, d, v: bowed(m, d, v, players=3, attack=0.3, release=0.4)),
    'spiccato': (60, lambda m, d, v: spiccato(m, d, v)),
    'pizzicato': (67, lambda m, d, v: plucked(m, d, v, 'violin', VIOLIN_BODY, 0.45, 0.4, 0.3, 3000, 0.15, 0.9, twang=0.008)),
    'flute': (79, lambda m, d, v: wind(m, d, v, flute_spec, 0.04, (1500, 9000), 0.25, vib=(5.0, 0.06, 0.25), amp_vib=0.12, attack=0.04)),
    'clarinet': (62, lambda m, d, v: wind(m, d, v, clarinet_spec, 0.006, scoop=(0.4, 0.05), vib=(5.0, 0.04, 0.5))),
    'sax': (60, lambda m, d, v: wind(m, d, v, sax_spec, 0.012, (1000, 6000), air=0.08, scoop=(0.9, 0.08), vib=(5.0, 0.18, 0.45), glide=0.04)),
    'shakuhachi': (67, lambda m, d, v: wind(m, d, v, shaku_spec, 0.09, (800, 7000), 0.5, air=0.12, scoop=(1.2, 0.25),
                                            vib=(4.5, 0.1, 0.8), amp_vib=0.2, attack=0.08, release=0.3)),
    'bagpipe': (69, lambda m, d, v: wind(m, d, v, chanter_spec, 0.0, glide=0.004, artic=0.0, attack=0.01, release=0.05, drift=0.02)),
    'guitar': (55, lambda m, d, v: plucked(m, d, v, 'guitar', GUITAR_BODY, 1.6, 0.55, 0.18, 4000, 0.35)),
    'nylon': (55, lambda m, d, v: plucked(m, d, v, 'guitar', GUITAR_BODY, 1.8, 0.35, 0.2, 2500, 0.9)),
    'harp': (60, lambda m, d, v: plucked(m, d, v, 'harp', HARP_BODY, 3.5, 0.3, 0.45, 2500, 0.95, wet=0.75, seconds=0.5)),
    'banjo': (62, lambda m, d, v: plucked(m, d, v, 'banjo', BANJO_BODY, 0.9, 0.8, 0.12, 8000, 0.1, wet=0.9, twang=0.006, seconds=0.25)),
    'sitar': (61, lambda m, d, v: plucked(m, d, v, 'sitar', SITAR_BODY, 2.5, 0.85, 0.08, 9000, 0.0, wet=0.8, buzz=0.012)),
    'upright': (40, lambda m, d, v: plucked(m, d, v, 'cello', CELLO_BODY, 1.2, 0.25, 0.3, 900, 0.9, wet=0.7)),
    'marimba': (65, lambda m, d, v: struck(m, d, v, marimba_parts, 1.2, 0.15, (400, 2500), 0.004)),
    'steelpan': (72, lambda m, d, v: struck(m, d, v, steelpan_parts, 1.4, 0.12, (1500, 6000), 0.005, 0.004, 0.03)),
    'kalimba': (72, lambda m, d, v: struck(m, d, v, kalimba_parts, 1.8, 0.2, (2500, 9000), 0.003)),
    'bells': (64, lambda m, d, v: struck(m, d, v, bell_parts, 4.0, 0.15, (1000, 6000), 0.01)),
    'timpani': (38, lambda m, d, v: membrane(hz(m), max(d, 0.1) + 1.8, v, t60=1.8, bend=0.04, slap=0.25, seed=int(m))),
    'taiko': (36, lambda m, d, v: membrane(hz(m) * 0.9, max(d, 0.1) + 1.5, v, t60=1.0, bend=0.2, slap=0.5, seed=int(m))),
    'organ': (60, lambda m, d, v: organ(m, d, v)),
    'accordion': (67, lambda m, d, v: accordion(m, d, v)),
    'theremin': (69, lambda m, d, v: theremin(m, d, v)),
    'didgeridoo': (38, lambda m, d, v: didgeridoo(m, d, v)),
    'choir': (60, lambda m, d, v: sung(m, d, v, 'a', voices=3)),
    'choir-ooh': (60, lambda m, d, v: sung(m, d, v, 'u', voices=3)),
    'voice-aah': (60, lambda m, d, v: sung(m, d, v, 'a')),
    'hum': (50, lambda m, d, v: sung(m, d, v, 'M')),
    'hey': (57, lambda m, d, v: shout(m, d, v, 'hei')),
    'ha': (55, lambda m, d, v: shout(m, d, v, 'ha')),
}
SCALE = {}


def note(name, midi, dur, vel):
    """One note of phys:<name>, peak-normalised per instrument so themes mix it like the other instruments."""
    ref, fn = TABLE[name]
    if name not in SCALE:
        SCALE[name] = 0.3 / (np.abs(fn(ref, 1.0, 0.8)).max() + 1e-9)
    x = np.asarray(fn(midi, dur, vel), np.float64) * SCALE[name]
    n = len(x)
    fade = min(int(0.03 * SR), n // 4)
    x[n - fade:] *= np.linspace(1, 0, fade)
    return x.astype(np.float32)
