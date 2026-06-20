# StoryWriter — Handoff

Turns an audio track into a short story whose **structure is inferred from the
sound** — not a one-dimensional "loud = happy" mapping, but multiple characters and
intersecting arcs read from the music's layers, contrasts, peaks and crossings. A
local model drives the whole thing: it reads the audio and infers the emotional arc
the story should trace.

This was formerly the `resonator/` sub-app; it is now a single flat project at
`C:\Projects\GithubRoot\Portfolio\StoryWriter`, served at the public path
`/storywriter`.

## Pipeline

```
upload mp3
  → extract_arcs_hpss.py   pure-NumPy audio analysis (one STFT → 7 feature arcs) → input_arcs.csv
  → server.py              downsamples the features for the live graph
  → story_generator.py     THE MODEL DRIVES:
        1. infers a story SHAPE from the audio's structure (multiple characters,
           intersecting arcs, epoch moments) — explicitly not one-dimensional
        2. emits a POINTS line — a JSON array of 5–9 emotional waypoints
           (valence/arousal/dominance, 1–9) for how the piece FEELS over time
        3. writes ONE short story tracing that arc, in a single drafting pass
```

Round trip: **Python ⇄ Ollama.** (MongoDB is optional — opening-page style exemplars only.)

> **Architecture note:** the per-word MongoDB lexicon and the tool-calling
> `lookup_words` round-trip were removed. The arc now comes from the model reading the
> audio and emitting a POINTS array; there is no word/phrase lookup and no revise pass
> (generation is always a single draft).

`story_generator.py` streams newline-delimited JSON events on stdout
(`status`, `reasoning`, `lookup`, `story`, `story_reset`, `final`, `error`); `server.py`
turns those into the job state that `/status` serves, so the browser shows the audio
graph build left-to-right, the model's MAPPING/SHAPE reasoning, each emotional waypoint
as a dot, and the story typing out beside the status timeline.

## Processes & ports

| Port | Process | Interpreter | Role |
|------|---------|-------------|------|
| 80 | `app.py` (Portfolio gateway) | **Python 3.14** (`...\pythoncore-3.14-64`) | Front door for the whole portfolio. Serves the boot screen (`index.html`) at `/`, reverse-proxies `/storywriter/*` to :8000. |
| 8000 | `server.py` (StoryWriter backend) | **Python 3.12** (`C:\Program Files\Python312`) | Upload → extract → generate; serves `/status`, `/prompts.txt`, the UI. |
| 27017 | mongod (Windows service) | — | **Optional.** `StoryWriterCorpus.Openings` style exemplars only. |
| 11434 | Ollama | — | Local LLM. Any capable model (qwen2.5, llama3.1/3.2, …). |

The two app processes are independent and talk over HTTP, so the different
interpreters are fine. **Critical:** `server.py` spawns `story_generator.py` and
`extract_arcs_hpss.py` via `sys.executable`, so every backend dependency must live in
the **3.12**, not the 3.14:

- `numpy` — audio extraction (the extractor is pure NumPy; no librosa/scipy)
- `imageio-ffmpeg` — bundles the ffmpeg used to decode audio
- `pymongo` — only for opening-page exemplars (optional)

Confirm with: `& "C:\Program Files\Python312\python.exe" -c "import numpy,pymongo;print('ok')"`

## Files

