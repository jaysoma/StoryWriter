#!/usr/bin/env python3
r"""
story_generator.py — StoryWriter's brain.  The MODEL drives.

Given the audio-analysis arcs for one track, a local Ollama model:

  1. INFERS the shape of a STORY from the audio's *structure* — not a one-dimensional
     "loud = happy" mapping, but multiple characters and intersecting arcs read from
     the layers, contrasts, peaks and crossings in the sound.
  2. Outputs a POINTS line: a JSON array of 5-9 emotional waypoints (valence/arousal/
     dominance on a 1-9 scale) for how the piece FEELS, moment to moment. Each waypoint
     becomes a SEED on the emotional arc.
  3. WRITES a coherent short story that traces that arc — a dark, dystopian sci-fi piece
     ending on an unsettling reveal — in a single drafting pass. Style exemplars (opening
     pages) are pulled from MongoDB when available; the audio->arc link comes from the
     model reading the audio, not from any word/phrase lexicon.

Round trip:  Python  <->  Ollama   (MongoDB optional — only for opening-page exemplars).

Emits newline-delimited JSON events on STDOUT so a parent (server.py) can render
progress live:

  {"type":"status","msg":...}                       phase update
  {"type":"reasoning","text":...}                   MAPPING / SHAPE thinking (pre-STORY)
  {"type":"lookup","w":..,"v":..,"a":..,"d":..}      one emotional-arc waypoint (a dot/seed)
  {"type":"story_reset"}                            clear the prose pane (a new pass begins)
  {"type":"story","text":...}                       STORY prose delta
  {"type":"final","lookups":M}                       done
  {"type":"error","msg":...}                         failure

Human-readable debug goes to STDERR.  Optional --log writes the dashboard JSONL.

CLI (kept compatible with server.py):
  python story_generator.py <arcs_csv> --words 700 \
      --model llama3.2:3b [--prompt-file f] [--log run_log.jsonl]

Requires: an Ollama server running a capable model (qwen2.5, llama3.1/3.2, …).
pymongo + MongoDB are optional — used only for opening-page style exemplars.
"""
import sys, os, csv, json, math, random, argparse, time, re, urllib.request, urllib.error

try:
    from pymongo import MongoClient
except ImportError:
    MongoClient = None   # MongoDB is optional now — only powers opening-page exemplars

MONGO_URI   = os.environ.get("STORYWRITER_MONGO_URI",  "mongodb://localhost:27017/")
OPENINGS_DB   = os.environ.get("STORYWRITER_OPENINGS_DB",   "StoryWriterCorpus")
OPENINGS_COLL = os.environ.get("STORYWRITER_OPENINGS_COLL", "Openings")
OLLAMA_URL  = os.environ.get("STORYWRITER_OLLAMA",     "http://localhost:11434")


# ── tiny output helpers ──────────────────────────────────────────────────────
def emit(ev):
    sys.stdout.write(json.dumps(ev) + "\n")
    sys.stdout.flush()

def dbg(*a):
    print(*a, file=sys.stderr)
    sys.stderr.flush()


# ── audio arcs → a compact, audio-AWARE summary the model reasons over ───────
def is_number(s):
    try:
        float(s); return True
    except (TypeError, ValueError):
        return False

def load_arcs(path):
    rows = list(csv.DictReader(open(path, encoding="utf-8-sig", newline="")))
    if not rows:
        emit({"type": "error", "msg": f"No rows in {path}"}); sys.exit(1)
    return rows

def column(rows, name):
    return [float(r[name]) for r in rows if is_number(r.get(name, ""))]

def _norm(xs):
    if not xs:
        return xs
    lo, hi = min(xs), max(xs); rng = (hi - lo) or 1.0
    return [(x - lo) / rng for x in xs]

