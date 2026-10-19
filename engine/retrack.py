"""A real song (Suno, Runway, a library track) re-cut on its own bars so its changes land on the same spoken cues."""
import tempfile, time
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf

from . import synth as sy
from .common import run, slugify, step
from .mix import write_try
from .plan import fit
from .reference import key_of

SR = sy.SR


def bars_of(song):
    y = librosa.to_mono(song)
    y22 = librosa.resample(y, orig_sr=SR, target_sr=22050)
    tempo, frames = librosa.beat.beat_track(y=y22, sr=22050)
    beats = librosa.frames_to_time(frames, sr=22050)
    low = librosa.onset.onset_strength(y=librosa.effects.percussive(y22), sr=22050, fmax=200)
    lt = librosa.times_like(low, sr=22050)
    at = lambda t: low[min(len(low) - 1, np.searchsorted(lt, t))]
    phase = max(range(4), key=lambda p: sum(at(b) for b in beats[p::4]))
    beats = beats[phase:]
    bars = beats[::4]
    rms = np.array([np.sqrt(np.mean(y[int(a * SR):int(b * SR)] ** 2)) for a, b in zip(bars[:-1], bars[1:])])
    db = 20 * np.log10(np.maximum(rms, 1e-6))
    cuts = np.quantile(db, [0.2, 0.45, 0.75])
    level = 1 + np.searchsorted(cuts, db)
    onset = librosa.onset.onset_strength(y=y22, sr=22050)
    ot = librosa.times_like(onset, sr=22050)
    punch = np.array([onset[min(len(onset) - 1, np.searchsorted(ot, b))] for b in bars[:-1]])
    punch = np.clip(punch / (np.quantile(punch, 0.9) or 1), 0, 1)
    return float(np.atleast_1d(tempo)[0]), beats, bars, level, punch, y22


def choose(bars, level, want, n_bars, start, punch, weight):
    """Start bar for a part: right level, on a 4-bar phrase, the song's own order when it can; after a stop, a bar that opens on a hit."""
    best = None
    for i in range(0, max(1, len(level) - 1)):
        seg = level[i:i + n_bars]
        if not len(seg):
            continue
        cost = abs(float(np.mean(seg)) - want) + (0 if i % 4 == 0 else 0.6) + (0 if i == start else 0.25) + (0.8 if len(seg) < n_bars else 0) + weight * (1 - punch[i])
        if best is None or cost < best[0]:
            best = (cost, i)
    return best[1]


def stretch(x, seconds):
    with tempfile.TemporaryDirectory() as d:
        a, b = Path(d) / 'a.wav', Path(d) / 'b.wav'
        sf.write(a, x.T, SR)
        run('rubberband', '-3', '-q', '-D', f'{seconds:.6f}', a, b)
        y, _ = sf.read(b, always_2d=True)
    return y.T.astype(np.float32)


def retrack(slug, song_file, speech, out):
    name = Path(song_file).stem
    tid = f'song-{slugify(name)}'[:40]
    label = f'Re-cut {name} for {speech["title"][:24]}'
    step(label, 'run')
    started = time.time()
    song, sr = librosa.load(song_file, sr=SR, mono=False)
    song = np.atleast_2d(song) if song.ndim > 1 else np.stack([song, song])
    tempo, beats, bars, level, punch, y22 = bars_of(song)
    print(f'Song: {tempo:.1f} BPM, {len(bars)} bars', flush=True)
    grid = {**fit(out, (tempo * 0.97, tempo * 1.03)), 'speechEnd': out['speechEnd']}
    n = int((speech['seconds'] + 1) * SR)
    bed = np.zeros((2, n), np.float32)
    spans, cursor = [], 0
    beat_len = 60 / tempo
    for k, p in enumerate(grid['parts']):
        if p['kind'] != 'play':
            continue
        n_bars = int(np.ceil(p['beats'] / 4))
        after_break = k and grid['parts'][k - 1]['kind'] == 'break'
        i = choose(bars, level, p['level'], n_bars, cursor, punch, 0.8 if after_break else 0.3)
        a = bars[i]
        end_beat = np.searchsorted(beats, a - 1e-3) + p['beats']
        z = beats[end_beat] if end_beat < len(beats) else a + p['beats'] * beat_len
        if z > song.shape[1] / SR:
            i = choose(bars, level, p['level'], n_bars, 0, punch, 0.8 if after_break else 0.3)
            a = bars[i]; z = a + p['beats'] * beat_len
        x = song[:, int(a * SR):int(z * SR)]
        x = stretch(x, p['t1'] - p['t0'])
        tail = int(0.012 * SR)
        x[:, :tail] *= np.linspace(0, 1, tail)
        x[:, -tail:] *= np.linspace(1, 0, tail)
        s = int(p['t0'] * SR)
        bed[:, s:s + x.shape[1]] += x[:, :n - s]
        spans.append([p['t0'], p['t1']])
        cursor = i + n_bars
        p['source'] = round(float(a), 2)
    end = grid['speechEnd']
    last_src = grid['parts'][-1].get('source')
    if last_src is not None:
        a = last_src + (grid['parts'][-1]['t1'] - grid['parts'][-1]['t0']) * grid['parts'][-1]['bpm'] / tempo
        x = song[:, int(a * SR):int((a + 3) * SR)]
        s = int(end * SR)
        x = x[:, :max(0, n - s)] * np.linspace(1, 0, min(x.shape[1], max(0, n - s)))
        bed[:, s:s + x.shape[1]] += x
    note, mode, _ = key_of(y22)
    bed = bed[:, :int((speech['seconds'] + 0.05) * SR)]
    bed = np.stack([sy.peak_eq(c, 2600, -3, 0.8) for c in bed]).astype(np.float32)
    bed *= 10 ** (-1.5 / 20) / (np.abs(bed).max() or 1)
    meta = {'kind': 'song', 'name': name[:40], 'about': f'Your track, re-cut on its own bars: {tempo:.0f} BPM, nudged at most {grid["maxDriftPct"]}% per part.', 'key': f'{note} {mode}', 'under': 10,
            'layers': {'song': spans}, 'song': str(song_file), 'composeSeconds': round(time.time() - started, 1)}
    t = write_try(slug, tid, bed, meta, grid, out)
    step(label, 'ok', f"{t['bpm']} BPM, cues within {t['score']['cueErrorMs']} ms, {t['composeSeconds']} s")
    print(f"{name}: cue error {t['score']['cueErrorMs']} ms", flush=True)
    return t
