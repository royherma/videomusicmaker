# Third-party parts

None of these are stored in this repo. `scripts/install.sh` downloads them and checks each file's SHA-256.

| Part | Used for | Source | License |
| --- | --- | --- | --- |
| GeneralUser GS 2.0.3 (SoundFont), S. Christian Collins | Recorded instruments (piano, strings, guitar...) | github.com/mrbumpy409/GeneralUser-GS, commit 9704918 | GeneralUser GS License v2.0: free for private and commercial music, may be used in software projects ([text](https://github.com/mrbumpy409/GeneralUser-GS/blob/main/documentation/LICENSE.txt)) |
| Whisper large-v3-turbo (ggml), OpenAI | Writing down what is said, with word times | huggingface.co/ggerganov/whisper.cpp | MIT |
| whisper.cpp | Runs the Whisper model | github.com/ggml-org/whisper.cpp | MIT |
| FluidSynth | Plays the SoundFont | fluidsynth.org | LGPL-2.1 (loaded at run time, not shipped) |
| pyFluidSynth | Python link to FluidSynth | PyPI | MIT |
| FFmpeg, Rubber Band | Audio/video read, write, time-stretch | ffmpeg.org, breakfastquay.com | LGPL/GPL (separate programs, not shipped) |
| Demucs (optional) | Splitting a reference song into parts | github.com/facebookresearch/demucs | MIT |
| numpy, scipy, soundfile, numba, librosa | Analysis and synthesis | PyPI | BSD (numpy, scipy, soundfile, numba), ISC (librosa) |

Music you make with VideoMusicMaker is yours.