| File | Role |
|------|------|
| `index.html` | The UI (React, single file). Served at `/`, proxied at `/storywriter`. |
| `server.py` | Backend on :8000. Upload/extract/generate; `/status`, `/prompts.txt`. |
| `story_generator.py` | Model-driven story engine (reads audio → emotional arc → prose). |
| `extract_arcs_hpss.py` | Pure-NumPy feature extractor → `*_arcs.csv`. |
| `build_openings.py` | Loads public-domain opening pages into MongoDB (style exemplars, optional). |
| `prompts.txt` | Short, editable constraints; prefilled into the UI prompt box and folded into the model's direction. |
| `run-storywriter.ps1` | One command: check deps/Ollama, start the stack, open the browser. |
| `start-storywriter-stack.ps1` | Start BOTH processes in the background (gateway via VBS, backend via pythonw). |
| `restart-storywriter.ps1` | Stop/relaunch just the backend (:8000). |
| `install-storywriter-task.ps1` | Register the boot auto-start task for the backend. |
| `storywriter-finalize.ps1` | One-shot: cleanup + py_compile + deps + Mongo check + restart both. |
| `..\start-gateway.vbs` | Windowless, detached launcher for `app.py` on 3.14 (in the Portfolio folder). |

## Running it

Prereqs: Ollama up with a capable model (qwen2.5/llama3.1/3.2) and the 3.12 deps
installed (above). MongoDB is optional (opening-page exemplars only).

One command (checks deps + Ollama, frees ports, starts both, opens the browser):

```powershell
powershell -ExecutionPolicy Bypass -File ".\run-storywriter.ps1"
```

Or start both in the background without the checks:

```powershell
powershell -ExecutionPolicy Bypass -File ".\start-storywriter-stack.ps1"
```

Either frees :80 and :8000, launches the gateway through `start-gateway.vbs` (3.14, no
window) and the backend with `pythonw` (3.12), then reports each port UP/DOWN. Open
`http://localhost/storywriter` (or `http://localhost:8000` standalone).

Config via env vars: `STORYWRITER_OLLAMA`, `STORYWRITER_MONGO_URI`,
`STORYWRITER_OPENINGS_DB`, `STORYWRITER_OPENINGS_COLL`, `STORYWRITER_TOKEN`.

## The /storywriter route

`app.py` reverse-proxies `/storywriter` and `/storywriter/*` (case-insensitive, so
`/StoryWriter` works) to `http://127.0.0.1:8000`, stripping the prefix. The DOS
landing page (`..\index.html`) navigates to `/storywriter/` when you type
"storywriter" at the boot prompt. The app's own UI is path-aware (`BASE =
location.pathname…`), so the same file works standalone or behind the proxy.

## Known issues & gotchas

- **3.14 `pythonw.exe` is broken** on this pythoncore build, and
  `Start-Process -WindowStyle Hidden` on its `python.exe` dies silently. Launch the
  gateway via `start-gateway.vbs` instead (`WScript.Shell.Run(…, 0, False)` =
  hidden + detached — the same trick as `start-ngrok.vbs`). `python.exe app.py` in
  the foreground works fine for debugging.
- **Port-restart races.** Killing :80/:8000 and immediately rebinding can leave a
  half-open, non-serving socket (a "churning" port). The scripts wait for the port
  to actually release before relaunching; if you restart by hand, pause ~1–2s.
- **`localhost` vs `127.0.0.1`.** `app.py` binds `0.0.0.0` (IPv4). If `localhost`
  resolves to IPv6 `::1` first, the browser can churn; try `http://127.0.0.1/`.
- **Interpreter split.** pymongo etc. must be in the **3.12** the backend runs on —
  having them only in the 3.14 will make generation fail even though the gateway is
  happy.
- **One job at a time-ish.** The backend caps concurrent heavy jobs
  (`MAX_CONCURRENT = 2`); uploads are sandboxed under `uploads/<id>/`.
- **`/` must serve `index.html`, not `dos.html`.** `dos.html` is a stale stub that
  redirects to `/`; if `app.py` serves it at `/` you get an infinite redirect loop.
  The gateway is set to serve `index.html` (the boot screen) at `/`.

## Startup order at boot (optional, for persistence)

The background launch above lasts until reboot. For survive-a-reboot, register
scheduled tasks: point/extend `PortfolioApp` (or a new task) at `start-gateway.vbs`
for the gateway, and run `install-storywriter-task.ps1` to register
`PortfolioStoryWriter` for the backend — or one logon task that just runs
`start-storywriter-stack.ps1`.
