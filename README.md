# StoryWriter

Turns an audio track into a short story whose **structure** is inferred from the
sound — not a one-dimensional "loud = happy" mapping, but multiple characters and
intersecting arcs read from the music's layers, contrasts, peaks and crossings.

## The pipeline

```
upload mp3
  → extract_arcs_hpss.py    audio analysis (one NumPy STFT → 7 feature arcs over time)
  → server.py               downsamples features for the live graph
  → story_generator.py      THE MODEL DRIVES:
        1. reads the audio's structure (layers, contrasts, peaks, crossings) and
           infers the SEQUENCE OF EMOTIONAL STATES it moves through — not
           one-dimensional
        2. emits a POINTS line: a JSON array of 5–9 emotional waypoints
           (valence/arousal/dominance, 1–9) for how the piece FEELS, moment to moment
        3. WRITES one coherent short story that traces that emotional arc — a single
           drafting pass — optionally studying a published opening page for voice
```

The emotional arc comes entirely from the model reading the audio. (Earlier versions
queried a MongoDB word/phrase lexicon per waypoint; that path has been removed.)

The generator streams newline-delimited JSON events on stdout (`status`,
`reasoning`, `lookup`, `story`, `story_reset`, `final`, `error`); `server.py` turns
those into the job state that `/status` serves, so the browser shows the audio graph
filling in, the model's reasoning, each emotional waypoint as a dot, and the story
typing out.

## Files

| File | Role |
|------|------|
| `index.html` | The UI (React, single file). Served at `/` and proxied to `/storywriter`. |
| `server.py` | Backend on :8000. Upload → extract → generate; serves `/status`. |
| `story_generator.py` | The model-driven story engine. |
| `extract_arcs_hpss.py` | Pure-NumPy audio-feature extractor → `*_arcs.csv`. |
| `build_openings.py` | Loads public-domain opening pages into MongoDB (style only, optional). |
| `run-storywriter.ps1` | One command: check deps/Ollama, start the stack, open the browser. |
| `restart-storywriter.ps1` | Stop/relaunch just the backend on :8000. |
| `install-storywriter-task.ps1` | Register the boot auto-start task. |

## Prerequisites

- **Ollama** running a model (e.g. `qwen2.5:7b`): `ollama list`.
- Python 3.12 with `pymongo`, `numpy`, `imageio-ffmpeg`.
- **MongoDB** is **optional** — used only for the opening-page style exemplars
  (`build_openings.py`). Generation works fine without it.

## Run

```powershell
powershell -ExecutionPolicy Bypass -File .\run-storywriter.ps1
```

That checks dependencies, starts the backend (:8000) and gateway (:80), and opens
`http://localhost/storywriter`. Standalone (no gateway): `http://localhost:8000`.

Config via env vars: `STORYWRITER_OLLAMA`, `STORYWRITER_MONGO_URI`,
`STORYWRITER_OPENINGS_DB`, `STORYWRITER_OPENINGS_COLL`, `STORYWRITER_TOKEN`.
