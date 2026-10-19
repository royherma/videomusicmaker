"""Trim a talking-head take by its sound before scoring it. Rules: CLAUDE.md "Rules for trims".

trim.py phrases <video> <dir>         waveform -> phrases split at real pauses, WhisperX text on each -> <dir>/phrases.json
trim.py cut <video> <dir> <out.mp4>   keeps <dir>/keep.json {"keep": [k, ...], "startAt": {"k": sec}, "endAt": {"k": sec}}
trim.py check <video> <dir>           each kept piece alone through Whisper, plus <dir>/wave.png (kept = orange)
"""
import json, os, shutil, struct, subprocess, sys, zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine.common import WHISPER_MODEL

import numpy as np
import soundfile as sf

WHISPERX = os.environ.get('WHISPERX') or shutil.which('whisperx') or str(Path.home() / '.cache/whisperx-venv/bin/whisperx')
FILLERS = 'Umm, so, uh, I- I think, like, you know, the- the thing is, uh, hmm.'  # makes Whisper write fillers instead of smoothing them
FRAME, VOICE_DB, MIN_PAUSE = 0.01, -45, 0.25
PRE, POST, END_HOLD, KEEP_PAUSE = 0.15, 0.22, 0.6, 0.45


def sh(*a):
    return subprocess.run([str(x) for x in a], capture_output=True, text=True)


def level(d):
    y, sr = sf.read(d / 'voice.wav')
    hop = int(sr * FRAME)
    return np.array([20 * np.log10(np.sqrt(np.mean(y[i:i + hop] ** 2)) + 1e-9) for i in range(0, len(y) - hop, hop)])


def phrases(video, d):
    d.mkdir(parents=True, exist_ok=True)
    sh('ffmpeg', '-v', 'error', '-y', '-i', video, '-ar', '16000', '-ac', '1', d / 'voice.wav')
    sh(WHISPERX, d / 'voice.wav', '--model', 'small.en', '--language', 'en', '--compute_type', 'int8', '--output_format', 'json', '--output_dir', d)
    words = [x for s in json.loads((d / 'voice.json').read_text())['segments'] for x in s.get('words', []) if 'start' in x]
    on, runs, i = level(d) > VOICE_DB, [], 0
    while i < len(on):
        j = i
        while j < len(on) and on[j] == on[i]:
            j += 1
        if on[i]:
            if runs and i * FRAME - runs[-1][1] < MIN_PAUSE:
                runs[-1][1] = j * FRAME
            else:
                runs.append([i * FRAME, j * FRAME])
        i = j
    P = [{'k': k, 's': round(a, 2), 'e': round(b, 2), 'text': ' '.join(w['word'] for w in words if a - 0.05 <= (w['start'] + w['end']) / 2 <= b + 0.05)}
         for k, (a, b) in enumerate(r for r in runs if r[1] - r[0] >= 0.08)]
    (d / 'phrases.json').write_text(json.dumps(P))
    for p in P:
        print(f"{p['k']:3} {p['s']:6.2f}-{p['e']:6.2f}  {p['text']}")


def pieces(d):
    P, spec = json.loads((d / 'phrases.json').read_text()), json.loads((d / 'keep.json').read_text())
    keep = sorted(spec['keep'])
    start_at, end_at = ({int(k): v for k, v in spec.get(n, {}).items()} for n in ('startAt', 'endAt'))
    segs = []
    for n, k in enumerate(keep):
        p = P[k]
        prev_e = P[k - 1]['e'] if k else 0
        next_s = P[k + 1]['s'] if k + 1 < len(P) else p['e'] + 5
        s = start_at.get(k, max(p['s'] - PRE, (prev_e + p['s']) / 2))
        e = end_at.get(k, min(p['e'] + (END_HOLD if n == len(keep) - 1 else POST), (p['e'] + next_s) / 2))
        joined = segs and keep[n - 1] == k - 1 and k not in start_at and keep[n - 1] not in end_at and p['s'] - prev_e <= KEEP_PAUSE
        if joined:
            segs[-1][1] = round(e, 3)
        else:
            segs.append([round(s, 3), round(e, 3)])
    return P, segs


def cut(video, d, out):
    _, segs = pieces(d)
    f, cat = [], ''
    for k, (s, e) in enumerate(segs):
        f.append(f"[0:v]trim=start={s}:end={e},setpts=PTS-STARTPTS[v{k}]")
        f.append(f"[0:a]atrim=start={s}:end={e},asetpts=PTS-STARTPTS,afade=t=in:d=0.02,afade=t=out:st={e - s - 0.06:.3f}:d=0.06[a{k}]")
        cat += f"[v{k}][a{k}]"
    f.append(f"{cat}concat=n={len(segs)}:v=1:a=1[v][a]")
    r = sh('ffmpeg', '-v', 'error', '-y', '-i', video, '-filter_complex', ';'.join(f), '-map', '[v]', '-map', '[a]', '-c:v', 'libx264', '-crf', '18',
           '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', out)
    if r.returncode:
        sys.exit(r.stderr)
    print(json.dumps({'pieces': len(segs), 'seconds': round(sum(e - s for s, e in segs), 2), 'segs': segs}))


def wave(d, segs, png):
    db = level(d)
    t = np.arange(len(db)) * FRAME
    h = np.clip((db + 70) / 70, 0, 1)
    rows = [(a, min(a + 20, t[-1])) for a in np.arange(0, t[-1], 20)]
    W, H = 2000, 160
    img = np.full((H * len(rows), W, 3), 250, np.uint8)
    for r, (a, b) in enumerate(rows):
        for x in range(W):
            tt = a + (b - a) * x / W
            if tt > t[-1]:
                break
            amp = int(h[min(int(tt / FRAME), len(h) - 1)] * (H / 2 - 12))
            kept = any(s <= tt <= e for s, e in segs)
            img[r * H + H // 2 - amp:r * H + H // 2 + amp + 1, x] = (230, 110, 60) if kept else (170, 170, 170)
        for s in range(int(a), int(b) + 1):
            img[r * H:r * H + 8, min(W - 1, int((s - a) / (b - a) * W))] = (0, 0, 0)
    raw = b''.join(b'\0' + img[i].tobytes() for i in range(img.shape[0]))
    chunk = lambda k, v: struct.pack('>I', len(v)) + k + v + struct.pack('>I', zlib.crc32(k + v) & 0xffffffff)
    Path(png).write_bytes(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', W, img.shape[0], 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(raw, 6)) + chunk(b'IEND', b''))


def check(video, d):
    P, segs = pieces(d)
    for k, (s, e) in enumerate(segs):
        wav = d / f'piece-{k}.wav'
        sh('ffmpeg', '-v', 'error', '-y', '-ss', s, '-to', e, '-i', d / 'voice.wav', '-af', 'adelay=600,apad=pad_dur=0.6', wav)
        heard = sh('whisper-cli', '-m', WHISPER_MODEL, '-f', wav, '-np', '-nt').stdout.strip()
        print(f"{k:2} {s:6.2f}-{e:6.2f}  {heard}")
    wave(d, segs, d / 'wave.png')
    print(d / 'wave.png')


if __name__ == '__main__':
    cmd, video, d = sys.argv[1], sys.argv[2], Path(sys.argv[3])
    {'phrases': lambda: phrases(video, d), 'cut': lambda: cut(video, d, sys.argv[4]), 'check': lambda: check(video, d)}[cmd]()
