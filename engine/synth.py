"""Instruments and effects in plain numpy. Every function returns float32 samples at SR; no state, so notes can be cached."""
from functools import lru_cache
from pathlib import Path

import numpy as np
from scipy.signal import butter, fftconvolve, sosfilt

SR = 48000
NYQ = SR / 2
SOUNDFONT = Path(__file__).resolve().parent.parent / 'library' / 'soundfonts' / 'GeneralUser-GS.sf2'
GM = {'grand': 0, 'celeste': 8, 'glock': 9, 'vibes': 11, 'marimba': 12, 'organ': 16, 'accordion': 21, 'nylon': 24, 'steel': 25,
      'jazzguitar': 26, 'upright': 32, 'fingerbass': 33, 'violin': 40, 'viola': 41, 'cello': 42, 'contrabass': 43, 'pizz': 45,
      'harp': 46, 'timpani': 47, 'strings': 48, 'slowstrings': 49, 'choir': 52, 'horns': 60, 'oboe': 68, 'bassoon': 70,
      'clarinet': 71, 'flute': 73, 'banjo': 105, 'tremolo': 44, 'trumpet': 56, 'mutedtrumpet': 59, 'altosax': 65,
      'tenorsax': 66, 'englishhorn': 69, 'piccolo': 72}
KITS = {'kit': 0, 'room': 8, 'jazz': 32, 'brush': 40, 'orch': 48}
DRUMS = {'kick': 36, 'rim': 37, 'snare': 38, 'clap': 39, 'swirl': 40, 'hat': 42, 'pedalhat': 44, 'tom': 45, 'openhat': 46,
         'crash': 49, 'ride': 51, 'tambourine': 54, 'shaker': 70, 'triangle': 81}
_fluid = []


def hz(midi):
    return 440.0 * 2 ** ((midi - 69) / 12)


def tt(dur):
    return np.arange(int(dur * SR)) / SR