def audio_summary(rows, win_s=0.5):
    """Describe the track to the model: per-feature trend PLUS structural events
    (which layer leads and where they cross, where energy peaks/troughs). The
    structural notes are what push the model toward multiple characters and
    intersecting arcs instead of one rising-and-falling line."""
    headers = [h for h in rows[0].keys() if h != "time_s"]
    n = len(rows)
    out = [f"AUDIO ANALYSIS of one piece of music — {n} time-windows (~{n*win_s:.0f}s long).",
           "Each row is a moment in time; the columns are orthogonal acoustic features:",
           "  energy=loudness, centroid=brightness, onset=overall attack rate,",
           "  perc_onset=percussive/rhythmic drive, harm_flux=harmonic movement,",
           "  melody_f0=lead-voice pitch, contrast=spectral space/clarity.",
           "",
           "Per-feature trend (first -> last, and range):"]
    for h in headers:
        xs = column(rows, h)
        if len(xs) >= 0.5 * n:
            out.append(f"  {h}: {xs[0]:.3g} -> {xs[-1]:.3g}   (min {min(xs):.3g}, max {max(xs):.3g})")

    # Structural events: which layer dominates, and where dominance flips (crossings).
    events = []
    perc, harm = _norm(column(rows, "perc_onset")), _norm(column(rows, "harm_flux"))
    if perc and harm and len(perc) == len(harm):
        prev = None
        for i in range(len(perc)):
            dom = "percussive/rhythmic" if perc[i] >= harm[i] else "harmonic/melodic"
            if dom != prev:
                events.append(f"  t~{i*win_s:.0f}s: the {dom} layer takes the lead")
                prev = dom
    en = _norm(column(rows, "energy"))
    if en:
        pk = max(range(len(en)), key=lambda i: en[i]) * win_s
        tr = min(range(len(en)), key=lambda i: en[i]) * win_s
        events.append(f"  energy peaks around t~{pk:.0f}s and bottoms out around t~{tr:.0f}s")
    if events:
        out += ["",
                "STRUCTURAL EVENTS (read these as entrances, exits, and the moments two",
                "different voices cross — the raw material for separate characters and arcs):"]
        out += events[:14]

    # A few evenly-spaced raw rows so the model can see the actual shape.
    idxs = sorted(set(round(i * (n - 1) / (min(16, n) - 1)) for i in range(min(16, n)))) if n > 1 else [0]
    out += ["", f"Sampled rows ({len(idxs)} of {n}):", ",".join(["time_s"] + headers)]
    out += [",".join([rows[i].get("time_s", "")] + [rows[i].get(h, "") for h in headers]) for i in idxs]
    return "\n".join(out)


