#!/bin/sh
# Sets up VideoMusicMaker in this folder: Python env, packages, soundfont, Whisper model. Safe to rerun.
set -eu
cd "$(dirname "$0")/.."

SF_URL=https://raw.githubusercontent.com/mrbumpy409/GeneralUser-GS/97049183643d5fc5a9322a69c5b09efb667c6c3a/GeneralUser-GS.sf2
SF_SHA=9575028c7a1f589f5770fccc8cff2734566af40cd26ed836944e9a5152688cfe
WM_URL=https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo.bin
WM_SHA=1fc70f774d38eb169993ac391eea357ef47c88757ef72ee5943879b7e8e2bc69

missing=""
for bin in ffmpeg ffprobe whisper-cli rubberband node; do command -v "$bin" >/dev/null 2>&1 || missing="$missing $bin"; done
if [ -n "$missing" ]; then
  echo "Missing programs:$missing"
  echo "  macOS:  brew install ffmpeg whisper-cpp rubberband fluid-synth node"
  echo "  Debian: apt install ffmpeg rubberband-cli fluidsynth libfluidsynth3 nodejs  (whisper-cli: build whisper.cpp)"
  exit 1
fi

if [ ! -x .venv/bin/python ]; then
  if command -v uv >/dev/null 2>&1; then uv venv --python 3.12 .venv; else python3 -m venv .venv; fi
fi
if command -v uv >/dev/null 2>&1; then uv pip install --python .venv/bin/python -r requirements.txt; else .venv/bin/python -m pip install -q -r requirements.txt; fi

sha() { if command -v shasum >/dev/null 2>&1; then shasum -a 256 "$1"; else sha256sum "$1"; fi | cut -d' ' -f1; }
fetch() { # url sha dest
  [ -f "$3" ] && [ "$(sha "$3")" = "$2" ] && { echo "ok   $3"; return; }
  echo "get  $3"; mkdir -p "$(dirname "$3")"; curl -fL --progress-bar -o "$3.part" "$1"
  [ "$(sha "$3.part")" = "$2" ] || { echo "checksum mismatch: $3"; rm -f "$3.part"; exit 1; }
  mv "$3.part" "$3"
}
fetch "$SF_URL" "$SF_SHA" library/soundfonts/GeneralUser-GS.sf2
if [ -n "${WHISPER_MODEL:-}" ] && [ -f "$WHISPER_MODEL" ]; then echo "ok   $WHISPER_MODEL"
elif [ -f "$HOME/.cache/whisper/ggml-large-v3-turbo.bin" ]; then echo "ok   $HOME/.cache/whisper/ggml-large-v3-turbo.bin"
else fetch "$WM_URL" "$WM_SHA" models/ggml-large-v3-turbo.bin; fi

bin/soundtrack doctor
