"""Measures the music in someone else's video against what is said in it: the numbers our own tracks are held to."""
import shutil
from pathlib import Path

import librosa
import numpy as np

from .common import DEMUCS, NOTES, RESEARCH, WORK, loudness, opus, run, write_json
from .speech import from_video

MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
BANDS = [(0, 150), (150, 400), (400, 1000), (1000, 2500), (2500, 6000), (6000, 12000)]
SR = 22050


def db(x):
    return 20 * np.log10(np.maximum(x, 1e-7))


def rms(y, hop):
    return np.array([np.sqrt(np.mean(y[i:i + hop] ** 2)) for i in range(0, len(y) - hop, hop)])


def split(audio, out):
    """Voice, bass, drums and the rest as four files (Demucs). About 90 s per 100 s of sound, once."""
    if not (out / 'vocals.wav').exists():
        tmp = out.parent / 'demucs'
        run(DEMUCS, '-n', 'htdemucs', '-o', tmp, audio)
        out.mkdir(parents=True, exist_ok=True)
        for f in (tmp / 'htdemucs' / Path(audio).stem).glob('*.wav'):
            shutil.move(f, out / f.name)
        shutil.rmtree(tmp)
    return out


def key_of(y):
    chroma = librosa.feature.chroma_cqt(y=y, sr=SR).mean(axis=1)
    fit, note, mode = max((np.corrcoef(np.roll(p, i), chroma)[0, 1], NOTES[i], m) for i in range(12) for p, m in ((MAJOR, 'major'), (MINOR, 'minor')))
    return note, mode, round(float(fit), 2)


def chords(y, bar):
    chroma = librosa.feature.chroma_cqt(y=librosa.effects.harmonic(y, margin=3), sr=SR, hop_length=512)
    t = librosa.times_like(chroma[0], sr=SR, hop_length=512)
    shapes = {}
    for root in range(12):
        for name, steps in (('', (0, 4, 7)), ('m', (0, 3, 7))):
            v = np.zeros(12)
            v[[(root + s) % 12 for s in steps]] = 1
            shapes[NOTES[root] + name] = v / np.linalg.norm(v)
    out = []
    for b in range(int(len(y) / SR / bar)):
        c = chroma[:, (t >= b * bar) & (t < (b + 1) * bar)].mean(axis=1)
        out.append(max(shapes, key=lambda k: float(shapes[k] @ (c / (np.linalg.norm(c) + 1e-9)))))
    return out


def measure(video, slug, title=None):
    work = WORK / slug
    work.mkdir(parents=True, exist_ok=True)
    audio = work / 'audio.wav'
    if not audio.exists():
        run('ffmpeg', '-y', '-v', 'error', '-i', video, '-vn', '-ac', '2', '-ar', '44100', audio)
    stems = split(audio, work / 'stems')
    music_file = work / 'music.wav'
    run('ffmpeg', '-y', '-v', 'error', '-i', stems / 'bass.wav', '-i', stems / 'drums.wav', '-i', stems / 'other.wav', '-filter_complex', 'amix=inputs=3:normalize=0', music_file)
    opus(music_file, work / 'music.opus')
    speech = from_video(video, slug, title, voice=stems / 'vocals.wav')

    part = {k: librosa.load(stems / f'{k}.wav', sr=SR)[0] for k in ('bass', 'drums', 'other')}
    music = sum(part.values())
    voice_lufs, music_lufs = loudness(stems / 'vocals.wav')[0], loudness(music_file)[0]
    energy = {k: float(np.mean(v ** 2)) for k, v in part.items()}

    _, beats = librosa.beat.beat_track(y=music, sr=SR)
    beat = float(np.median(np.diff(librosa.frames_to_time(beats, sr=SR))))
    note, mode, fit = key_of(part['other'] + part['bass'])

    level = db(rms(music, int(SR * 0.25)))
    mid = float(np.median(level))
    quiet, breaks, start = level < mid - 12, [], None
    for i, q in enumerate(list(quiet) + [False]):
        if q and start is None:
            start = i
        if not q and start is not None:
            if (i - start) * 0.25 >= 0.75 and start * 0.25 > 1 and i * 0.25 < len(level) * 0.25 - 1.5:
                breaks.append({'t': start * 0.25, 'd': (i - start) * 0.25})
            start = None
    starts = np.array([s['t'] for s in speech['sentences']])
    for b in breaks:
        back = b['t'] + b['d']
        k = int(np.argmin(np.abs(starts - back)))
        i = int(back / 0.25)
        b.update(back=round(back, 2), line=speech['sentences'][k]['text'][:80], off=round(float(back - starts[k]), 2), lift=round(float(np.mean(level[i + 1:i + 40]) - np.mean(level[max(0, int(b['t'] / 0.25) - 40):int(b['t'] / 0.25)])), 1))

    spec = np.abs(librosa.stft(music, n_fft=2048, hop_length=512)) ** 2
    freqs = librosa.fft_frequencies(sr=SR, n_fft=2048)
    drums = db(rms(part['drums'], int(SR * 0.25)))
    progression = chords(part['other'] + part['bass'], beat * 4)

    data = {
        'slug': slug, 'title': speech['title'], 'seconds': speech['seconds'],
        'bpm': round(60 / beat, 1), 'key': f'{note} {mode}', 'keyFit': fit,
        'under': round(voice_lufs - music_lufs, 1), 'voiceLufs': voice_lufs, 'musicLufs': music_lufs,
        'share': {k: round(v / sum(energy.values()), 2) for k, v in energy.items()},
        'bands': {f'{a}-{b}': round(float(spec[(freqs >= a) & (freqs < b)].sum() / spec.sum()), 3) for a, b in BANDS},
        'level': [round(float(x - mid), 1) for x in level],
        'drums': [round(float(x), 1) for x in drums],
        'breaks': breaks, 'chords': progression,
        'notesPerSecond': round(len(librosa.onset.onset_detect(y=music, sr=SR)) / (len(music) / SR), 2),
    }
    write_json(RESEARCH / slug / 'ref.json', data)
    from .mix import write_levels
    write_levels(slug, music_file)
    return data