# ── Ollama /api/chat with token streaming ────────────────────────────────────
def ollama_chat(messages, model, base_url, tools=None, timeout=1800,
                stream=True, on_delta=None, options=None, keep_alive="30m"):
    # keep_alive holds the model resident between the several calls one story makes,
    # so CPU-only boxes don't pay the multi-GB reload each turn. options caps runaway
    # generation (num_predict) so a rambling model can't balloon the wall-clock time.
    body = {"model": model, "messages": messages, "stream": bool(stream),
            "keep_alive": keep_alive}
    if tools:
        body["tools"] = tools
    if options:
        body["options"] = options
    req = urllib.request.Request(base_url.rstrip("/") + "/api/chat",
                                 data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        detail = ""
        try: detail = e.read().decode("utf-8", "replace")
        except Exception: pass
        if e.code == 404 or "not found" in detail.lower():
            raise RuntimeError(f"Ollama has no model '{model}'. Pull it (ollama pull {model}) "
                               f"or pick a tag from `ollama list`. [{detail[:200]}]")
        raise RuntimeError(f"Ollama HTTP {e.code} for model '{model}': {detail[:200]}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Cannot reach Ollama at {base_url} ({e.reason}). Is it running?")
    with resp:
        if not stream:
            return json.loads(resp.read())["message"]
        parts, tool_calls, role = [], [], "assistant"
        for raw in resp:                              # newline-delimited JSON chunks
            raw = raw.strip()
            if not raw:
                continue
            msg = (json.loads(raw).get("message") or {})
            role = msg.get("role") or role
            piece = msg.get("content") or ""
            if piece:
                parts.append(piece)
                if on_delta:
                    on_delta(piece)
            if msg.get("tool_calls"):
                tool_calls.extend(msg["tool_calls"])
        out = {"role": role, "content": "".join(parts)}
        if tool_calls:
            out["tool_calls"] = tool_calls
        return out


# ── splits the streamed prose into pre-STORY reasoning vs the STORY itself ───
# Process narration that should never reach the UI. Small models sometimes print a
# stray plan or label; any line matching this is dropped. Kept tight so it can't eat
# normal prose.
META_LINE = re.compile(
    r"(?i)(chosen arbitrarily|were not provided|emotionally[- ]charged word)")

class SectionRouter:
    """The model is asked to print MAPPING, then SHAPE, then a 'STORY' heading,
    then the prose. We stream everything before the STORY heading as 'reasoning'
    and everything after as 'story', without ever emitting the heading line.

    Works line by line so it can also (a) drop fenced ``` code blocks entirely and
    (b) drop process/tool-narration lines (META_LINE) — so a printed plan or a
    fake tool call never shows up in the UI."""
    HEADING = re.compile(r"(?i)^\s*#{0,6}\s*STORY\b.*$")
    FENCE   = re.compile(r"^\s*```")
    # A bare section heading re-emitted mid-story (e.g. a model that restarts its
    # output) — drop it so it can't pollute the prose pane.
    SECTION = re.compile(r"(?i)^\s*#{0,6}\s*(mapping|shape|story)\b[\s:.\-]*$")

    def __init__(self):
        self.in_story = False
        self.in_fence = False
        self.buf = ""
        self.any_story = False

    def feed(self, piece):
        self.buf += piece
        while "\n" in self.buf:                  # emit only complete lines
            line, self.buf = self.buf.split("\n", 1)
            self._line(line + "\n")

    def _line(self, line):
        if self.FENCE.match(line):               # ``` toggles a code fence
            self.in_fence = not self.in_fence
            return
        if self.in_fence:                        # body of a fence — drop it
            return
        if not self.in_story:
            m = self.HEADING.search(line)
            if m:
                before, after = line[:m.start()], line[m.end():]
                if before.strip() and not META_LINE.search(before):
                    emit({"type": "reasoning", "text": before})
                self.in_story = True
                if after.strip() and not META_LINE.search(after):
                    self.any_story = True
                    emit({"type": "story", "text": after})
                return
            if line.strip() and not META_LINE.search(line):
                emit({"type": "reasoning", "text": line})
            return
        if META_LINE.search(line):               # stray narration inside STORY
            return
        if self.SECTION.match(line):             # re-emitted MAPPING/SHAPE/STORY heading
            return
        self.any_story = True
        emit({"type": "story", "text": line})

    def flush(self):
        if self.buf.strip():                     # trailing partial (no newline)
            self._line(self.buf if self.buf.endswith("\n") else self.buf + "\n")
        self.buf = ""


# ── recover tool calls a model printed as TEXT instead of using the tool channel ─
def _json_objects(text):
    """Yield top-level {...} substrings (brace-balanced) from text."""
    depth, start, out = 0, None, []
    for i, c in enumerate(text):
        if c == "{":
            if depth == 0:
                start = i
            depth += 1
        elif c == "}" and depth > 0:
            depth -= 1
            if depth == 0 and start is not None:
                out.append(text[start:i + 1]); start = None
    return out

def collect_points(obj, _depth=0):
    """Recursively pull every {valence, arousal, ...} point out of WHATEVER shape a
    model crammed into its POINTS output — a real array, a single object, points nested
    under any key, or a JSON-encoded string at any level. This is what makes parsing
    robust to the wildly varying output formats local models emit."""
    if _depth > 6:
        return []
    if isinstance(obj, str):
        try: obj = json.loads(obj)
        except (ValueError, TypeError): return []
    found = []
    if isinstance(obj, dict):
        if "valence" in obj and "arousal" in obj:
            found.append(obj)
        else:
            for v in obj.values():
                found += collect_points(v, _depth + 1)
    elif isinstance(obj, list):
        for it in obj:
            found += collect_points(it, _depth + 1)
    return found


def fallback_points(rows, k=6):
    """Safety net: derive a few VAD points straight from the audio when the model
    fails to supply usable ones (e.g. it echoes the raw feature numbers instead of
    choosing 1-9 emotion ratings). Deliberately simple — energy→arousal,
    brightness→valence, spectral contrast→dominance — and used ONLY as a last resort
    so the lexicon is never empty; the model-driven path is always preferred."""
    en = _norm(column(rows, "energy"))
    br = _norm(column(rows, "centroid"))
    ct = _norm(column(rows, "contrast"))
    n = max(len(en), len(br), len(ct))
    if n == 0:
        return []
    at = lambda xs, i: xs[i] if i < len(xs) else 0.5
    pts = []
    for j in range(max(1, k)):
        i = round(j * (n - 1) / max(1, k - 1))
        pts.append({"valence":   round(1 + 8 * at(br, i), 2),
                    "arousal":   round(1 + 8 * at(en, i), 2),
                    "dominance": round(1 + 8 * at(ct, i), 2)})
    return pts


def build_system(author, words, extra):
    sys_t = (
        "You are StoryWriter's inference core. You read the analysis of a piece of music "
        "and infer the SEQUENCE OF EMOTIONAL STATES it moves through. You write NO prose of "
        "your own.\n\n"
        "Work in this exact order, and output ONLY these sections:\n"
        "1. MAPPING — in 2-4 sentences under a heading 'MAPPING', read the shape: its "
        "layers, contrasts, peaks and crossings, and the sequence of feelings they trace. "
        "Read it richly, never one-dimensionally (not loud=happy).\n"
        "2. SHAPE — under a heading 'SHAPE', list the waypoints in order (the turning "
        "points the piece moves through, each tied to a moment in it). A few lines.\n"
        "3. POINTS — on a final line beginning 'POINTS:', output a JSON array of 5 to 9 "
        "emotion waypoints in order, each {\"valence\":n,\"arousal\":n,\"dominance\":n} on a "
        "1-9 scale for how that moment FEELS (emotions you invent, NEVER the analysis "
        'numbers). Example: POINTS: [{"valence":6,"arousal":4,"dominance":5},'
        '{"valence":2,"arousal":8,"dominance":3}]. Write nothing after the POINTS line.'
    )
    if extra and extra.strip():
        sys_t += "\n\nADDITIONAL DIRECTION:\n" + extra.strip()
    return sys_t


# ── turn the inferred waypoints (the SEEDS) into material for a real story ────
def vad_feeling(v, a):
    """Plain-language label for a valence/arousal point, so the writer model reads
    'weary, melancholy -> restless, alert' instead of bare numbers. Mirrors the same
    3x3 grid the UI header uses, for one consistent emotional vocabulary."""
    grid = [
        ["weary, melancholy",      "uneasy, somber",    "anxious, afraid"],
        ["subdued, contemplative", "pensive, watchful", "restless, alert"],
        ["calm, content",          "warm, hopeful",     "elated, exhilarated"],
    ]
    lo, hi = 4.2, 5.8
    vb = 0 if v < lo else (2 if v > hi else 1)
    ab = 0 if a < lo else (2 if a > hi else 1)
    return grid[vb][ab]

_WRITER_SYSTEM_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "writer_system.txt")
_WRITER_SYSTEM_DEFAULT = (
    "You are a literary science-fiction writer. EVERY story you write here is a DARK, "
    "DYSTOPIAN SCIENCE-FICTION story in the spirit of Black Mirror, and it ALWAYS ends on an "
    "UNSETTLING REVEAL. That genre and that ending are FIXED — they OVERRIDE every other "
    "instruction below. Never write a cozy, warm, or reassuring story, and never resolve the "
    "unease away with a happy or comforting ending.\n\n"
    "THE WORLD: a recognizable near-future in which artificial intelligence has been woven "
    "into ordinary daily life in some unexpected, barely-questioned way. The main character "
    "begins noticing ODD, uncanny things because of it — small wrongnesses in routine moments "
    "that don't quite add up. Let the dread build quietly.\n\n"
    "THE ENDING (most important): the story MUST end on a genuinely UNSETTLING REVEAL — the "
    "true, sinister nature or reach of that AI, recasting everything before it. Do NOT explain "
    "the unease away or reassure the reader (a scare that turns out to be a kind neighbour is "
    "exactly what NOT to do). The reveal IS the ending; land it as the final, deliberate beat. "
    "The story must reach it — never trail off mid-scene.\n\n"
    "CRAFT: ONE complete, self-contained short story — narrative fiction told in scenes, one "
    "main character, concrete action, a clear through-line, natural contemporary English. "
    "Write flowing prose ONLY — no titles, headings, numbered sections, **bold** labels, or "
    "stage-directions like 'External Event' or 'Interruption.' Never mention music, sound, "
    "rhythm, or any 'analysis.'\n\n"
    "THE EMOTIONAL ARC you are given is ONLY a mood contour to pass through — it NEVER changes "
    "the genre or the dark ending. A 'warm' or 'hopeful' beat is hope inside a dystopia, about "
    "to be betrayed by the reveal; render it that way, never as genuine comfort.\n\n"
    "Aim for about {words} words. You MUST finish on a complete sentence ending with "
    "a period — never stop mid-sentence. Output ONLY the story prose."
)
def _load_writer_system():
    try:
        with open(_WRITER_SYSTEM_FILE, encoding="utf-8") as f:
            t = f.read().strip()
            return t if t else _WRITER_SYSTEM_DEFAULT
    except FileNotFoundError:
        return _WRITER_SYSTEM_DEFAULT