def fade(x, a=0.003, r=0.02):
    n = len(x)
    a, r = min(int(a * SR), n // 2), min(int(r * SR), n // 2)
    if a:
        x[:a] *= np.linspace(0, 1, a)
    if r:
        x[n - r:] *= np.linspace(1, 0, r)
    return x


def harmonics(f, t, top, rolloff, decay=0.0, per=0.0, detune=0.0, rng=None):
    out = np.zeros_like(t)
    for k in range(1, 64):
        fk = f * k * (1 + detune)
        if fk > min(top, NYQ * 0.9):
            break
        amp = 1 / k ** rolloff
        env = np.exp(-t * (decay + per * k)) if decay or per else 1
        out += amp * env * np.sin(2 * np.pi * fk * t + (rng.uniform(0, 6.28) if rng is not None else 0))
    return out


def filt(x, kind, cut, order=2):
    return sosfilt(butter(order, np.clip(np.array(cut) / NYQ, 1e-4, 0.999), btype=kind, output='sos'), x)


def sampled(bank, program, midi, dur, vel, tail):
    """A recorded instrument from the GM soundfont, its own reverb and chorus off so the engine's room is the only space."""
    if not _fluid:
        import fluidsynth
        fs = fluidsynth.Synth(samplerate=float(SR))
        fs.setting('synth.reverb.active', 0)
        fs.setting('synth.chorus.active', 0)
        _fluid.extend([fs, fs.sfload(str(SOUNDFONT))])
    fs, sfid = _fluid
    ch = 9 if bank == 128 else 0
    fs.program_select(ch, sfid, bank, program)
    fs.noteon(ch, midi, int(np.clip(round(20 + vel * 90), 1, 127)))
    held = fs.get_samples(max(1, int(dur * SR)))
    fs.noteoff(ch, midi)
    x = np.concatenate([held, fs.get_samples(int(tail * SR))]).reshape(-1, 2).mean(axis=1).astype(np.float32) / 32768
    fs.cc(ch, 120, 0)
    fs.get_samples(512)
    return fade(x * 8, 0.0005, 0.05)


def lead_in(x):
    """Seconds a recorded note takes to speak (10% of its peak); placed that much early so it sounds on the beat."""
    a = np.abs(x)
    return min(0.06, int(np.argmax(a > a.max() * 0.1)) / SR)


@lru_cache(maxsize=64)
def slow(inst):
    """True for bowed, blown and pad sounds that take over 0.15 s to reach full level."""
    return int(np.argmax(np.abs(note(inst, 60, 1.0, 0.8)))) > 0.15 * SR


def is_hit(inst):
    return inst.split(':')[0] in KITS


@lru_cache(maxsize=4096)
def note(inst, midi, dur, vel):
    """One note. dur is rounded by the caller so repeats hit the cache."""
    if inst.startswith('sf:'):
        return sampled(0, GM[inst[3:]], midi, dur, vel, 1.6)
    if inst.startswith('phys:'):
        from .phys.inst import note as phys_note
        return phys_note(inst[5:], midi, dur, vel)
    f, rng = hz(midi), np.random.default_rng(int(midi * 1000 + dur * 100))
    if inst == 'pulse':
        t = tt(max(dur, 0.06) + 0.08)
        x = harmonics(f, t, 1800, 1.0, 9, 1.6) + 0.6 * harmonics(f, t, 1600, 1.0, 9, 1.6, detune=0.004)
        x *= np.exp(-t / 0.16) * np.minimum(1, t / 0.004)
        return fade(x * 0.25 * vel, 0.002, 0.03).astype(np.float32)
    if inst == 'pluck':
        t = tt(dur + 0.6)
        x = harmonics(f, t, 6000, 1.0, 3.5, 2.2, rng=rng) * np.minimum(1, t / 0.003)
        return fade(x * 0.3 * vel, 0.002, 0.08).astype(np.float32)
    if inst == 'pad':
        t = tt(dur + 0.9)
        x = sum(harmonics(f, t, 2600, 1.5, detune=d, rng=rng) for d in (-0.0045, 0, 0.005))
        a = np.minimum(1, t / 0.45) * np.where(t > dur, np.exp(-(t - dur) / 0.3), 1)
        x *= a * (1 + 0.08 * np.sin(2 * np.pi * 0.21 * t))
        return fade(x * 0.06 * vel, 0.01, 0.1).astype(np.float32)
    if inst == 'epiano':
        t = tt(dur + 1.2)
        index = 1.6 * vel * np.exp(-t / 0.35) + 0.25
        x = np.sin(2 * np.pi * f * t + index * np.sin(2 * np.pi * f * t))
        x += 0.18 * vel * np.sin(2 * np.pi * f * 14 * t) * np.exp(-t / 0.05) if f * 14 < NYQ * 0.9 else 0
        x *= np.exp(-t / 1.4) * np.where(t > dur, np.exp(-(t - dur) / 0.18), 1) * (1 + 0.12 * np.sin(2 * np.pi * 4.2 * t))
        return fade(x * 0.22 * vel, 0.002, 0.1).astype(np.float32)
    if inst == 'piano':
        t = tt(dur + 1.5)
        x = np.zeros_like(t)
        for k in range(1, 14):
            fk = f * k * np.sqrt(1 + 0.0004 * k * k)
            if fk > 7000:
                break
            x += (1 / k ** (1.6 - 0.5 * vel)) * np.exp(-t * (0.9 + 0.55 * k) * (f / 260) ** 0.4) * np.sin(2 * np.pi * fk * t)
        x *= np.where(t > dur, np.exp(-(t - dur) / 0.12), 1) * np.minimum(1, t / 0.002)
        x[:240] += filt(rng.standard_normal(240), 'low', 1800) * 0.05 * np.linspace(1, 0, 240)
        return fade(x * 0.2 * vel, 0.001, 0.08).astype(np.float32)
    if inst == 'bell':
        t = tt(dur + 1.5)
        x = np.sin(2 * np.pi * f * t + 1.2 * np.exp(-t / 0.6) * np.sin(2 * np.pi * f * 3.5 * t)) * np.exp(-t / 0.9)
        return fade(x * 0.12 * vel, 0.002, 0.1).astype(np.float32)
    if inst == 'sub':
        t = tt(dur + 0.08)
        x = np.sin(2 * np.pi * f * t) + 0.22 * np.sin(4 * np.pi * f * t)
        x = np.tanh(1.4 * x) * np.minimum(1, t / 0.008) * np.where(t > dur, np.exp(-(t - dur) / 0.03), 1)
        return fade(x * 0.32 * vel, 0.004, 0.03).astype(np.float32)
    if inst == 'bass':
        t = tt(dur + 0.1)
        x = harmonics(f, t, 1400, 1.1, 2.0, 1.8) * np.minimum(1, t / 0.004) * np.where(t > dur, np.exp(-(t - dur) / 0.04), 1)
        x += 0.5 * np.sin(2 * np.pi * f * t) * np.exp(-t / 0.8)
        return fade(np.tanh(x) * 0.3 * vel, 0.002, 0.03).astype(np.float32)
    raise ValueError(f'no instrument {inst}')


@lru_cache(maxsize=256)
def hit(kind, vel):
    if is_hit(kind):
        kit, drum = kind.split(':')
        return sampled(128, KITS[kit], DRUMS[drum], 0.05, vel, 2.5 if drum in ('crash', 'ride') else 0.8)
    rng = np.random.default_rng(7)
    if kind == 'kick':
        t = tt(0.45)
        f = 44 + 70 * np.exp(-t / 0.04)
        x = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.22)
        x[:96] += filt(rng.standard_normal(96), 'low', 4000) * 0.3
        return fade(np.tanh(1.6 * x) * 0.55 * vel, 0.0005, 0.03).astype(np.float32)
    if kind == 'snare':
        t = tt(0.3)
        x = filt(rng.standard_normal(len(t)), 'band', (1500, 7000)) * np.exp(-t / 0.09) * 0.6 + np.sin(2 * np.pi * 190 * t) * np.exp(-t / 0.06) * 0.5
        return fade(x * 0.4 * vel, 0.0005, 0.02).astype(np.float32)
    if kind == 'clap':
        t = tt(0.35)
        env = sum(np.where(t >= o, np.exp(-(t - o) / 0.008), 0) for o in (0, 0.011, 0.022)) + np.where(t >= 0.03, np.exp(-(t - 0.03) / 0.12), 0) * 0.5
        return fade(filt(rng.standard_normal(len(t)), 'band', (900, 3500)) * env * 0.35 * vel, 0.0005, 0.02).astype(np.float32)
    if kind in ('hat', 'openhat'):
        t = tt(0.06 if kind == 'hat' else 0.35)
        x = filt(rng.standard_normal(len(t)), 'high', 7500) * np.exp(-t / (0.022 if kind == 'hat' else 0.14))
        return fade(x * 0.22 * vel, 0.0005, 0.01).astype(np.float32)
    if kind == 'shaker':
        t = tt(0.09)
        x = filt(rng.standard_normal(len(t)), 'band', (5000, 11000)) * np.minimum(1, t / 0.012) * np.exp(-t / 0.035)
        return fade(x * 0.16 * vel, 0.001, 0.01).astype(np.float32)
    if kind == 'rim':
        t = tt(0.08)
        x = (np.sin(2 * np.pi * 1700 * t) * 0.6 + filt(rng.standard_normal(len(t)), 'band', (2000, 6000)) * 0.4) * np.exp(-t / 0.018)
        return fade(x * 0.25 * vel, 0.0003, 0.01).astype(np.float32)
    if kind == 'tom':
        t = tt(0.6)
        f = 70 + 40 * np.exp(-t / 0.06)
        return fade(np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.3) * 0.5 * vel, 0.001, 0.05).astype(np.float32)
    if kind == 'impact':
        t = tt(2.2)
        f = 32 + 60 * np.exp(-t / 0.12)
        x = np.tanh(1.5 * np.sin(2 * np.pi * np.cumsum(f) / SR)) * np.exp(-t / 0.75)
        x += filt(rng.standard_normal(len(t)), 'low', 2500) * np.exp(-t / 0.25) * 0.35
        return fade(x * 0.5 * vel, 0.0008, 0.3).astype(np.float32)
    raise ValueError(f'no hit {kind}')


