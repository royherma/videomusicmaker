import functools, hashlib, json, os, re, shutil, subprocess, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORK, RESEARCH, LIBRARY, THEMES = ROOT / 'work', ROOT / 'research', ROOT / 'library', ROOT / 'engine' / 'themes'
WHISPER_MODEL = Path(os.environ.get('WHISPER_MODEL') or next((p for p in (ROOT / 'models/ggml-large-v3-turbo.bin', Path.home() / '.cache/whisper/ggml-large-v3-turbo.bin') if p.exists()), ROOT / 'models/ggml-large-v3-turbo.bin'))
DEMUCS = os.environ.get('DEMUCS') or shutil.which('demucs') or (str(ROOT / '.venv/bin/demucs') if (ROOT / '.venv/bin/demucs').exists() else 'demucs')
SR = 48000
TRACK_CODE, SPEECH_CODE = ('**/*.py', 'themes/*.json'), ('speech.py',)
NOTES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']


@functools.lru_cache(maxsize=None)
def code_stamp(patterns):
    """Hash of the engine files that shaped an output. server.mjs computes the same hash to mark old work as stale."""
    files = sorted({f for p in patterns for f in (ROOT / 'engine').glob(p) if '__pycache__' not in f.parts}, key=lambda f: f.relative_to(ROOT).as_posix())
    h = hashlib.sha1()
    for f in files:
        h.update(f.relative_to(ROOT).as_posix().encode() + b'\0' + f.read_bytes())
    return h.hexdigest()[:10]


def run(*cmd, check=True):
    return subprocess.run([str(c) for c in cmd], capture_output=True, text=True, check=check)


def read_json(path, default=None):
    path = Path(path)
    return json.loads(path.read_text()) if path.exists() else default


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(data, indent=1))
    tmp.replace(path)


def append_jsonl(path, row):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a') as f:
        f.write(json.dumps({'at': time.strftime('%Y-%m-%dT%H:%M:%S%z'), **row}) + '\n')


def seconds(file):
    return float(run('ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', file).stdout)


def video_seconds(file):
    """The picture's own length: what a player loops on, often a few frames shorter than the file."""
    return float(run('ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=duration', '-of', 'csv=p=0', file).stdout.strip() or seconds(file))


def loudness(file):
    """Integrated loudness (LUFS) and true peak (dBTP) of a file, measured by ffmpeg ebur128."""
    err = run('ffmpeg', '-nostats', '-i', file, '-vn', '-af', 'ebur128=peak=true', '-f', 'null', '-').stderr.split('Summary:')[-1]
    return float(re.search(r'I:\s+(-?[\d.]+) LUFS', err).group(1)), float(re.search(r'Peak:\s+(-?(?:[\d.]+|inf)) dBFS', err).group(1))


def slugify(name):
    return re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')[:48]


def opus(wav, out, kbps=128):
    run('ffmpeg', '-y', '-v', 'error', '-i', wav, '-c:a', 'libopus', '-b:a', f'{kbps}k', out)


def step(name, state, note=''):
    """One row of the build list the page shows live. state: run | ok | fail."""
    build = read_json(WORK / 'build.json', {'steps': []})
    row = next((s for s in build['steps'] if s['name'] == name), None)
    if row is None:
        row = {'name': name, 'started': time.time()}
        build['steps'].append(row)
    row.update(state=state, note=note, at=time.time())
    write_json(WORK / 'build.json', build)