WRITER_SYSTEM = _load_writer_system()

def arc_sentence(seeds):
    """The emotional arc as a plain feelings-phrase — no numbers, no list — so the model
    can't transcribe it as section headings or recite the valence/energy values."""
    return " then ".join(vad_feeling(s["v"], s["a"]) for s in seeds)

def writer_user(summary, seeds, author, openings=None):
    """Build the writer's brief. The audio 'reading' is deliberately NOT passed — its music
    jargon ('harmonic layer', 'percussive') was leaking straight into the prose. The writer
    gets only the openings (style), the emotional shape as a sentence, and a free-form
    external-event cue."""
    parts = []
    if openings:
        parts.append("Study these published OPENINGS for craft, voice and density. Do NOT "
                     "reuse their words, names, characters, or plots — only their command "
                     "of language:")
        for o in openings:
            cite = " — ".join(x for x in (o.get("author"), o.get("title")) if x)
            parts.append("\n--- %s ---\n%s" % (cite or "opening", (o.get("text") or "").strip()))
        parts.append("")
    parts += ["EMOTIONAL SHAPE — let the story pass through these feelings in order, each "
              "shift carried by events (never named, numbered, or written as a heading): "
              + arc_sentence(seeds) + ".", ""]
    parts += ["Somewhere the feeling spikes, a sudden EXTERNAL event should intrude from "
              "outside the character — you choose where and what (a downpour, a stranger "
              "speaking, a phone call with news, a knock at the door): an interruption the "
              "character didn't choose.", ""]
    if author:
        parts.append(f"Write with the sensibility of {author}.")
    parts.append("Write the story now — a DARK dystopian story with a sinister AI woven into "
                 "daily life, ending on an UNSETTLING reveal. Not warm, not reassuring.")
    return "\n".join(parts)

