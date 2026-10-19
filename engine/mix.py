"""Master the bed, measure it against the speech, and write the video with it mixed in."""
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf

from . import synth as sy
from .common import TRACK_CODE, WORK, append_jsonl, LIBRARY, code_stamp, loudness, opus, read_json, run, seconds, video_seconds, write_json

SR = sy.SR


def master(stems, theme, length, loop=False):
    bed = sum(stems.values())[:, :int(round(length * SR)) if loop else int((length + 0.05) * SR)]
    size = bed.shape[1]
    if loop:
        bed = np.concatenate([bed, bed, bed], axis=1)
    bed = np.stack([sy.filt(c, 'high', 35) for c in bed])
    if theme.get('lp'):
        bed = np.stack([sy.filt(c, 'low', theme['lp']) for c in bed])
    if theme.get('pocket'):
        bed = np.stack([sy.peak_eq(c, 2600, theme['pocket'], 0.8) for c in bed])
    if loop:
        bed = bed[:, size:2 * size]
    peak = np.abs(bed).max() or 1
    bed = np.tanh(bed / peak * 1.2) / np.tanh(1.2) * 10 ** (-1.5 / 20)
    if not loop:
        r = int(0.4 * SR)
        bed[:, -r:] *= np.linspace(1, 0, r)
    return bed.astype(np.float32)


def dbfs(bed):
    mono = bed.mean(axis=0) if bed.ndim > 1 else bed
    hop = int(0.25 * SR)
    return 20 * np.log10(np.maximum([np.sqrt(np.mean(mono[i:i + hop] ** 2)) for i in range(0, len(mono) - hop, hop)], 1e-6))


def curve(bed):
    db = dbfs(bed)
    return [round(float(x - np.median(db)), 1) for x in db]


def write_levels(slug, music=None):
    """Loudness per 0.25 s in dBFS: the voice, and the reference's own music when there is one. The page draws music against voice."""
    voice, _ = sf.read(WORK / slug / 'voice.wav', always_2d=True)
    data = {'voice': [round(float(x), 1) for x in dbfs(voice.T)]}
    if music:
        m, _ = sf.read(music, always_2d=True)
        data['musicMedian'] = round(float(np.median(dbfs(m.T))), 1)
    write_json(WORK / slug / 'levels.json', data)
    return data


def reentries(y, sr, times):
    """Per re-entry: attackMs = rise from 20 dB under the part's level to 3 dB under it; jumpDb = 100 ms after the cue vs 150 ms before."""
    hop = int(0.005 * sr)
    db = 20 * np.log10(np.maximum(np.sqrt(np.convolve(y ** 2, np.ones(2 * hop) / (2 * hop), 'same'))[::hop], 1e-6))
    at = lambda t: int(round(t * sr / hop))
    rows = []
    for t in times:
        level = float(np.median(db[at(t + 0.1):at(t + 1.5)]))
        win = db[at(t - 0.4):at(t + 1)]
        top = np.flatnonzero(win >= level - 3)
        if not len(top):
            continue
        low = np.flatnonzero(win[:top[0]] < level - 20)
        start = low[-1] if len(low) else 0
        rows.append({'t': round(t, 2), 'attackMs': round((top[0] - start) * 5.0), 'jumpDb': round(float(db[at(t):at(t + 0.1)].max() - db[at(t - 0.15):at(t - 0.02)].mean()), 1),
                     'preDb': round(float(db[at(t - 0.3):at(t - 0.02)].mean() - level), 1)})
    return rows