def vinyl(n):
    rng = np.random.default_rng(11)
    x = filt(rng.standard_normal(n), 'band', (800, 6000)) * 0.004
    clicks = rng.random(n) < 4 / SR
    x[clicks] += rng.uniform(-0.25, 0.25, clicks.sum())
    return filt(x, 'low', 7000).astype(np.float32)


@lru_cache(maxsize=4)
def room(seconds=2.2, seed=5):
    rng = np.random.default_rng(seed)
    t = tt(seconds)
    ir = rng.standard_normal((2, len(t))) * np.exp(-6.9 * t / seconds)
    ir = np.stack([filt(c, 'low', 5500) for c in ir])
    ir[:, :int(0.018 * SR)] = 0
    return (ir / np.sqrt((ir ** 2).sum(axis=1, keepdims=True))).astype(np.float32)


def reverb(x, seconds=2.2):
    ir = room(seconds)
    return np.stack([fftconvolve(x, ir[0])[:len(x)], fftconvolve(x, ir[1])[:len(x)]]).astype(np.float32)


def delay(x, step, feedback=0.4, taps=5):
    out = np.zeros((2, len(x)), np.float32)
    for k in range(1, taps + 1):
        d = int(step * k * SR)
        if d >= len(x):
            break
        out[k % 2, d:] += x[:len(x) - d] * feedback ** k
    return out


def peak_eq(x, f0, db, q=0.9):
    a, w = 10 ** (db / 40), 2 * np.pi * f0 / SR
    al = np.sin(w) / (2 * q)
    b = np.array([1 + al * a, -2 * np.cos(w), 1 - al * a]) / (1 + al / a)
    aa = np.array([1, -2 * np.cos(w) / (1 + al / a), (1 - al / a) / (1 + al / a)])
    return sosfilt(np.concatenate([b, aa])[None, :], x)
