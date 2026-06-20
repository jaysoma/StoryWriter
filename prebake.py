r"""
prebake.py - batch-generate stories for the song library and persist them to MongoDB,
so picking a catalog song in the UI is instant (no model wait).

It reuses the REAL pipeline from server.py (extract_arcs_hpss -> story_generator ->
save_story), so generation behaves exactly like a live run and each result is keyed by
its catalog filename (one canonical, re-bakeable doc per song).

Prereqs (same as a live run): Ollama up with a capable model and the 3.12 deps
installed (MongoDB optional, for opening-page exemplars). Run it with the SAME interpreter the
backend uses:

    & "C:\Program Files\Python312\python.exe" prebake.py            # bake every not-yet-baked song
    & "C:\Program Files\Python312\python.exe" prebake.py --genre Rock
    & "C:\Program Files\Python312\python.exe" prebake.py --limit 5
    & "C:\Program Files\Python312\python.exe" prebake.py --only "cher"
    & "C:\Program Files\Python312\python.exe" prebake.py --force      # re-bake even if already stored
    & "C:\Program Files\Python312\python.exe" prebake.py --words 700 --model qwen2.5:7b
    & "C:\Program Files\Python312\python.exe" prebake.py --list       # just show what would be baked

By default it SKIPS songs that already have a stored result, so you can stop and resume.
"""
import os, sys, uuid, time, shutil, argparse

import server  # the real pipeline + persistence helpers (importing does not start the server)

HERE = os.path.dirname(os.path.abspath(__file__))


def parse_args(argv):
    ap = argparse.ArgumentParser(description="Prebake StoryWriter library songs into MongoDB.")
    ap.add_argument("--genre", default=None, help="only this genre (e.g. Rock)")
    ap.add_argument("--only",  default=None, help="substring match on 'title artist'")
    ap.add_argument("--limit", type=int, default=None, help="cap how many to bake this run")
    ap.add_argument("--words", type=int, default=700, help="story length target (default 700)")
    ap.add_argument("--model", default=os.environ.get("STORYWRITER_MODEL", "qwen2.5:7b"),
                    help="Ollama model tag")
    ap.add_argument("--author", default="", help="optional author sensibility")
    ap.add_argument("--force", action="store_true", help="re-bake even if already stored")
    ap.add_argument("--list", action="store_true", help="list the songs that would be baked, then exit")
    return ap.parse_args(argv)


def select(songs, args, already):
    out = []
    for s in songs:
        if args.genre and s.get("genre") != args.genre:
            continue
        if args.only and args.only.lower() not in (s.get("title", "") + " " + s.get("artist", "")).lower():
            continue
        if (not args.force) and s.get("file") in already:
            continue
        out.append(s)
    if args.limit:
        out = out[: args.limit]
    return out


def main(argv):
    args = parse_args(argv)
    cat = server.load_catalog()
    songs = cat.get("songs", [])
    if not songs:
        print("No catalog found (songs_catalog.json). Nothing to do.")
        return 1

    already = set() if args.force else server.prebaked_files()
    todo = select(songs, args, already)

    print("Catalog: %d songs across %s." % (len(songs), ", ".join(cat.get("genres", []))))
    print("Already baked: %d.  To bake this run: %d." % (len(already), len(todo)))
    if args.list or not todo:
        for s in todo:
            print("  - [%s] %s - %s" % (s.get("genre", "?"), s.get("title", ""), s.get("artist", "")))
        if not todo:
            print("Nothing to bake. (Use --force to re-bake.)")
        return 0

    os.makedirs(server.UPLOAD_ROOT, exist_ok=True)
    ok = fail = 0
    t_all = time.time()
    for i, s in enumerate(todo, 1):
        fn = s.get("file", "")
        src = os.path.join(server.SONGS_DIR, fn)
        head = "[%d/%d] %s - %s" % (i, len(todo), s.get("title", ""), s.get("artist", ""))
        if not os.path.isfile(src):
            print(head + "  -> MISSING FILE, skipped"); fail += 1; continue

        jid = uuid.uuid4().hex
        jobdir = os.path.join(server.UPLOAD_ROOT, "prebake_" + jid)
        os.makedirs(jobdir, exist_ok=True)
        mp3 = os.path.join(jobdir, "input" + os.path.splitext(fn)[1].lower())
        try:
            shutil.copyfile(src, mp3)
            print(head + " ...", flush=True)
            t0 = time.time()
            # Synchronous call into the real pipeline; library_file keys + upserts the result.
            server.run_pipeline(jid, jobdir, mp3, args.author, args.words, args.model,
                                 None, library_file=fn)
            st = server.get_job(jid)
            if st.get("state") == "done" and st.get("story"):
                print("      done in %ds (%d chars)" % (int(time.time() - t0), len(st.get("story", ""))))
                ok += 1
            else:
                print("      FAILED: %s" % (st.get("error") or "no story produced")); fail += 1
        except Exception as e:
            print("      ERROR: %s" % e); fail += 1
        finally:
            shutil.rmtree(jobdir, ignore_errors=True)

    print("Done: %d ok, %d failed, %ds total." % (ok, fail, int(time.time() - t_all)))
    return 0 if fail == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
