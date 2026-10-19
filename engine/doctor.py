"""`soundtrack doctor`: every program, package and file the engine needs, with what to do about a missing one."""
import importlib.metadata, shutil, subprocess, sys
from pathlib import Path

from .common import DEMUCS, ROOT, WHISPER_MODEL
from .synth import SOUNDFONT

PROGRAMS = [('ffmpeg', 'brew install ffmpeg'), ('ffprobe', 'brew install ffmpeg'), ('whisper-cli', 'brew install whisper-cpp'),
            ('rubberband', 'brew install rubberband'), ('node', 'brew install node')]


def doctor():
    bad = 0

    def row(ok, what, detail, fix='', need=True):
        nonlocal bad
        bad += need and not ok
        print(f"{'ok  ' if ok else 'MISS' if need else 'opt '}  {what:<22} {detail}{'' if ok else f'  ->  {fix}'}")

    row(sys.version_info >= (3, 11), 'python', sys.version.split()[0], 'Python 3.11 or newer')
    for line in (ROOT / 'requirements.txt').read_text().split():
        name, _, want = line.partition('==')
        try: have = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError: have = None
        row(have is not None, name, have or 'not installed', 'scripts/install.sh')
    for name, fix in PROGRAMS:
        row(bool(shutil.which(name)), name, shutil.which(name) or 'not found', fix)
    try:
        import fluidsynth  # noqa: F401
        row(True, 'libfluidsynth', 'loads')
    except Exception as e:
        row(False, 'libfluidsynth', str(e)[:60], 'brew install fluid-synth')
    row(SOUNDFONT.exists(), 'soundfont', str(SOUNDFONT.relative_to(ROOT)) if SOUNDFONT.exists() else 'missing', 'scripts/install.sh')
    row(Path(WHISPER_MODEL).exists(), 'whisper model', str(WHISPER_MODEL), 'scripts/install.sh, or set WHISPER_MODEL')
    demucs = shutil.which(DEMUCS) or (Path(DEMUCS).exists() and DEMUCS)
    row(bool(demucs), 'demucs', demucs or 'not found', 'pip install demucs (only to learn from a reference song)', need=False)
    if shutil.which('ffmpeg'):
        enc = subprocess.run(['ffmpeg', '-hide_banner', '-encoders'], capture_output=True, text=True).stdout
        row('libopus' in enc, 'ffmpeg libopus', 'yes' if 'libopus' in enc else 'no', 'an ffmpeg built with libopus')
    print('ready' if not bad else f'{bad} missing')
    return 0 if not bad else 1
