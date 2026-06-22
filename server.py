r"""
server.py — local backend for StoryWriter, hardened for tunnelled/external access.

  python server.py                         # binds 127.0.0.1:8000 (gateway proxies to it)

Pipeline per job:
  upload audio -> extract_arcs_hpss.py (pure-NumPy audio analysis via bounded ffmpeg)
              -> audio-feature series for the graph
              -> story_generator.py  (the model infers an emotional arc from the audio —
                 a POINTS array of valence/arousal/dominance waypoints — then WRITES a
                 coherent short story tracing that arc, in a single drafting pass)

story_generator.py speaks newline-delimited JSON events on its stdout; we translate
those into the job state that /status serves:
  status      -> message          reasoning -> reasoning (MAPPING/SHAPE)
  lookup      -> words[] (seeds)   story     -> partial (the streaming prose)
  story_reset -> clears partial    error     -> error
  final       -> done

Safe-for-tunnel: uploads land in ./uploads/<id>/input.<ext> (never the code dir),
extension allowlist + size cap, a concurrency cap, and each job runs cwd=its own dir.

Put access control at the tunnel:  ngrok http --basic-auth "user:pass" 8000
(optionally set STORYWRITER_TOKEN to require an X-Token header — off by default).

API:
  POST /upload   raw audio body, header X-Filename   -> {upload_id, name}
  POST /process  JSON {upload_id, author, words, model, prompt} -> {job_id}
  GET  /status?id=<job_id>                            -> {state, message, partial, words, audio, story|error}
"""
import os, sys, json, uuid, threading, subprocess, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
UPLOAD_ROOT = os.path.join(HERE, "uploads")
PORT = 8765
PY = sys.executable
# On Windows, keep child processes (extractor, generator, their ffmpeg) windowless.
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0

ALLOWED_EXT = {".mp3", ".wav", ".flac", ".ogg", ".m4a"}
MAX_UPLOAD = 40 * 1024 * 1024        # 40 MB
MAX_CONCURRENT = 16                  # effectively unblocked for single-user/demo use
TOKEN = os.environ.get("STORYWRITER_TOKEN")  # if set, require X-Token header

# ── persistence: each finished run is saved to MongoDB (same server as the lexicon) ──
MONGO_URI    = os.environ.get("STORYWRITER_MONGO_URI",    "mongodb://localhost:27017")
MONGO_DB     = os.environ.get("STORYWRITER_MONGO_DB",     "DataDrivenStory")
STORIES_COLL = os.environ.get("STORYWRITER_STORIES_COLL", "GeneratedStories")

def save_story(story, reasoning, mp3_path, source_name,
               audio=None, words=None, library_file=None):
    """Persist a finished run — the story prose, the model's MAPPING/SHAPE reasoning, the
    mapping it was built from (the graph arcs + lexicon seeds), and the source song — to
    MongoDB, so a pre-baked run can be replayed instantly with zero model latency.

    Library (catalog) songs live on disk under Songs/ and are served from there, so we do
    NOT duplicate their audio into GridFS; we just key the result by `library_file`, one
    canonical doc per song (re-baking replaces it). Uploaded songs have no on-disk home, so
    those we stash in GridFS. Best-effort: any failure is logged and swallowed so it can
    never break a job that already finished successfully."""
    if not story:
        return
    try:
        from pymongo import MongoClient
        import gridfs, datetime
        cli = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
        db  = cli[MONGO_DB]
        song_id = None
        if not library_file:                      # uploads: keep the bytes; library: on disk
            try:
                with open(mp3_path, "rb") as fh:
                    song_id = gridfs.GridFS(db, collection="songs").put(
                        fh, filename=source_name, contentType="audio/mpeg")
            except Exception as e:
                print("[persist] song save skipped:", e, file=sys.stderr)
        doc = {
            "story":           story,
            "reasoning":       reasoning or "",
            "audio":           audio or {},        # the graph arcs (audio_series) — the mapping
            "words":           words or [],        # the lexicon seeds / gutter pins
            "source_filename": source_name,
            "library_file":    library_file,       # set for catalog songs; None for uploads
            "song_file_id":    song_id,            # GridFS id of the mp3 (uploads only)
            "created_at":      datetime.datetime.now(datetime.timezone.utc),
        }
        if library_file:                          # one canonical pre-baked result per song
            db[STORIES_COLL].replace_one({"library_file": library_file}, doc, upsert=True)
        else:
            db[STORIES_COLL].insert_one(doc)
        cli.close()
        print(f"[persist] saved story to {MONGO_DB}.{STORIES_COLL}"
              + (f" (library: {library_file})" if library_file else ""), file=sys.stderr)
    except Exception as e:
        print("[persist] story save skipped:", e, file=sys.stderr)