def score(wav, grid, out):
    """Measured on the rendered file, not assumed from the plan."""
    y, sr = librosa.load(wav, sr=22050)
    env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=128)
    times = librosa.times_like(env, sr=sr, hop_length=128)
    errs = []
    for a in out['anchors']:
        if a['kind'] != 'change':
            continue
        win = (times > a['t'] - 0.15) & (times < a['t'] + 0.15)
        if win.any():
            errs.append(abs(float(times[win][np.argmax(env[win])]) - a['t']) * 1000)
    spec = np.abs(librosa.stft(y, n_fft=2048, hop_length=512)) ** 2
    freqs = librosa.fft_frequencies(sr=sr, n_fft=2048)
    lv = curve(np.stack([y, y]))
    playing = [i for i in range(len(lv)) if any(p['kind'] == 'play' and p['t0'] <= i * 0.25 < p['t1'] for p in grid['parts'])]
    quiet = [i for i in playing if lv[i] < -30]
    onsets = librosa.onset.onset_detect(y=y, sr=sr, units='time')
    chopped, into, unchecked = 0, [], []
    for p in grid['parts']:
        if p['kind'] == 'play' and any(q['kind'] == 'break' and abs(q['t0'] - p['t1']) < 1e-3 for q in grid['parts']):
            last = p['t1'] - 2 * (p['t1'] - p['t0']) / p['beats']
            chopped += int(((onsets > last + 0.08) & (onsets < p['t1'])).sum())
            rms = lambda a, z: 10 * np.log10(np.mean(y[int(a * sr):int(z * sr)] ** 2) + 1e-12)
            if p['t1'] - p['t0'] >= 2.5:
                into.append(round(float(rms(p['t1'] - 0.3, p['t1'] - 0.15) - rms(max(p['t0'], p['t1'] - 6), p['t1'] - 2)), 1))
            else:
                unchecked.append({'key': 'stop', 'why': f"only {p['t1'] - p['t0']:.1f} s of music before the stop at {p['t1']:.1f} s"})
    seam = loop_seam(y, sr, grid) if grid.get('loop') else {}
    back = reentries(y, sr, [p['t0'] for p in grid['parts'] if p['kind'] == 'play' and any(q['kind'] == 'break' and abs(q['t1'] - p['t0']) < 1e-3 for q in grid['parts'])])
    out = {
        'reentries': back, 'hitsAfterLastHit': chopped, 'stopDb': max(into, default=None), 'attackMs': max((r['attackMs'] for r in back), default=None), 'jumpDb': min((r['jumpDb'] for r in back), default=None),
        'cueErrorMs': round(max(errs), 1) if errs else None, 'cueErrorMeanMs': round(float(np.mean(errs)), 1) if errs else None, 'cues': len(errs),
        'maxDriftPct': grid['maxDriftPct'],
        'voiceBandPct': round(float(spec[(freqs >= 1000) & (freqs < 4000)].sum() / spec.sum() * 100), 1),
        'under400Pct': round(float(spec[freqs < 400].sum() / spec.sum() * 100), 1),
        'gapsPct': round(len(quiet) / max(1, len(playing)) * 100, 1), **seam,
    }
    for k, v in out.items():
        if isinstance(v, float) and v != v:
            out[k] = None
            unchecked.append({'key': k, 'why': f'{k} came back empty'})
    return {**out, 'unchecked': unchecked}


def loop_seam(y, sr, grid):
    """The track played twice: are the 2 bars before the loop point as loud as the 2 after (one drum pattern cycle), and does the tempo carry over."""
    end, twice = len(y) / sr, np.concatenate([y, y])
    rms = lambda a, z: 10 * np.log10(np.mean(twice[int(a * sr):int(z * sr)] ** 2) + 1e-12)
    plays = [p for p in grid['parts'] if p['kind'] == 'play']
    last, first = (8 * (p['t1'] - p['t0']) / p['beats'] for p in (plays[-1], plays[0]))
    return {'seamTempoPct': round(abs(plays[-1]['bpm'] / plays[0]['bpm'] - 1) * 100, 2), 'seamJumpDb': round(float(abs(rms(end - last, end) - rms(end, end + first))), 1)}


GATES = [
    ('cue', 'Changes land on the word', lambda s: s['cueErrorMs'], 60, 'ms off'),
    ('drift', 'Tempo holds steady', lambda s: s['maxDriftPct'], 3, '% tempo move'),
    ('chop', 'Nothing plays after the last chord', lambda s: s['hitsAfterLastHit'], 0, 'notes after it'),
    ('stop', 'Already down before the stop', lambda s: s['stopDb'], -6, 'dB'),
    ('silent', 'Silent until it comes back', lambda s: max((r['preDb'] for r in s['reentries']), default=None), -25, 'dB'),
    ('attack', 'Back in on the word, no fade', lambda s: s['attackMs'], 30, 'ms to full'),
    ('seamTempo', 'Tempo carries through the loop', lambda s: s.get('seamTempoPct'), 3, '% tempo jump'),
    ('seam', 'Loops with no bump', lambda s: s.get('seamJumpDb'), 3, 'dB'),
]


SCORE_KEY = {'cue': 'cueErrorMs', 'drift': 'maxDriftPct', 'chop': 'hitsAfterLastHit', 'stop': 'stopDb', 'attack': 'attackMs', 'seamTempo': 'seamTempoPct', 'seam': 'seamJumpDb'}


