"""What is said and when: words, sentences, pauses, sections. Everything the music is fitted to."""
import json, re
from pathlib import Path

import numpy as np
import soundfile as sf

from .common import SPEECH_CODE, WHISPER_MODEL, WORK, code_stamp, loudness, opus, read_json, run, seconds, write_json

END = re.compile(r'[.?!]["\')]*$')
PIVOT = re.compile(r"^(but|now|here'?s|here is|so|one|see|the truth|okay|ok|why|except|and yet)\b", re.I)
TAG_LEVEL = {'hook': 2, 'context': 2, 'rehook-1': 3, 'conflict': 3, 'rehook-2': 3, 'share-hook': 4}


def sentences(words):
    out, cur = [], None
    for w in words:
        cur = cur or {'t': w['t'], 'words': []}
        cur['words'].append(w['w'])
        cur['end'] = w['t'] + w['d']
        if END.search(w['w']):
            out.append(cur)
            cur = None
    if cur:
        out.append(cur)
    return [{'t': round(s['t'], 3), 'end': round(s['end'], 3), 'text': ' '.join(s['words']), 'n': len(s['words'])} for s in out]


def pauses(voice, above_floor=9, shortest=0.3, join=0.15, blip=0.15):
    """Silence measured against this take's own room noise; a cluster of sound with under `blip` s voiced (a tick, a click) is not voice."""
    x, sr = sf.read(voice, dtype='float32')
    x = x.mean(1) if x.ndim > 1 else x
    hop = sr // 100
    frames = x[:len(x) // hop * hop].reshape(-1, hop)
    db = 10 * np.log10(np.convolve((frames ** 2).mean(1), np.ones(3) / 3, 'same') + 1e-12)
    on = db > np.percentile(db, 10) + above_floor
    edges = np.flatnonzero(np.diff(np.r_[0, on.astype(np.int8), 0]))
    clusters = []
    for a, b in zip(edges[::2], edges[1::2]):
        if clusters and a - clusters[-1][1] < join * 100:
            clusters[-1][1:] = [b, clusters[-1][2] + b - a]
        else:
            clusters.append([a, b, b - a])
    voiced = [(float(a) / 100, float(b) / 100) for a, b, n in clusters if n >= blip * 100]
    cuts = [0.0] + [v for span in voiced for v in span] + [len(on) / 100.0]
    return [{'t': round(a, 3), 'd': round(b - a, 3)} for a, b in zip(cuts[::2], cuts[1::2]) if b - a >= shortest]


def transcribe(voice, out, terms=''):
    wav = Path(out).with_suffix('.16k.wav')
    run('ffmpeg', '-y', '-v', 'error', '-i', voice, '-ac', '1', '-ar', '16000', wav)
    run('whisper-cli', '-m', WHISPER_MODEL, '-f', wav, '-ml', '1', '-sow', '-oj', '-of', Path(out).with_suffix(''), '-np', *(['--prompt', terms] if terms else []))
    wav.unlink()
    rows = json.loads(Path(out).read_text())['transcription']
    words = [{'w': r['text'].strip(), 't': r['offsets']['from'] / 1000, 'd': (r['offsets']['to'] - r['offsets']['from']) / 1000} for r in rows if r['text'].strip() and not r['text'].strip().startswith('[')]
    if not terms and len(words) > 20 and not any(END.search(w['w']) for w in words):
        return transcribe(voice, out, 'Okay. So, here is the thing: it works. Does it?')  # tight cuts can make Whisper drop all punctuation
    return words


def mark_pivots(sents, tags=None):
    """A pivot is a short line that turns the story ("But hold on."). The music stops under it and comes back on the next line."""
    for i, s in enumerate(sents[:-1]):
        length = s['end'] - s['t']
        answers = i > 0 and sents[i - 1]['text'].rstrip('"\')').endswith('?')
        if s['t'] > 4 and ((s['n'] <= 6 and length <= 2.8 and PIVOT.search(s['text'])) or (answers and s['n'] <= 10 and length <= 3.6)):
            score = 2 if answers and not PIVOT.search(s['text']) else 3 if re.match(r'but\b', s['text'], re.I) else 2 if re.match(r"(here'?s|one|the truth|except)\b", s['text'], re.I) else 1
            s['pivot'] = score + (1 if tags and str(tags.get(s.get('beat'), '')).startswith('rehook') else 0)
    return sents


def finish(slug, title, video, voice, words, sections, extra=None, snap=False):
    out = WORK / slug
    out.mkdir(parents=True, exist_ok=True)
    src = ['-i', voice, '-vn'] if has_audio(voice) else ['-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=stereo', '-t', str(seconds(video))]
    run('ffmpeg', '-y', '-v', 'error', *src, '-ac', '2', '-ar', '48000', out / 'voice.wav')
    opus(out / 'voice.wav', out / 'voice.opus', 96)
    sents, gaps = sentences(words), pauses(out / 'voice.wav')
    if snap:
        starts = [g['t'] + g['d'] for g in gaps]
        for s in sents:
            near = [e for e in starts if -0.3 <= e - s['t'] <= 1.2]
            if near:
                s['t'] = round(min(near, key=lambda e: abs(e - s['t'])), 3)
        for s in sents:
            gap = next((g for g in gaps if g['t'] <= s['t'] < g['t'] + g['d']), None)
            if gap:
                s['t'] = round(gap['t'] + gap['d'], 3)
            gap = next((g for g in gaps if g['t'] < s['end'] <= g['t'] + g['d'] and g['t'] > s['t']), None)
            if gap:
                s['end'] = round(gap['t'], 3)
            s['end'] = max(s['end'], round(s['t'] + 0.3, 3))
    for s in sents:
        s['beat'] = next((c['beat'] for c in reversed(sections.get('cues', [])) if c['t'] <= s['t'] + 0.05), None)
    data = {
        'slug': slug, 'title': title, 'video': str(video), 'seconds': round(seconds(video), 3),
        'words': [{'w': w['w'], 't': round(w['t'], 3), 'd': round(w['d'], 3)} for w in words],
        'sentences': mark_pivots(sents, sections.get('tags')),
        'pauses': gaps,
        'sections': sections.get('sections', []),
        'reader': code_stamp(SPEECH_CODE),
        **(extra or {}),
    }
    write_json(out / 'speech.json', data)
    return data


def from_concept(concept):
    """A TG Studio video: its take's word times, its script's sections and its arc tags are already on disk."""
    concept = Path(concept)
    slug = concept.name
    short, script = read_json(concept / 'short.json'), read_json(sorted((concept / 'script').glob('v*.json'))[-1])
    take = read_json(concept / 'takes' / f"{short['voice']['take']}.json")
    tags = read_json(concept / 'arc.json', {}).get('tags', {})
    start = short.get('from', 0)
    words = [{**w, 't': w['t'] - start} for w in take['words'] if w['t'] >= start - 0.01]
    cues = [{'t': round(c['t'] - start, 3), 'beat': c['beat']} for c in take['cues'] if 'beat' in c]
    name = {b['id']: b['section'] for b in script['beats']}
    sections = []
    for c in cues:
        if not sections or sections[-1]['name'] != name.get(c['beat']):
            sections.append({'t': c['t'], 'name': name.get(c['beat'], ''), 'tag': tags.get(c['beat'], ''), 'level': TAG_LEVEL.get(tags.get(c['beat'], ''), 2)})
    video = concept / 'short' / f'{slug}.mp4'
    return finish(slug, read_json(concept / 'concept.json')['title'], video, video, words, {'cues': cues, 'tags': tags, 'sections': sections}, {'concept': str(concept), 'take': short['voice']['take']})


def from_video(video, slug, title=None, voice=None):
    """Any video: Whisper gives the words. Pass `voice` (a voice-only file) when the video already has music in it."""
    out = WORK / slug
    out.mkdir(parents=True, exist_ok=True)
    silent = not has_sound(voice or video)
    words = [] if silent else transcribe(voice or video, out / 'whisper.json')
    return finish(slug, title or Path(video).stem, video, voice or video, words, {}, {'noVoice': True} if silent else None, snap=True)


def has_sound(file):
    """Whisper writes "Thank you." over a silent track, so silence is checked first: no audio stream, or a peak under -60 dB."""
    return has_audio(file) and loudness(file)[1] > -60


def has_audio(file):
    return bool(run('ffprobe', '-v', 'error', '-select_streams', 'a', '-show_entries', 'stream=index', '-of', 'csv=p=0', file).stdout.strip())