SONGS_DIR    = os.path.join(HERE, "Songs")
CATALOG_PATH = os.path.join(HERE, "songs_catalog.json")

def load_catalog():
    """The editable song library (genres + songs). Returns an empty shell if absent."""
    try:
        with open(CATALOG_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"genres": [], "songs": []}

def prebaked_files():
    """Set of catalog filenames that already have a stored result — for the UI 'ready' badge."""
    try:
        from pymongo import MongoClient
        cli = MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000)
        files = cli[MONGO_DB][STORIES_COLL].distinct("library_file")
        cli.close()
        return set(f for f in files if f)
    except Exception:
        return set()

def load_result(library_file):
    """Fetch a pre-baked run (story + reasoning + mapping) for a catalog song, or None."""
    library_file = (library_file or "").strip()
    if not library_file:
        return None
    try:
        from pymongo import MongoClient
        cli = MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000)
        doc = cli[MONGO_DB][STORIES_COLL].find_one(
            {"library_file": library_file}, sort=[("created_at", -1)])
        cli.close()
        if not doc:
            return None
        return {"found": True, "story": doc.get("story", ""),
                "reasoning": doc.get("reasoning", ""),
                "audio": doc.get("audio") or {}, "words": doc.get("words") or []}
    except Exception:
        return None

JOBS, LOCK = {}, threading.Lock()
RUNNING = 0
def set_job(jid, **kw):
    with LOCK: JOBS.setdefault(jid, {}).update(kw)
def get_job(jid):
    with LOCK: return dict(JOBS.get(jid, {}))


# The seven core arcs surfaced in the left-hand "what the machine heard" graph,
# mapped to the short keys the UI traces use. (The extractor produces more
# features still — those richer arcs feed the model, not this graph.)
GRAPH_COLS = (
    ("energy",     "energy"),      # loudness
    ("centroid",   "bright"),      # brightness
    ("onset",      "onset"),       # overall attack rate
    ("perc_onset", "perc"),        # percussive / rhythmic drive
    ("harm_flux",  "harm"),        # harmonic movement
    ("melody_f0",  "melody"),      # lead-voice pitch
    ("contrast",   "contrast"),    # spectral clarity
)

def audio_series(arcs_csv, n=64):
    """Downsample the seven core audio-analysis features from the arcs CSV to ~n
    points each, normalised to a 1–9 range, for the left-hand graph."""
    import csv as _csv
    raw = {src: [] for src, _ in GRAPH_COLS}
    with open(arcs_csv, newline="") as f:
        for row in _csv.DictReader(f):
            for src, _ in GRAPH_COLS:
                try: raw[src].append(float(row[src]))
                except (KeyError, ValueError, TypeError): pass
    def shape(vals):
        if not vals: return []
        m, out = len(vals), []
        for i in range(n):
            a = i * m // n; b = max(a + 1, (i + 1) * m // n)
            chunk = vals[a:b]
            out.append(sum(chunk) / len(chunk))
        lo, hi = min(out), max(out); rng = (hi - lo) or 1.0
        return [round(1 + (x - lo) / rng * 8, 3) for x in out]
    return {key: shape(raw[src]) for src, key in GRAPH_COLS}


