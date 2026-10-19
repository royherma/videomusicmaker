---
name: videomusicmaker
description: "Write background music that fits what is said in a video: words and timings from local Whisper, music changes snapped to the spoken cues, 20 genres composed in code and each checked against 6 timing tests, then an mp4 with the chosen track mixed under the voice. No AI service or API key. Trigger phrases: /videomusicmaker <video>, 'music for this video', 'score my video', 'background music under my voice', 'add a soundtrack to this take', 'which genre fits this video'."
user-invocable: true
version: 1.0.0
---

# VideoMusicMaker

The tool is the repo this folder sits in: `REPO` = this skill's base directory, one level up (`<base>/..`).
Run it, do not rebuild it. Every command below runs from `REPO`.

## 1. Check it is installed

```sh
bin/soundtrack doctor
```

Any `MISS` line: run `scripts/install.sh` (it prints the one `brew install` line for missing programs and stops).
Rerun `doctor` until it says `ready`. Do not guess around a missing program.

## 2. Make the music

```sh
bin/soundtrack speech "<video>" --slug <slug>     # slug: short lowercase name for the video
bin/soundtrack make <slug> all                    # all 20 genres; each rewritten until it passes or runs out of tries
bin/soundtrack results <slug>                     # one line per genre: pass/FAIL, tests passed, BPM, key, cue timing
```

Check `speech` printed `sentences` above 1. If it is 1, the transcript lost its punctuation and there will be no
stops; say so before going on.

## 3. Let the person listen and pick

```sh
node server.mjs        # in the background; page at http://soundtrack.localhost:4812/?v=<slug>
```

Give them the URL. Choosing music is their call: the 6 tests check timing, not taste. Never pick for them unless
they ask; then pick the passed genre with the lowest cue timing and say that is how you chose.

## 4. Export the one they chose

```sh
bin/soundtrack export <slug> <genre-id> [--under 10]    # --under: dB the music sits under the voice (default per genre)
```

It prints the mp4 path (`work/<slug>/exports/`). Hand that full path back.

## Rules

- Each video gets its own take (key, tune, chord pattern). `make <slug> all --fresh` writes a new take; plain `make`
  repeats the current one exactly.
- A FAIL in `results` is kept on purpose (best try). Say which test failed (`gates` in `work/<slug>/tries/<id>/try.json`).
- New genre = a JSON file in `engine/themes/` (README, "Add a genre"). Never edit the engine to change one genre.
- Costs nothing beyond computer time: no network calls after install.
