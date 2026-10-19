"""track.json for the visualizer (page/vz-engine.js): the same per-frame curves, hits, beats and sections its analyze.py makes, taken from what we know."""
import librosa
import numpy as np
import soundfile as sf

from .common import WORK, read_json, write_json

FPS = 30
KIND = {'kick': 'kick', 'tom': 'kick', 'impact': 'kick', 'snare': 'snare', 'clap': 'snare', 'rim': 'snare', 'hat': 'hats', 'openhat': 'hats', 'shaker': 'hats', 'ride': 'hats', 'tambourine': 'hats', 'crash': 'hats', 'swirl': 'snare'}


def norm(x, pct=98):
    hi = np.percentile(x, pct) or 1.0
    return np.clip(x / hi, 0, 1)


def smooth(x, k):
    w = np.hanning(k)
    return np.convolve(x, w / w.sum(), mode='same')


def frames(y, sr, nf):
    hop = sr // FPS
    return np.array([np.sqrt(np.mean(y[i * hop:(i + 1) * hop] ** 2)) if i * hop < len(y) else 0 for i in range(nf)])


def picked(env, nf, gap, delta):
    env = norm(env[:nf])
    out = np.zeros(nf)
    for p in librosa.util.peak_pick(env, pre_max=2, post_max=2, pre_avg=6, post_avg=2, delta=delta, wait=gap):
        if p < nf:
            out[p] = env[p]
    return out


def sections_of(parts, starts, lo=6.0, hi=10.0):
    """One visual section per lo-hi s, cut on sentence starts snapped to a beat: the reference changes shape every ~8-11 s."""
    out, first = [], True
    for p in parts:
        if p['kind'] == 'break':
            out.append({'start': round(p['t0'], 2), 'end': round(p['t1'], 2), 'energy': 0, 'name': 'Break'})
            continue
        bt = p.get('beatTimes')
        snap = (lambda t: min(bt, key=lambda b: abs(b - t))) if bt else (lambda t: t)
        cuts = [p['t0']]
        for t in sorted(starts):
            c = snap(t)
            if c - cuts[-1] >= lo and p['t1'] - c >= lo:
                cuts.append(c)
        pieces = []
        for a, z in zip(cuts, cuts[1:] + [p['t1']]):
            k = int(np.ceil((z - a) / hi))
            pieces += [snap(a + (z - a) * j / k) if j else a for j in range(k)]
        for a, z in zip(pieces, pieces[1:] + [p['t1']]):
            out.append({'start': round(a, 2), 'end': round(z, 2), 'energy': round(p['level'] / 4, 2), 'name': 'Intro' if first else 'Drop' if p['level'] >= 4 else 'Groove'})
            first = False
    return out


def write_track(path, bed, sr, slug, parts, bpm, events=None):
    y = bed.mean(axis=0) if bed.ndim > 1 else bed
    nf = int(len(y) / sr * FPS)
    hop = sr // FPS
    S = np.abs(librosa.stft(y, n_fft=4096, hop_length=hop))[:, :nf]
    f = librosa.fft_frequencies(sr=sr, n_fft=4096)
    band = lambda lo, hi: np.pad(S[(f >= lo) & (f < hi)].mean(axis=0), (0, max(0, nf - S.shape[1])))[:nf]
    voice, vsr = sf.read(WORK / slug / 'voice.wav', always_2d=True)
    curves = {'bass': norm(smooth(band(30, 160), 5)), 'vocal': norm(smooth(frames(voice.mean(axis=1), vsr, nf), 7)), 'keys': norm(smooth(band(160, 1200), 5))}
    if events:
        hits = {k: np.zeros(nf) for k in ('kick', 'snare', 'hats')}
        for inst, t, vel, *_ in events:
            fr = int(t * FPS)
            if inst in KIND and fr < nf:
                hits[KIND[inst]][fr] = max(hits[KIND[inst]][fr], vel)
        hits = {k: v / (v.max() or 1) for k, v in hits.items()}
    else:
        db = librosa.amplitude_to_db(S)
        hits = {'kick': picked(librosa.onset.onset_strength(S=db[f < 150], sr=sr, hop_length=hop), nf, 6, 0.25),
                'snare': picked(librosa.onset.onset_strength(S=db[(f >= 180) & (f < 4000)], sr=sr, hop_length=hop), nf, 6, 0.25),
                'hats': picked(librosa.onset.onset_strength(S=db[f >= 6000], sr=sr, hop_length=hop), nf, 3, 0.2)}
    beats = sorted({int(t * FPS) for p in parts for t in p.get('beatTimes', [])})
    speech = read_json(WORK / slug / 'speech.json', {})
    sections = sections_of(parts, [x['t'] for x in speech.get('sentences', [])])
    if sections:
        sections[-1]['end'] = round(nf / FPS, 2)
    r = lambda a: [round(float(v), 3) for v in a]
    write_json(path, {
        'fps': FPS, 'frames': nf, 'duration': round(nf / FPS, 3), 'source': 'soundtrack', 'tempo': round(float(bpm), 1), 'beats': beats,
        'curves': {k: r(v) for k, v in curves.items()}, 'energy': r(norm(smooth(frames(y, sr, nf), 15))),
        'hits': {k: r(v) for k, v in hits.items()}, 'hitFrames': {k: [int(i) for i in np.flatnonzero(v > 0.05)] for k, v in hits.items()},
        'notes': [[round(e[1], 3), e[3], e[4], e[5], round(e[2], 2)] for e in sorted(events or [], key=lambda e: e[1]) if e[0] == 'note'],
        'drums': [[round(t, 3), KIND[inst], round(vel, 2)] for inst, t, vel, *_ in sorted(events or [], key=lambda e: e[1]) if inst in KIND],
        'parts': [{'t0': round(p['t0'], 3), 't1': round(p['t1'], 3), 'kind': p['kind'], 'level': p.get('level', 0)} for p in parts],
        'vocalMarks': [int(s['t'] * FPS) for s in speech.get('sentences', []) if s['t'] * FPS < nf], 'sections': sections,
    })