def brief_display(openings, seeds):
    """A readable rendering of what we hand the writer, for the Model Reasoning pane:
    opening exemplars as one-line citations, plus the emotional shape."""
    out = []
    if openings:
        out.append("OPENINGS (style only): " + "; ".join(
            (" — ".join(x for x in (o.get("author"), o.get("title")) if x) or "opening")
            for o in openings))
    out.append("ARC: " + arc_sentence(seeds))
    return "\n".join(out)

def load_openings(client):
    """Load style-exemplar opening pages from Mongo (built by build_openings.py).
    Returns [] when none are installed, so the writer falls back to seed imagery."""
    try:
        docs = list(client[OPENINGS_DB][OPENINGS_COLL].find(
            {}, {"author": 1, "title": 1, "text": 1}))
        return [d for d in docs if (d.get("text") or "").strip()]
    except Exception:
        return []

def pick_openings(openings, k=2):
    """A random handful of openings to study this run — unscored, for variety. They
    teach voice/craft only; the audio->arc link comes from the model reading the audio."""
    if not openings:
        return []
    return random.sample(openings, min(k, len(openings)))


# ── stream prose to the UI, dropping any preamble / headings / fences ────────
class ProseRouter:
    """Streams a prose pass as 'story' deltas while suppressing the junk small models
    sometimes prepend — a 'Here is the story:' line, a markdown title, a code fence —
    so only clean prose reaches the pane. Accumulates the emitted text for the caller."""
    META  = re.compile(r"(?i)^\s*(here(?:'s| is)\b|sure[,!.]|certainly\b|okay\b|of course"
                       r"|title\s*:|the (?:revised )?story\b|below is|i hope|let me know"
                       r"|\*\*)")
    HEAD  = re.compile(r"^\s*#{1,6}\s")
    FENCE = re.compile(r"^\s*```")

    def __init__(self, label="Writing"):
        self.buf = ""; self.started = False; self.in_fence = False; self.text = ""
        self.label = label; self._last = 0; self._last_r = 0

    def feed(self, piece):
        self.buf += piece
        while "\n" in self.buf:
            line, self.buf = self.buf.split("\n", 1)
            self._line(line + "\n")

    def _line(self, line):
        if self.FENCE.match(line):
            self.in_fence = not self.in_fence; return
        if self.in_fence:
            return
        if not self.started:                       # still skipping leading junk
            if not line.strip():
                return
            if self.META.match(line) or self.HEAD.match(line):
                return
            self.started = True
        self.text += line
        emit({"type": "story", "text": line})
        w = len(self.text.split())
        if w - self._last >= 10:                    # live word-count in the status bar
            self._last = w
            emit({"type": "status", "msg": "%s — %d words" % (self.label, w)})
        if w - self._last_r >= 50:                  # periodic progress in the Model Reasoning pane
            self._last_r = w
            emit({"type": "reasoning", "text": "  · %d words written…\n" % w})

    def flush(self):
        if self.buf:
            self._line(self.buf if self.buf.endswith("\n") else self.buf + "\n")
            self.buf = ""


