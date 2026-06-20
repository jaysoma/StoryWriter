#!/usr/bin/env python3
"""build_openings.py — load a few gripping public-domain OPENING PAGES into MongoDB for
StoryWriter to use as style exemplars.

Each first page is fetched from Project Gutenberg AT RUN TIME and trimmed to its opening,
so no large book text is stored in this file. The pages are written to
StoryWriterCorpus.Openings (one doc per book).

    python build_openings.py            # fetch + upsert
    python build_openings.py --drop     # replace the collection first
    python build_openings.py --list     # show what's already stored (no network/writes)

These are STYLE teachers only: the writer studies their craft and never copies their
words, names, or plots. Stored UNSCORED by design — story_generator.py picks one or two
at random per story; the audio->story link comes from the model reading the audio.

Needs: pymongo, a running mongod, and internet access to gutenberg.org.
"""
import argparse, hashlib, os, re, sys, urllib.request

URI      = os.environ.get("STORYWRITER_MONGO_URI",      "mongodb://localhost:27017/")
OUT_DB   = os.environ.get("STORYWRITER_OPENINGS_DB",    "StoryWriterCorpus")
OUT_COLL = os.environ.get("STORYWRITER_OPENINGS_COLL",  "Openings")
TARGET_WORDS = 430        # roughly a first page

# (author, title, Gutenberg id, a short marker phrase where the story's narrative begins)
# Dark dystopian / sci-fi short stories — public domain — so the style exemplars reinforce
# the Black Mirror tone instead of fighting it.
BOOKS = [
    ("E. M. Forster",       "The Machine Stops",    72890, "hexagonal in shape"),
    ("Ambrose Bierce",      "Moxon's Master",       4366,  "do you really believe that a machine thinks"),
    ("Fitz-James O'Brien",  "The Diamond Lens",     23169, "toward microscopic investigations"),
    ("H. G. Wells",         "The Star",             27365, "the motion of the planet Neptune"),
    ("Charlotte P. Gilman", "The Yellow Wall-Paper", 1952, "secure ancestral halls"),
]

def gut_urls(i):
    return [f"https://www.gutenberg.org/cache/epub/{i}/pg{i}.txt",
            f"https://www.gutenberg.org/files/{i}/{i}-0.txt"]

def fetch(gid):
    last = None
    for url in gut_urls(gid):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "StoryWriter/1.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:
            last = e
    raise RuntimeError(f"could not fetch Gutenberg #{gid}: {last}")

def first_page(raw, marker, target=TARGET_WORDS):
    """From the Gutenberg START marker, find the narrative's first line, then take whole
    paragraphs up to ~target words."""
    m = re.search(r"\*\*\*\s*START OF.*?\*\*\*", raw, re.I | re.S)
    body = raw[m.end():] if m else raw
    # match the marker tolerant of line wraps (Gutenberg hard-wraps at ~70 chars, so a
    # multi-word phrase often has a newline mid-phrase) and of case.
    pat = re.compile(r"\s+".join(re.escape(w) for w in marker.split()), re.I)
    mm = pat.search(body)
    if not mm:
        raise RuntimeError(f"opening marker {marker!r} not found")
    i = mm.start()
    # back up to the start of the line/sentence the marker sits in
    start = body.rfind("\n", 0, i)
    body = body[start + 1 if start >= 0 else i:]
    paras, words = [], 0
    for para in re.split(r"\n[ \t]*\n", body):
        p = re.sub(r"\s+", " ", para).strip()
        if not p:
            continue
        paras.append(p)
        words += len(p.split())
        if words >= target:
            break
    text = "\n\n".join(paras).strip()
    if not text:
        raise RuntimeError("empty opening after trim")
    return text

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--drop", action="store_true", help="drop the collection before loading")
    ap.add_argument("--list", action="store_true", help="list stored openings and exit")
    ap.add_argument("--mongo-uri", default=URI)
    a = ap.parse_args()

    from pymongo import MongoClient
    cli = MongoClient(a.mongo_uri, serverSelectionTimeoutMS=4000)
    try:
        cli.admin.command("ping")
    except Exception as ex:
        sys.exit(f"Mongo not reachable at {a.mongo_uri} -> {ex}")
    coll = cli[OUT_DB][OUT_COLL]

    if a.list:
        for d in coll.find({}, {"author": 1, "title": 1, "words": 1}).sort("title", 1):
            print(f"  {d.get('author','?')} — {d.get('title','?')}  ({d.get('words','?')} words)")
        print(f"\n{coll.estimated_document_count()} openings in {OUT_DB}.{OUT_COLL}.")
        return

    if a.drop:
        coll.drop(); print(f"dropped {OUT_DB}.{OUT_COLL}")

    n = 0
    for author, title, gid, marker in BOOKS:
        try:
            text = first_page(fetch(gid), marker)
        except Exception as e:
            print(f"  SKIP  {title}: {e}", file=sys.stderr); continue
        doc = {"_id": hashlib.sha1(title.encode("utf-8")).hexdigest()[:16],
               "author": author, "title": title, "gutenberg_id": gid,
               "source": f"https://www.gutenberg.org/ebooks/{gid}",
               "text": text, "words": len(text.split())}
        coll.replace_one({"_id": doc["_id"]}, doc, upsert=True)
        n += 1
        print(f"  ok    {author} — {title}  ({doc['words']} words)")
    print(f"\nUpserted {n}/{len(BOOKS)} openings into {OUT_DB}.{OUT_COLL}.")

if __name__ == "__main__":
    main()