def gates(score):
    """Every check a track must pass. A check with nothing to measure (no full stop in the take) is left out;
    one that should have run but could not is kept, failed, with its reason in `unchecked`."""
    rows, why = [], {u['key']: u['why'] for u in score.get('unchecked', [])}
    for key, label, get, limit, unit in GATES:
        value = get(score)
        reason = why.get(key) or why.get(SCORE_KEY.get(key))
        if reason:
            rows.append({'key': key, 'label': label, 'value': None, 'limit': limit, 'unit': unit, 'ok': False, 'unchecked': reason})
        elif value is not None:
            rows.append({'key': key, 'label': label, 'value': value, 'limit': limit, 'unit': unit, 'ok': value <= limit})
    return rows


def write_try(slug, tid, bed, meta, grid, out, events=None):
    d = WORK / slug / 'tries' / tid
    d.mkdir(parents=True, exist_ok=True)
    sf.write(d / 'bed.wav', bed.T, SR, subtype='PCM_16')
    opus(d / 'bed.wav', d / 'bed.opus')
    lufs, peak = loudness(d / 'bed.wav')
    data = {**meta, 'id': tid, 'file': f'tries/{tid}/bed.opus', 'lufs': lufs, 'peak': peak, 'voiceLufs': out['voiceLufs'], 'bpm': grid['bpm'],
            'parts': [{k: v for k, v in p.items() if k != 'beatTimes'} for p in grid['parts']], 'bars': grid['bars'], 'level': curve(bed), 'levelMedian': round(float(np.median(dbfs(bed))), 1), 'score': score(d / 'bed.wav', grid, out)}
    data['gates'] = gates(data['score'])
    data['passed'] = all(g['ok'] for g in data['gates'])
    data['engine'] = code_stamp(TRACK_CODE)
    write_json(d / 'try.json', data)
    from .viz import write_track
    write_track(d / 'track.json', bed, SR, slug, grid['parts'], grid['bpm'], events)
    append_jsonl(LIBRARY / 'ledger.jsonl', {'slug': slug, 'try': tid, 'kind': meta.get('kind'), 'bpm': grid['bpm'], 'passed': data['passed'], **data['score']})
    return data


def export(slug, tid, under=None, out=None):
    speech, t = read_json(WORK / slug / 'speech.json'), read_json(WORK / slug / 'tries' / tid / 'try.json')
    under = under if under is not None else t['under']
    gain = t['voiceLufs'] - under - t['lufs']
    concept = Path(speech['concept']) if speech.get('concept') else None
    out = Path(out or (concept / 'music' if concept else WORK / slug / 'exports') / f'{slug}-{tid}.mp4')
    out.parent.mkdir(parents=True, exist_ok=True)
    graph = f"[0:a]aresample=48000,aformat=channel_layouts=stereo[vo];[1:a]volume={gain}dB[bd];[vo][bd]amix=inputs=2:normalize=0:duration=first,loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000,alimiter=limit=0.8:level=false[a]"
    loop = ['-t', f"{video_seconds(speech['video']):.6f}"] if read_json(WORK / slug / 'outline.json', {}).get('loop') else []
    run('ffmpeg', '-y', '-v', 'error', '-i', speech['video'], '-i', WORK / slug / 'tries' / tid / 'bed.wav', '-filter_complex', graph, '-map', '0:v', '-map', '[a]', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', *loop, out)
    mixed, peak = loudness(out)
    row = {'slug': slug, 'try': tid, 'under': under, 'bedGainDb': round(gain, 1), 'file': str(out), 'lufs': mixed, 'peak': peak, 'seconds': seconds(out)}
    append_jsonl(LIBRARY / 'exports.jsonl', row)
    if concept:
        m = read_json(concept / 'music.json', {'mix': '', 'tests': []})
        m['mix'] = f"Made by VideoMusicMaker (soundtrack.localhost:4812): music written to the take's own timing, {under} LU under the voice, whole short at -14 LUFS."
        m['tests'] = [x for x in m['tests'] if x.get('id') != f'soundtrack-{tid}'] + [{'id': f'soundtrack-{tid}', 'title': t['name'], 'note': f"{t['bpm']} BPM, {t['key']}, changes within {t['score']['cueErrorMs']} ms of the words", 'file': f'music/{out.name}', 'credits': 0, 'bed': {'tool': 'soundtrack', 'try': tid}}]
        write_json(concept / 'music.json', m)
        row['studio'] = f"http://127.0.0.1:4801/sound/{concept.name}"
    return row