class ReasonRouter:
    """Stream the model's MAPPING/SHAPE thinking to the reasoning pane AS IT ARRIVES,
    so the wait before the lookups isn't dead air. Drops code fences, tool-narration
    (META_LINE), and any printed tool-call JSON so only the readable reasoning shows."""
    FENCE   = re.compile(r"^\s*```")
    JSONISH = re.compile(r'^\s*[\[{]|"points"|"valence"|"arousal"')

    def __init__(self):
        self.buf = ""; self.in_fence = False; self.text = ""

    def feed(self, piece):
        self.buf += piece
        while "\n" in self.buf:
            line, self.buf = self.buf.split("\n", 1)
            self._line(line + "\n")

    def _line(self, line):
        if self.FENCE.match(line):
            self.in_fence = not self.in_fence; return
        if self.in_fence or META_LINE.search(line) or self.JSONISH.search(line):
            return
        if line.strip():
            self.text += line                  # keep the cleaned reading to hand to the writer
            emit({"type": "reasoning", "text": line})

    def flush(self):
        if self.buf.strip():
            self._line(self.buf if self.buf.endswith("\n") else self.buf + "\n")
        self.buf = ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("arcs_csv")
    ap.add_argument("--author", default="")   # off by default; style comes from the openings
    ap.add_argument("--words", type=int, default=700)
    ap.add_argument("--model", default="qwen2.5:7b")
    ap.add_argument("--prompt-file", default=None)
    ap.add_argument("--seed", type=int)
    ap.add_argument("--log", default=None)
    args = ap.parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    # Mongo is needed only for the opening exemplars now — the emotional arc comes from the
    # model reading the audio, not a phrase lexicon. Connect, but don't hard-fail if it's down
    # (or if pymongo isn't installed at all).
    client = None
    if MongoClient is not None:
        try:
            client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=4000)
            client.admin.command("ping")
        except Exception as ex:
            dbg("Mongo not reachable (%s) — openings disabled, continuing." % ex)
            client = None

    extra = ""
    if args.prompt_file and os.path.exists(args.prompt_file):
        with open(args.prompt_file, encoding="utf-8") as f:
            extra = f.read()

    rows = load_arcs(args.arcs_csv)
    summary = audio_summary(rows)
    dbg("AUDIO SUMMARY handed to the model:\n" + summary)

    # optional dashboard log
    log_path = args.log
    t0 = time.time()
    def logrec(ev):
        if not log_path:
            return
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"t": round(time.time() - t0, 3), **ev}) + "\n")
        except OSError:
            pass
    if log_path:
        try: open(log_path, "w").close()
        except OSError: pass

    # The structured MAPPING/SHAPE/POINTS machinery lives in the engine's own system
    # prompt; prompts.txt (short, editable in the UI) is folded in as the user's extra
    # direction. Author + length come from the UI fields.
    system = build_system(args.author, args.words, extra)
    # Feed the model the TREND + STRUCTURAL-EVENTS summary only, not the verbose sampled-row
    # CSV dump — it doesn't need the raw rows to read MAPPING/SHAPE, and dropping them cuts
    # the prompt (and the prefill wait) substantially on a CPU box.
    model_summary = summary.split("\nSampled rows")[0].strip()
    user = ("Here is the analysis of one piece of music. Read it, then give MAPPING and "
            "SHAPE, then a POINTS line (a JSON array of the emotional waypoints). Write "
            "nothing after POINTS.\n\n"
            + model_summary)
    messages = [{"role": "system", "content": system},
                {"role": "user", "content": user}]

    emit({"type": "status", "msg": "Inferring the shape of a story from the audio."})
    # Show the analysis the model is about to read, so this phase isn't dead air while the
    # model prefills the (long) prompt — which alone can take a minute on a CPU box. The
    # model's own MAPPING/SHAPE then streams in underneath this if it emits any.
    emit({"type": "reasoning", "text": "WHAT THE MACHINE HEARD\n"
          + summary.split("\nSampled rows")[0].strip() + "\n"})
    # The inference turn only needs MAPPING/SHAPE (a few sentences) + the tool call — it
    # does NOT scale with story length, so cap it tight. A chatty small model could
    # otherwise burn minutes rambling here before it calls the tool. (The prose passes set
    # their own, larger token budgets separately.)
    gen_opts = {"num_predict": 420}
    reason_router = ReasonRouter()       # stream the model's MAPPING/SHAPE thinking live
    pts = []
    for attempt in range(2):
        try:
            msg = ollama_chat(messages, args.model, OLLAMA_URL, tools=None,
                              stream=True, on_delta=reason_router.feed, options=gen_opts)
        except Exception as ex:
            emit({"type": "error", "msg": str(ex)})
            sys.exit(1)
        reason_router.flush()
        messages.append(msg)
        content = msg.get("content") or ""
        for blob in _json_objects(content):          # parse the POINTS array out of the text
            pts += collect_points(blob)
        logrec({"type": "infer_turn", "attempt": attempt,
                "points": len(pts), "content_chars": len(content)})
        if pts:
            break
        if attempt == 0:                              # nudge once if it skipped the POINTS line
            messages.append({"role": "user", "content":
                'Now output ONLY the POINTS line: a JSON array of 5-9 objects, each '
                '{"valence":n,"arousal":n,"dominance":n} on a 1-9 scale, in story order.'})

    if not pts:                                       # nothing usable — read the arc from the audio
        emit({"type": "status", "msg": "Deriving the arc straight from the audio."})
        pts = fallback_points(rows, k=6)

    # ── EMOTIONAL ARC — each waypoint becomes a feeling in the left-pane timeline.
    def clamp19(x):
        try: return max(1.0, min(9.0, float(x)))
        except (TypeError, ValueError): return 5.0
    seeds = []
    for p in pts:
        v, a, d = clamp19(p.get("valence")), clamp19(p.get("arousal")), clamp19(p.get("dominance"))
        feel = vad_feeling(v, a)
        seeds.append({"v": v, "a": a, "d": d})
        emit({"type": "lookup", "w": feel,
              "v": round(v, 2), "a": round(a, 2), "d": round(d, 2)})
        logrec({"type": "arc_point", "feeling": feel, "v": v, "a": a, "d": d})

    # ── THE STORY ────────────────────────────────────────────────────────────
    # The seeds are the emotional map. The model now WRITES an original, coherent short
    # story that traces that arc — in a single drafting pass.
    if not seeds:
        emit({"type": "error", "msg": "No usable seeds were found for this track."})
        sys.exit(1)

    # Generous token headroom so the model can reach a real ending instead of being cut off
    # mid-sentence. It's a ceiling, not a target — the model stops when the story is done.
    prose_predict = int(min(8192, max(2048, args.words * 6)))

    def prose_pass(sys_prompt, user_prompt, status_msg, temp):
        """The streaming writing pass. Clears the pane (story_reset), streams clean prose,
        and returns the full text it emitted."""
        emit({"type": "status", "msg": status_msg})
        emit({"type": "reasoning", "text": "\n▷ " + status_msg + "\n"})
        emit({"type": "story_reset"})
        router = ProseRouter(status_msg.rstrip("."))
        opts = {"num_predict": prose_predict, "temperature": temp,
                "top_p": 0.95 if temp > 0.6 else 0.9}
        try:
            ollama_chat([{"role": "system", "content": sys_prompt},
                         {"role": "user", "content": user_prompt}],
                        args.model, OLLAMA_URL, tools=None, stream=True,
                        on_delta=router.feed, options=opts)
        except Exception as ex:
            emit({"type": "error", "msg": str(ex)}); sys.exit(1)
        router.flush()
        return router.text.strip()

    # Surface the spine the story will follow, so the user sees what the model decided.
    spine = " → ".join(vad_feeling(s["v"], s["a"]).split(",")[0].strip() for s in seeds)
    emit({"type": "reasoning", "text": "\nEMOTIONAL ARC: " + spine + "\n"})

    # Pick one opening exemplar at random (if any are installed) to carry the voice.
    openings = pick_openings(load_openings(client), k=1)
    if openings:
        emit({"type": "status", "msg": "Studying %d opening%s for voice." %
              (len(openings), "" if len(openings) == 1 else "s")})

    w_user = writer_user(summary, seeds, args.author, openings)
    writer_sys = WRITER_SYSTEM.format(words=args.words)
    emit({"type": "reasoning", "text": "\n— BRIEF SENT TO THE WRITER —\n"
          + brief_display(openings, seeds) + "\n"})

    story_text = prose_pass(writer_sys, w_user, "Writing the story.", 0.85)
    emit({"type": "reasoning", "text": "✓ Draft complete — %d words.\n" % len(story_text.split())})

    emit({"type": "status", "msg": "Done."})
    emit({"type": "final", "lookups": len(seeds), "story_chars": len(story_text)})
    logrec({"type": "final", "lookups": len(seeds), "story_chars": len(story_text),
            "elapsed_s": round(time.time() - t0, 2)})


if __name__ == "__main__":
    main()
