#!/usr/bin/env python3
"""selftest.py — local sanity check for StoryWriter. Run this after edits, since the
agent's sandbox can't always see your real files.

    python selftest.py            # compile + imports + Mongo/Ollama checks
    python selftest.py --smoke    # ALSO run a real end-to-end generation (needs the stack)

Run it with the SAME interpreter the backend uses (the 3.12 that server.py spawns
children with), e.g.:

    & "C:\\Program Files\\Python312\\python.exe" selftest.py --smoke

Exit code 0 = all hard checks passed. Mongo/Ollama being down are WARNINGS unless
--smoke is given (which needs the full stack)."""
import argparse, glob, json, os, py_compile, shutil, subprocess, sys, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OK, WARN, BAD = "  OK   ", "  WARN ", "  FAIL "
problems = []

def hr(t): print("\n=== %s ===" % t)

def compile_all():
    hr("1. Python syntax (py_compile)")
    bad = 0
    for f in sorted(glob.glob(os.path.join(HERE, "*.py"))):
        try:
            py_compile.compile(f, doraise=True)
            print(OK + os.path.basename(f))
        except py_compile.PyCompileError as e:
            print(BAD + os.path.basename(f) + " -> " + str(e).strip().splitlines()[-1])
            bad += 1
    if bad:
        problems.append("%d file(s) failed to compile" % bad)

def import_check():
    hr("2. Backend imports (interpreter: %s)" % sys.executable)
    for mod in ("pymongo", "numpy"):
        try:
            m = __import__(mod)
            print(OK + "%s %s" % (mod, getattr(m, "__version__", "?")))
        except Exception as e:
            print(BAD + "%s -> %s" % (mod, e))
            problems.append("missing backend dep: %s" % mod)
    exe = shutil.which("ffmpeg")
    if not exe:
        try:
            import imageio_ffmpeg
            exe = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            exe = None
    print((OK if exe else WARN) + "ffmpeg: " + (exe or "NOT FOUND -> pip install imageio-ffmpeg"))
    if not exe:
        problems.append("ffmpeg not found (audio extraction will fail)")

def mongo_check():
    hr("3. MongoDB collections")
    uri = os.environ.get("STORYWRITER_MONGO_URI", "mongodb://localhost:27017/")
    try:
        from pymongo import MongoClient
        cli = MongoClient(uri, serverSelectionTimeoutMS=3000)
        cli.admin.command("ping")
    except Exception as e:
        print(WARN + "Mongo not reachable at %s (%s)" % (uri, e))
        return
    op = cli[os.environ.get("STORYWRITER_OPENINGS_DB", "StoryWriterCorpus")][
        os.environ.get("STORYWRITER_OPENINGS_COLL", "Openings")
    ].estimated_document_count()
    print((OK if op else WARN) + "opening exemplars: %d" % op)
    if not op:
        print("         -> python build_openings.py   (openings are optional, style only)")

def ollama_check(model):
    hr("4. Ollama model")
    base = os.environ.get("STORYWRITER_OLLAMA", "http://localhost:11434")
    try:
        with urllib.request.urlopen(base.rstrip("/") + "/api/tags", timeout=4) as r:
            tags = [m.get("name", "") for m in json.loads(r.read()).get("models", [])]
    except Exception as e:
        print(WARN + "Ollama not reachable at %s (%s)" % (base, e))
        return
    hit = any(t == model or t.split(":")[0] == model.split(":")[0] for t in tags)
    print((OK if hit else WARN) + "model '%s' %s" %
          (model, "present" if hit else "NOT pulled  ->  ollama pull %s" % model))
    if tags:
        print("         installed: " + ", ".join(tags[:8]))

def smoke(model):
    hr("5. End-to-end smoke (single pass)")
    arcs = os.path.join(HERE, "input_arcs.csv")
    if not os.path.exists(arcs):
        print(BAD + "no input_arcs.csv to test on")
        problems.append("smoke: no arcs csv")
        return
    cmd = [sys.executable, os.path.join(HERE, "story_generator.py"), arcs,
           "--model", model, "--words", "140"]
    print("  $ " + " ".join(cmd))
    types, story, err = {}, [], None
    p = subprocess.Popen(cmd, cwd=HERE, stdout=subprocess.PIPE, text=True, bufsize=1)
    for line in p.stdout:
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        t = ev.get("type")
        types[t] = types.get(t, 0) + 1
        if t == "story":
            story.append(ev.get("text", ""))
        elif t == "status":
            print("    .. " + ev.get("msg", ""))
        elif t == "error":
            err = ev.get("msg")
    p.wait()
    print("  events: " + ", ".join("%s=%d" % kv for kv in types.items()))
    if err:
        print(BAD + "generator error: " + err)
        problems.append("smoke: generator error")
        return
    text = "".join(story).strip()
    if types.get("lookup", 0) and text:
        print(OK + "got %d seeds and a %d-char story" % (types.get("lookup", 0), len(text)))
        print("\n--- story ---\n" + text + "\n")
    else:
        print(BAD + "no story produced")
        problems.append("smoke: empty story")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true", help="run a real generation end-to-end")
    ap.add_argument("--model", default=os.environ.get("STORYWRITER_MODEL", "qwen2.5:7b"))
    a = ap.parse_args()
    compile_all()
    import_check()
    mongo_check()
    ollama_check(a.model)
    if a.smoke:
        smoke(a.model)
    hr("summary")
    if problems:
        print("FAILED:\n  - " + "\n  - ".join(problems))
        sys.exit(1)
    print("All hard checks passed." + ("" if a.smoke else "   (add --smoke for a real run)"))

if __name__ == "__main__":
    main()