def run_pipeline(jid, jobdir, mp3_path, author, words, model, prompt_file,
                 library_file=None):
    global RUNNING
    arcs = os.path.join(jobdir, "input_arcs.csv")
    stage = "extracting"
    try:
        set_job(jid, state="extracting", failed_stage=None, partial="", reasoning="",
                audio=None, words=[],
                message="Reading the waveform — separating layers, extracting arcs.")
        ep = subprocess.Popen([PY, os.path.join(HERE, "extract_arcs_hpss.py"), mp3_path],
                              cwd=jobdir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              text=True, bufsize=1, creationflags=_NO_WINDOW)
        ext_log = []
        for line in ep.stdout:                     # the extractor narrates its stages on stderr
            line = line.strip()
            if not line:
                continue
            ext_log.append(line)
            if line.startswith("[extract]"):        # surface each stage as live status
                set_job(jid, message=line[len("[extract]"):].strip().capitalize())
        ep.wait()
        if ep.returncode != 0 or not os.path.exists(arcs):
            raise RuntimeError("Extractor failed:\n" + "\n".join(ext_log)[-1500:])
        try: set_job(jid, audio=audio_series(arcs))
        except Exception: pass

        stage = "generating"
        set_job(jid, state="generating",
                message="Inferring the shape of a story from the audio.")
        cmd = [PY, os.path.join(HERE, "story_generator.py"), arcs,
               "--author", author, "--words", str(words), "--model", model,
               "--log", os.path.join(jobdir, "run_log.jsonl")]
        if prompt_file: cmd += ["--prompt-file", prompt_file]

        # The generator speaks newline-delimited JSON events on stdout. Translate
        # each into job state so /status streams progress to the browser.
        proc = subprocess.Popen(cmd, cwd=jobdir, text=True, bufsize=1,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                creationflags=_NO_WINDOW)
        story_buf, reason_buf, words_list, gen_err = [], [], [], None
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            t = ev.get("type")
            if t == "story":
                story_buf.append(ev.get("text", "")); set_job(jid, partial="".join(story_buf))
            elif t == "story_reset":                 # a new prose pass begins — clear the pane
                story_buf.clear(); set_job(jid, partial="")
            elif t == "reasoning":
                reason_buf.append(ev.get("text", "")); set_job(jid, reasoning="".join(reason_buf))
            elif t == "lookup":
                words_list.append({"w": ev.get("w", ""), "v": ev.get("v"),
                                   "a": ev.get("a"), "d": ev.get("d")})
                set_job(jid, words=list(words_list))
            elif t == "status":
                set_job(jid, message=ev.get("msg", ""))
            elif t == "error":
                gen_err = ev.get("msg", "generation error")
            # "final" needs no action — completion is handled below
        proc.wait()
        if gen_err:
            raise RuntimeError(gen_err)
        if proc.returncode != 0:
            raise RuntimeError("Generator failed:\n" + (proc.stderr.read() or "")[-1500:])

        story = "".join(story_buf).strip()
        set_job(jid, state="done", message="Done.", story=story, partial=story)
        # Persist the finished run (story + reasoning + mapping + source song) to MongoDB.
        reasoning = "".join(reason_buf).strip()
        if library_file:
            src_name = library_file
        else:
            src_name = os.path.basename(mp3_path)
            try:
                snp = os.path.join(jobdir, "source_name.txt")
                if os.path.exists(snp):
                    src_name = open(snp, encoding="utf-8").read().strip() or src_name
            except Exception:
                pass
        save_story(story, reasoning, mp3_path, src_name,
                   audio=get_job(jid).get("audio"), words=words_list,
                   library_file=library_file)
    except Exception as e:
        set_job(jid, state="error", failed_stage=stage,
                message="The run stopped.", error=str(e))
    finally:
        with LOCK: RUNNING -= 1


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body):
        if isinstance(body, (dict, list)): body = json.dumps(body).encode()
        elif isinstance(body, str): body = body.encode()
        ctype = "text/html; charset=utf-8" if isinstance(body, bytes) and body[:9]==b"<!doctype" else "application/json"
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store, must-revalidate")  # never serve a stale UI
        self.end_headers()
        self.wfile.write(body)

    def _authed(self):
        return (TOKEN is None) or (self.headers.get("X-Token") == TOKEN)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        if u.path in ("/", "/index.html"):
            with open(os.path.join(HERE, "index.html"), "rb") as f:
                return self._send(200, f.read())
        if u.path == "/status":
            jid = urllib.parse.parse_qs(u.query).get("id", [""])[0]
            return self._send(200, get_job(jid) or {"state": "unknown"})
        if u.path == "/prompts.txt":     # the editable default prompt, prefilled in the UI
            p = os.path.join(HERE, "prompts.txt")
            body = open(p, "rb").read() if os.path.exists(p) else b""
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if u.path == "/library":          # the genre-tabbed song catalog, with 'ready' flags
            cat = load_catalog()
            ready = prebaked_files()
            songs = [{**s, "ready": s.get("file") in ready} for s in cat.get("songs", [])]
            return self._send(200, {"genres": cat.get("genres", []), "songs": songs})
        if u.path == "/result":           # a pre-baked run for a catalog song (instant replay)
            fn = urllib.parse.parse_qs(u.query).get("file", [""])[0]
            return self._send(200, load_result(urllib.parse.unquote(fn)) or {"found": False})
        if u.path == "/song":             # stream a catalog mp3 from Songs/ (with Range support)
            fn = urllib.parse.parse_qs(u.query).get("file", [""])[0]
            return self._serve_song(urllib.parse.unquote(fn))
        self._send(404, {"error": "Not found."})

    def _serve_song(self, fn):
        """Serve a catalog mp3 from Songs/ (basename-only, no traversal) with single-range
        support so the browser audio element can seek."""
        fn = os.path.basename(fn or "")
        path = os.path.join(SONGS_DIR, fn)
        if not fn or not os.path.isfile(path):
            return self._send(404, {"error": "Song not found."})
        size = os.path.getsize(path)
        rng = self.headers.get("Range", "")
        if rng.startswith("bytes="):
            try:
                s, _, e = rng[len("bytes="):].partition("-")
                start = int(s) if s else 0
                end   = int(e) if e else size - 1
                start = max(0, start); end = min(end, size - 1)
                length = end - start + 1
                with open(path, "rb") as f:
                    f.seek(start); chunk = f.read(length)
                self.send_response(206)
                self.send_header("Content-Type", "audio/mpeg")
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, size))
                self.send_header("Content-Length", str(length))
                self.end_headers()
                self.wfile.write(chunk)
                return
            except Exception:
                pass
        with open(path, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", "audio/mpeg")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(size))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        global RUNNING
        u = urllib.parse.urlparse(self.path)
        if not self._authed():
            return self._send(401, {"error": "Not authorized."})

        if u.path == "/upload":
            ext = os.path.splitext(urllib.parse.unquote(self.headers.get("X-Filename","")))[1].lower()
            name = os.path.basename(urllib.parse.unquote(self.headers.get("X-Filename","audio")))
            if ext not in ALLOWED_EXT:
                return self._send(400, {"error": "Unsupported file type. Use: " + ", ".join(sorted(ALLOWED_EXT))})
            size = int(self.headers.get("Content-Length", 0))
            if size <= 0 or size > MAX_UPLOAD:
                return self._send(413, {"error": "File too large or empty (max %d MB)." % (MAX_UPLOAD//1048576)})
            uid = uuid.uuid4().hex
            jobdir = os.path.join(UPLOAD_ROOT, uid)
            os.makedirs(jobdir, exist_ok=True)
            with open(os.path.join(jobdir, "input"+ext), "wb") as f:  # fixed safe name
                f.write(self.rfile.read(size))
            try:                                  # keep the original song name for persistence
                with open(os.path.join(jobdir, "source_name.txt"), "w", encoding="utf-8") as nf:
                    nf.write(name)
            except Exception:
                pass
            return self._send(200, {"upload_id": uid, "name": name})

        if u.path == "/process":
            size = int(self.headers.get("Content-Length", 0))
            try: data = json.loads(self.rfile.read(size) or b"{}")
            except json.JSONDecodeError: return self._send(400, {"error": "Bad JSON."})
            library_file = None
            lf = os.path.basename(str(data.get("library_file", "")))  # no traversal
            if lf:
                src = os.path.join(SONGS_DIR, lf)
                if not os.path.isfile(src):
                    return self._send(400, {"error": "Unknown library song."})
                library_file = lf
                uid = uuid.uuid4().hex
                jobdir = os.path.join(UPLOAD_ROOT, uid)
                os.makedirs(jobdir, exist_ok=True)
                import shutil
                mp3 = os.path.join(jobdir, "input" + os.path.splitext(lf)[1].lower())
                shutil.copyfile(src, mp3)
            else:
                uid = os.path.basename(str(data.get("upload_id","")))  # no traversal
                jobdir = os.path.join(UPLOAD_ROOT, uid)
                if not uid or not os.path.isdir(jobdir):
                    return self._send(400, {"error": "Upload an audio file first."})
                mp3 = next((os.path.join(jobdir, f) for f in os.listdir(jobdir)
                            if f.startswith("input")), None)
                if not mp3:
                    return self._send(400, {"error": "Uploaded file is missing."})
            with LOCK:
                if RUNNING >= MAX_CONCURRENT:
                    return self._send(429, {"error": "Server busy - a story is already being made. Try again shortly."})
                RUNNING += 1
            author = (data.get("author") or "").strip()[:120]   # style now comes from the openings
            model  = (data.get("model")  or "qwen2.5:7b").strip()[:80]
            try: words = max(100, min(750, int(data.get("words", 750))))
            except (TypeError, ValueError): words = 750
            prompt_file = None
            if (data.get("prompt") or "").strip():
                prompt_file = os.path.join(jobdir, "prompt.txt")
                with open(prompt_file, "w", encoding="utf-8") as f:
                    f.write(str(data["prompt"])[:8000])
            jid = uuid.uuid4().hex
            set_job(jid, state="queued", message="Queued.", partial="", reasoning="",
                    failed_stage=None, audio=None, words=[])
            threading.Thread(target=run_pipeline,
                             args=(jid, jobdir, mp3, author, words, model, prompt_file),
                             kwargs={"library_file": library_file},
                             daemon=True).start()
            return self._send(200, {"job_id": jid})

        self._send(404, {"error": "Not found."})

    def log_message(self, *a): pass

if __name__ == "__main__":
    os.makedirs(UPLOAD_ROOT, exist_ok=True)
    if TOKEN: print("token auth: ON (X-Token required)")
    print(f"serving http://127.0.0.1:{PORT}  (Ctrl-C to stop)")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
