#!/usr/bin/env python3
"""
seed_syntaxvision.py — Claude's analysis of the StoryWriter pipeline files.
Writes Annotations and ControlFlow docs to the SyntaxVision MongoDB database.
Run once; upserts safely on re-run.
"""
import os, sys, datetime
from pymongo import MongoClient

MONGO_URI = os.environ.get("STORYWRITER_MONGO_URI", "mongodb://localhost:27017/")
DB        = "SyntaxVision"
MODEL     = "claude"
HERE      = os.path.dirname(os.path.abspath(__file__))

def db():
    cli = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    cli.admin.command("ping")
    return cli[DB]

def line_count(filename):
    with open(os.path.join(HERE, filename), encoding="utf-8") as f:
        return sum(1 for _ in f)

def upsert_annotations(database, filename, by_line):
    """by_line: dict of {line_number: annotation_text}. Lines not in dict get null."""
    n = line_count(filename)
    entries = [
        {"line_number": i, "claude_annotation": by_line.get(i), "ollama_annotation": None}
        for i in range(1, n + 1)
    ]
    database["Annotations"].replace_one(
        {"file": filename},
        {"file": filename, "annotations": entries},
        upsert=True
    )
    annotated = sum(1 for e in entries if e["claude_annotation"])
    print(f"  Annotations: {filename} — {n} lines, {annotated} annotated")

def upsert_control_flow(database, filename, tree):
    now = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
    database["ControlFlow"].replace_one(
        {"file": filename, "model": MODEL},
        {"file": filename, "model": MODEL,
         "execution": {"timestamp": now, "status": "success"},
         "tree": tree},
        upsert=True
    )
    print(f"  ControlFlow:  {filename} (model={MODEL})")


# ── story_generator.py ───────────────────────────────────────────────────────

STORY_GEN_ANNOTATIONS = {
    2:   "Shebang line — tells the OS to run this script with Python 3.",
    3:   "Module docstring begins — describes StoryWriter's pipeline: audio arcs in, model infers emotional waypoints, writes a dark sci-fi story.",
    19:  "Documents the newline-delimited JSON event protocol this script emits on stdout so server.py can stream progress to the browser.",
    32:  "Documents the CLI interface — how server.py invokes this script with an arcs CSV, word count, and model tag.",
    38:  "Lists runtime requirements — an Ollama server and an optional MongoDB instance for opening-page style exemplars.",
    41:  "Import standard library modules — sys and os for process I/O, csv for reading arcs, json for the event protocol, math/random for numeric helpers, argparse for CLI, time for logging, re for text filtering, urllib for HTTP without external deps.",
    43:  "Attempt to import MongoClient from pymongo.",
    46:  "Is pymongo installed? → YES — MongoClient is available / NO — set it to None so MongoDB becomes fully optional.",
    48:  "Read the MongoDB connection URI from the environment — defaults to localhost so no config is needed for local development.",
    49:  "Read the database and collection names for style-exemplar opening pages from the environment.",
    51:  "Read the Ollama server base URL from the environment — defaults to localhost:11434.",
    55:  "emit() — serialize a dict as a JSON line and write it to stdout, then flush immediately so server.py receives events the moment they happen.",
    59:  "dbg() — write human-readable debug text to stderr, which is never seen by the parent server process.",
    65:  "is_number() — return True if a string can be parsed as a float; used to skip empty or non-numeric CSV cells.",
    71:  "load_arcs() — read the audio-arcs CSV into a list of row dicts using csv.DictReader.",
    73:  "Is the CSV empty? → YES — emit an error event and exit immediately / NO — return the rows.",
    77:  "column() — extract one named column from the arc rows as a list of floats, silently skipping missing or non-numeric values.",
    80:  "_norm() — min-max normalize a list of floats to the 0–1 range.",
    81:  "Is the list empty? → YES — return it unchanged / NO — normalize.",
    82:  "Find the min, max, and range — if all values are identical the range defaults to 1.0 to prevent division by zero.",
    83:  "Return the normalized list.",
    86:  "audio_summary() — build a plain-text description of the track for the inference model, covering feature trends and structural events.",
    91:  "Collect all column headers except 'time_s' — these are the acoustic features.",
    93:  "Open the summary with lines describing the audio length and what each column measures.",
    100: "For each feature with enough data, append a line showing its first→last value and the min/max range.",
    106: "Structural events — detect which layer (percussive or harmonic) dominates at each frame and record every flip.",
    107: "Normalize both series to 0–1 so they can be compared on the same scale.",
    108: "Do both series exist and have the same length? → YES — compare them / NO — skip structural events.",
    113: "Record a timestamped 'takes the lead' event each time the dominant layer flips — these become character entrances in the story.",
    115: "Find the energy peak and trough timestamps and append them as structural events.",
    122: "Append the structural events section to the summary, capped at 14 so the prompt doesn't balloon.",
    126: "Compute up to 16 evenly-spaced sample indices so the model can see the actual numeric shape of the audio.",
    128: "Append the CSV header for the sampled rows.",
    129: "Append each sampled row as a comma-separated line.",
    130: "Return the complete summary string.",
    134: "ollama_chat() — send a chat request to Ollama's /api/chat endpoint and return the assembled response message.",
    139: "Build the request body — model, messages, stream flag, keep_alive to hold the model resident between calls, and optional tools and generation options.",
    146: "Create the HTTP POST request to /api/chat with the JSON body.",
    149: "Open the connection — timeout defaults to 30 minutes to allow slow CPU-only models to finish.",
    152: "HTTPError handler — read the error body for detail.",
    154: "Is this a 404? → YES — the model isn't pulled, raise a descriptive error telling the user to run 'ollama pull' / NO — raise a generic HTTP error.",
    159: "URLError handler — Ollama is not running or the URL is wrong; raise a descriptive error.",
    162: "Is streaming disabled? → YES — read the full response at once and return the message dict / NO — stream token by token.",
    163: "Initialize accumulators for content fragments, tool calls, and the role field.",
    164: "Iterate over newline-delimited JSON chunks from the streaming response.",
    168: "Parse each chunk and extract the message field.",
    171: "Append content fragments and call on_delta so the caller can forward text to the UI in real time.",
    175: "Collect any tool_call objects from the chunk.",
    177: "Assemble the final message dict from accumulated content parts.",
    179: "Attach tool_calls to the message if any were collected.",
    180: "Return the assembled message.",
    187: "META_LINE — compiled regex matching model narration that should never reach the UI (e.g. 'chosen arbitrarily', 'were not provided').",
    190: "SectionRouter — stateful router for the inference turn's streamed output; splits it into 'reasoning' and 'story' event streams.",
    198: "HEADING — matches lines containing the word 'STORY' — the section boundary that opens the prose.",
    199: "FENCE — matches markdown code fence delimiters (```).",
    200: "SECTION — matches bare MAPPING/SHAPE/STORY headings re-emitted mid-story — dropped so they don't pollute the prose pane.",
    204: "Initialize state: not yet in the story section, not inside a fence, empty buffer, any_story flag false.",
    210: "feed() — append a streamed text piece to the buffer and process any complete lines.",
    216: "_line() — route a single complete line to the correct output channel.",
    217: "Is this a ``` fence marker? → YES — toggle the in_fence flag and return / NO — continue.",
    219: "Are we inside a code fence? → YES — drop this line silently / NO — continue.",
    222: "Have we seen the STORY heading yet? → YES — skip to post-story routing / NO — scan for the heading.",
    223: "Search for the STORY heading within this line.",
    224: "Is the heading present? → YES — split at the boundary; text before goes to reasoning, heading itself is suppressed / NO — emit as reasoning.",
    229: "Open the story section; if text follows the heading on the same line, emit it immediately as a story delta.",
    233: "Non-heading, non-META reasoning lines are emitted as 'reasoning' events.",
    236: "Are we in the story section? → YES — check for META narration / NO — handled above.",
    238: "Is this a re-emitted MAPPING/SHAPE/STORY heading? → YES — drop it so it can't appear in the prose pane / NO — emit as story.",
    240: "Emit the line as a 'story' event.",
    243: "flush() — process any remaining partial line in the buffer at stream end.",
    250: "_json_objects() — extract all brace-balanced JSON object substrings from arbitrary text.",
    251: "Scan character by character, tracking brace depth to find complete top-level objects.",
    264: "collect_points() — recursively extract every {valence, arousal, dominance} point from whatever shape the model produced.",
    269: "Is the recursion deeper than 6 levels? → YES — return empty to prevent stack overflow / NO — continue.",
    271: "Is this value a string? → YES — try JSON-parsing it first before recursing / NO — check if it's a dict or list.",
    274: "Does this dict have both 'valence' and 'arousal' keys? → YES — it's a valid point, collect it / NO — recurse into its values.",
    279: "Is this a list? → YES — recurse into each element / NO — return empty.",
    287: "fallback_points() — derive k VAD waypoints directly from the audio features when the model fails to produce usable POINTS.",
    293: "Map brightness (centroid)→valence, energy→arousal, spectral contrast→dominance.",
    297: "Is there any feature data? → YES — build the points / NO — return empty.",
    299: "Helper — safely index a normalized array at position i, defaulting to 0.5 if out of bounds.",
    300: "Build k evenly-spaced points across the full track duration.",
    309: "build_system() — construct the system prompt for the MAPPING/SHAPE/POINTS inference turn.",
    310: "System prompt text — instructs the model to work in three ordered sections: MAPPING (read the audio), SHAPE (list waypoints), POINTS (emit a JSON array of VAD emotions).",
    325: "Is extra direction present? → YES — append it to the system prompt / NO — skip.",
    332: "vad_feeling() — map a valence/arousal point to a plain-English two-word label using a 3×3 grid.",
    337: "3×3 grid — rows are valence (low/mid/high), columns are arousal (low/mid/high).",
    341: "Threshold boundaries — below 4.2 is low, above 5.8 is high, between is mid.",
    344: "Return the grid cell label for this (valence, arousal) point.",
    346: "Path to writer_system.txt — the user-editable file that overrides the default writer system prompt.",
    347: "Default writer system prompt — dark dystopian sci-fi, Black Mirror tone, near-future AI woven into daily life, unsettling reveal ending.",
    373: "_load_writer_system() — load writer_system.txt if it exists, otherwise return the hardcoded default.",
    375: "Is writer_system.txt present and non-empty? → YES — use its contents / NO — use the default.",
    377: "Is the file absent? → YES — return the default / NO — handled above.",
    380: "WRITER_SYSTEM — the loaded or default writer system prompt, stored at module level so all calls share it.",
    382: "arc_sentence() — convert a list of VAD seeds into a plain-English feelings phrase joined by 'then' — so the writer reads an emotional arc, never bare numbers.",
    387: "writer_user() — build the writer model's user prompt from openings, seeds, and an optional author name.",
    390: "Are opening exemplars available? → YES — prepend them with a directive to study their craft but not copy their content / NO — skip.",
    393: "Format each opening with its author/title citation.",
    401: "Append the emotional arc as a plain-English sentence — this is the core directive to the writer.",
    404: "Instruct the model to include one external-event interruption somewhere in the story.",
    408: "Was an author name supplied? → YES — append a directive to write with that sensibility / NO — skip.",
    410: "Final directive — dark dystopian story, unsettling reveal, no comfort.",
    414: "brief_display() — format the writer's brief as a human-readable string for the Model Reasoning pane.",
    425: "load_openings() — load all style-exemplar opening pages from the StoryWriterCorpus.Openings MongoDB collection.",
    427: "Query for author, title, and text fields only.",
    429: "Filter out documents with empty or missing text.",
    431: "Did the query fail? → YES — return empty list so the pipeline continues without openings / NO — return the docs.",
    435: "pick_openings() — select k random exemplars from the loaded list for variety.",
    439: "Return a random sample of min(k, available) openings.",
    444: "ProseRouter — stateful router for prose streaming; suppresses leading junk and emits only clean prose as 'story' events.",
    448: "META — matches preamble lines small models sometimes prepend (e.g. 'Here is the story:', '**Title**').",
    449: "HEAD — matches markdown heading lines.",
    450: "FENCE — matches code fence delimiters.",
    454: "Initialize state — buffer, started flag, in_fence flag, emitted text accumulator, label, and word-count trackers.",
    458: "feed() — append a piece to the buffer and process complete lines.",
    462: "_line() — route one complete line.",
    465: "Is this a ``` fence marker? → YES — toggle fence state and return / NO — continue.",
    467: "Are we inside a code fence? → YES — drop this line / NO — continue.",
    469: "Have we started emitting prose yet? → YES — emit directly / NO — keep filtering leading junk.",
    470: "Is this line blank? → YES — skip it / NO — check if it's junk.",
    471: "Is this a META preamble line or a markdown heading? → YES — drop it / NO — the prose has started.",
    474: "Mark started=True — this is the first real prose line.",
    476: "Emit the line as a 'story' event and append it to the accumulated text.",
    477: "Update the running word count.",
    478: "Is the word count 10+ more than the last status update? → YES — emit a live word-count status / NO — skip.",
    481: "Is the word count 50+ more than the last reasoning update? → YES — emit a progress note to the reasoning pane / NO — skip.",
    485: "flush() — process any remaining partial line at stream end.",
    491: "ReasonRouter — stateful router for the inference model's MAPPING/SHAPE reasoning; streams it to the UI while dropping code fences, META narration, and POINTS JSON.",
    496: "JSONISH — matches lines that look like JSON (starts with [ or {, or contains 'points'/'valence') so the POINTS line is never shown as reasoning.",
    498: "Initialize state — buffer, in_fence flag, and accumulated text.",
    502: "feed() — buffer and process complete lines.",
    506: "_line() — route one line.",
    507: "Is this line inside a fence, META narration, or JSON? → YES — drop it / NO — emit as reasoning.",
    512: "Emit non-empty clean lines as 'reasoning' events and accumulate them.",
    515: "flush() — process any remaining partial line.",
    522: "main() — entry point: parse arguments, connect to MongoDB, load arcs, call the inference model for emotional waypoints, then call the writer model to produce the story.",
    523: "Define CLI arguments — arcs CSV path, author name, word count target, Ollama model tag, optional prompt file, and random seed.",
    531: "Parse the arguments.",
    533: "Was --seed supplied? → YES — seed the random number generator for a reproducible run / NO — use entropy.",
    538: "Is pymongo available? → YES — attempt a MongoDB connection / NO — skip (client stays None).",
    539: "Ping MongoDB to verify the connection is live.",
    544: "Did the connection fail? → YES — log a warning and continue with client=None (openings disabled) / NO — continue.",
    548: "Was --prompt-file supplied and does the file exist? → YES — read it into extra / NO — leave extra empty.",
    553: "Load the arcs CSV into rows and build the audio summary string.",
    555: "Log the full audio summary to stderr for debugging.",
    557: "Set up the optional dashboard log — if --log was given, logrec() appends timestamped JSONL events to it.",
    560: "logrec() — append a timestamped event to the log file; is a no-op if --log was not passed.",
    569: "Clear the log file at startup so each run starts fresh.",
    572: "Build the inference system prompt from the author name, word count, and any extra direction.",
    579: "Trim the audio summary to the trend and structural-events section only — dropping the sampled rows keeps the prompt shorter on CPU boxes.",
    582: "Build the user message for the inference turn.",
    584: "Package the system and user messages into the messages list.",
    587: "Emit an 'Inferring the shape' status message.",
    591: "Emit 'WHAT THE MACHINE HEARD' to the reasoning pane so there's no dead air while the model prefills the long prompt.",
    597: "Cap the inference turn at 420 tokens — it only needs MAPPING/SHAPE plus the POINTS line, not a full story.",
    598: "Instantiate the ReasonRouter to stream the model's MAPPING/SHAPE reasoning live.",
    600: "Retry loop — up to 2 attempts to get usable POINTS from the model.",
    601: "Call the inference model, streaming reasoning through the ReasonRouter.",
    604: "Did the call raise an exception? → YES — emit an error event and exit / NO — continue.",
    607: "Flush any remaining buffered reasoning text.",
    608: "Append the model's message to the conversation history for context.",
    610: "Extract POINTS — parse all JSON objects from the response text and collect VAD points.",
    613: "Log the inference attempt result to the dashboard.",
    614: "Were usable POINTS found? → YES — break out of the retry loop / NO — try again.",
    616: "Is this the first failed attempt? → YES — append a nudge message asking the model to output ONLY the POINTS line / NO — both attempts failed.",
    621: "Did both attempts produce no usable POINTS? → YES — fall back to audio-derived waypoints as a last resort / NO — handled above.",
    625: "Clamp each VAD point to the 1–9 range, convert it to a plain-English feeling label, and emit a 'lookup' event — these become the seeds in the UI's left-pane timeline.",
    641: "Is the seed list empty? → YES — emit an error and exit, this should never happen / NO — continue.",
    647: "Set a generous token ceiling for the prose pass — up to 8192, minimum 2048, scaled by the word target.",
    649: "prose_pass() — define a single streaming prose writing pass: clear the pane, stream the model's output, return the emitted text.",
    651: "Emit a status message and a reasoning note for the start of this pass.",
    652: "Clear the story pane so the new prose starts fresh.",
    653: "Instantiate a ProseRouter for this pass.",
    654: "Set generation options — token ceiling, temperature, and top_p.",
    657: "Call ollama_chat in streaming mode, routing output through the ProseRouter.",
    662: "Did the call raise an exception? → YES — emit an error and exit / NO — continue.",
    664: "Flush the ProseRouter and return the accumulated story text.",
    669: "Build the emotional arc spine as a plain arrow-joined label sequence and emit it to the reasoning pane.",
    672: "Load one random style-exemplar opening from MongoDB (if available).",
    673: "Were openings found? → YES — emit a status message about them / NO — skip.",
    678: "Build the writer's user prompt from the seeds, optional author, and openings.",
    679: "Format the writer system prompt with the word-count target.",
    680: "Emit the writer's brief to the reasoning pane so the user sees what the model was given.",
    683: "Call prose_pass() to write the story in a single drafting pass at temperature 0.85.",
    684: "Log completion with the draft word count.",
    686: "Emit 'status: Done.'",
    687: "Emit the 'final' event with seed count and story character count.",
    688: "Log the final event to the dashboard JSONL if enabled.",
    693: "Entry point guard — call main() only when the script is run directly, not imported.",
}

STORY_GEN_TREE = {
    "name": "story_generator.py",
    "type": "file",
    "children": [
        {
            "name": "module_header",
            "type": "block",
            "line_start": 1, "line_end": 51,
            "annotation": "Module header — docstring describing the full pipeline, stdlib imports, optional pymongo import, and environment-variable configuration for MongoDB and Ollama endpoints.",
            "on_happy_path": True, "captured": None, "children": []
        },
        {
            "name": "emit",
            "type": "function",
            "line_start": 55, "line_end": 57,
            "annotation": "Write a dict as a JSON-encoded line to stdout and flush immediately — the sole output channel server.py reads to update job state in real time.",
            "on_happy_path": True, "captured": None, "children": []
        },
        {
            "name": "dbg",
            "type": "function",
            "line_start": 59, "line_end": 61,
            "annotation": "Write human-readable debug text to stderr — never seen by the parent process, for local debugging only.",
            "on_happy_path": True, "captured": None, "children": []
        },
        {
            "name": "csv_utilities",
            "type": "block",
            "line_start": 65, "line_end": 84,
            "annotation": "Four small helpers for reading and normalizing the arcs CSV: is_number() guards against bad cells, load_arcs() reads the file, column() extracts one feature series, _norm() min-max normalizes it to 0–1.",
            "on_happy_path": True, "captured": None,
            "children": [
                {
                    "name": "empty_file_guard",
                    "type": "if",
                    "line_start": 73, "line_end": 74,
                    "annotation": "Is the CSV empty? → YES — emit an error event and exit; a valid arcs file always has rows so this is never on the happy path.",
                    "on_happy_path": False, "captured": None, "children": []
                }
            ]
        },
        {
            "name": "audio_summary",
            "type": "function",
            "line_start": 86, "line_end": 130,
            "annotation": "Build a multi-line plain-text description of the track for the inference model — per-feature trends, structural events (layer dominance flips, energy peak/trough), and a sample of raw rows so the model can see the actual numeric shape.",
            "on_happy_path": True, "captured": None,
            "children": [
                {
                    "name": "structural_events",
                    "type": "block",
                    "line_start": 106, "line_end": 124,
                    "annotation": "Detect structural events: find every frame where the dominant layer (percussive vs harmonic) flips, and locate the energy peak and trough — these become the raw material for separate characters and intersecting arcs.",
                    "on_happy_path": True, "captured": None, "children": []
                },
                {
                    "name": "sampled_rows",
                    "type": "block",
                    "line_start": 126, "line_end": 130,
                    "annotation": "Append up to 16 evenly-spaced raw rows so the model can see the actual numeric shape, not just the trend summary.",
                    "on_happy_path": True, "captured": None, "children": []
                }
            ]
        },
        {
            "name": "ollama_chat",
            "type": "function",
            "line_start": 134, "line_end": 180,
            "annotation": "Send a chat request to Ollama's /api/chat endpoint — supports streaming with token-by-token callbacks, tool calls, keep_alive to hold the model resident between calls, and a num_predict cap to prevent runaway generation.",
            "on_happy_path": True, "captured": None,
            "children": [
                {
                    "name": "http_error_404",
                    "type": "if",
                    "line_start": 154, "line_end": 158,
                    "annotation": "Is this a 404? → YES — the model isn't pulled; raise a descriptive error telling the user to run 'ollama pull' / NO — raise a generic HTTP error with the status code.",
                    "on_happy_path": False, "captured": None, "children": []
                },
                {
                    "name": "url_error_handler",
                    "type": "except",
                    "line_start": 159, "line_end": 160,
                    "annotation": "Ollama is not running or the URL is wrong — raise a descriptive error so the caller can emit a clean error event.",
                    "on_happy_path": False, "captured": None, "children": []
                },
                {
                    "name": "non_streaming_path",
                    "type": "if",
                    "line_start": 162, "line_end": 162,
                    "annotation": "Is streaming disabled? → YES — read the full response body at once and return; not used in the main pipeline, all calls stream.",
                    "on_happy_path": False, "captured": None, "children": []
                },
                {
                    "name": "streaming_loop",
                    "type": "block",
                    "line_start": 163, "line_end": 180,
                    "annotation": "Streaming path — iterate over newline-delimited JSON chunks, accumulate content and tool_call fragments, and call on_delta for each piece so the caller can forward text in real time.",
                    "on_happy_path": True, "captured": None, "children": []
                }
            ]
        },
        {
            "name": "SectionRouter",
            "type": "function",
            "line_start": 187, "line_end": 246,
            "annotation": "Stateful line router for the inference turn's streamed output — everything before the 'STORY' heading goes to 'reasoning' events, everything after goes to 'story' events; also drops code fences and META narration.",
            "on_happy_path": True, "captured": None,
            "children": [
                {
                    "name": "pre_story_routing",
                    "type": "block",
                    "line_start": 222, "line_end": 235,
                    "annotation": "Before the STORY heading is seen — scan each line for the heading; when found, split at the boundary and open the story section.",
                    "on_happy_path": True, "captured": None, "children": []
                },
                {
                    "name": "post_story_routing",
                    "type": "block",
                    "line_start": 236, "line_end": 241,
                    "annotation": "After the STORY heading — emit each non-META, non-section-heading line as a 'story' event.",
                    "on_happy_path": True, "captured": None, "children": []
                }
            ]
        },
        {
            "name": "points_extraction",
            "type": "block",
            "line_start": 250, "line_end": 306,
            "annotation": "Three helpers for getting VAD waypoints out of the model's response: _json_objects() extracts brace-balanced substrings, collect_points() recursively finds {valence,arousal,dominance} objects in any shape, fallback_points() derives points from the audio if the model fails.",
            "on_happy_path": True, "captured": None,
            "children": [
                {
                    "name": "fallback_points",
                    "type": "function",
                    "line_start": 287, "line_end": 306,
                    "annotation": "Last-resort fallback — derive k VAD waypoints directly from audio features (brightness→valence, energy→arousal, contrast→dominance) when the model produces no usable POINTS.",
                    "on_happy_path": False, "captured": None, "children": []
                }
            ]
        },
        {
            "name": "prompt_builders",
            "type": "block",
            "line_start": 309, "line_end": 423,
            "annotation": "All functions that build prompts and briefs: build_system() for the inference turn, vad_feeling() to label VAD points, the WRITER_SYSTEM constant, arc_sentence(), writer_user(), and brief_display().",
            "on_happy_path": True, "captured": None,
            "children": [
                {
                    "name": "extra_direction",
                    "type": "if",
                    "line_start": 325, "line_end": 327,
                    "annotation": "Was extra direction supplied from prompts.txt? → YES — append it to the system prompt / NO — skip; prompts.txt is optional.",
                    "on_happy_path": False, "captured": None, "children": []
                },
                {
                    "name": "writer_system_file_missing",
                    "type": "except",
                    "line_start": 377, "line_end": 379,
                    "annotation": "Is writer_system.txt absent? → YES — use the hardcoded default system prompt / NO — handled above.",
                    "on_happy_path": False, "captured": None, "children": []
                },
                {
                    "name": "openings_in_brief",
                    "type": "if",
                    "line_start": 395, "line_end": 399,
                    "annotation": "Were opening exemplars loaded? → YES — prepend them to the writer prompt with a directive to study craft but not copy content / NO — skip.",
                    "on_happy_path": False, "captured": None, "children": []
                },
                {
                    "name": "author_sensibility",
                    "type": "if",
                    "line_start": 408, "line_end": 409,
                    "annotation": "Was an author name supplied? → YES — append a sensibility directive / NO — skip; style comes from the openings.",
                    "on_happy_path": False, "captured": None, "children": []
                }
            ]
        },
        {
            "name": "openings_loader",
            "type": "block",
            "line_start": 425, "line_end": 440,
            "annotation": "load_openings() fetches style-exemplar opening pages from MongoDB (returns [] on any failure — MongoDB is optional). pick_openings() randomly selects k of them for variety.",
            "on_happy_path": True, "captured": None,
            "children": [
                {
                    "name": "mongo_query_failure",
                    "type": "except",
                    "line_start": 431, "line_end": 433,
                    "annotation": "Did the MongoDB query fail? → YES — return empty list and continue without openings / NO — return the docs.",
                    "on_happy_path": False, "captured": None, "children": []
                }
            ]
        },
        {
            "name": "ProseRouter",
            "type": "function",
            "line_start": 444, "line_end": 488,
            "annotation": "Stateful router for prose streaming — suppresses leading junk (preamble lines, headings, fences) and emits only clean prose as 'story' events; also emits live word-count status updates.",
            "on_happy_path": True, "captured": None,
            "children": [
                {
                    "name": "leading_junk_filter",
                    "type": "block",
                    "line_start": 469, "line_end": 474,
                    "annotation": "Before the first real prose line — skip blank lines, META preamble, and markdown headings until clean prose begins.",
                    "on_happy_path": False, "captured": None, "children": []
                },
                {
                    "name": "word_count_updates",
                    "type": "block",
                    "line_start": 477, "line_end": 483,
                    "annotation": "Emit a live word-count status every 10 words and a reasoning-pane progress note every 50 words so the UI shows writing progress in real time.",
                    "on_happy_path": True, "captured": None, "children": []
                }
            ]
        },
        {
            "name": "ReasonRouter",
            "type": "function",
            "line_start": 491, "line_end": 519,
            "annotation": "Stateful router for the inference model's MAPPING/SHAPE reasoning — streams clean reasoning to the UI while dropping code fences, META narration, and POINTS JSON so only human-readable text appears.",
            "on_happy_path": True, "captured": None, "children": []
        },
        {
            "name": "main",
            "type": "function",
            "line_start": 522, "line_end": 693,
            "annotation": "Entry point — parse CLI args, connect to MongoDB, load the arcs CSV, call the inference model for emotional waypoints, then call the writer model to produce the story in a single prose pass.",
            "on_happy_path": True, "captured": None,
            "children": [
                {
                    "name": "arg_parse",
                    "type": "block",
                    "line_start": 523, "line_end": 531,
                    "annotation": "Define and parse CLI arguments — arcs CSV path, author name, word count, Ollama model tag, optional prompt file, and optional random seed.",
                    "on_happy_path": True, "captured": None, "children": []
                },
                {
                    "name": "seed_random",
                    "type": "if",
                    "line_start": 533, "line_end": 534,
                    "annotation": "Was --seed supplied? → YES — seed the RNG for a reproducible run (testing only) / NO — use entropy.",
                    "on_happy_path": False, "captured": None, "children": []
                },
                {
                    "name": "mongo_connect",
                    "type": "block",
                    "line_start": 538, "line_end": 546,
                    "annotation": "Attempt MongoDB connection and ping — set client to None on any failure so the pipeline continues with openings disabled.",
                    "on_happy_path": True, "captured": None,
                    "children": [
                        {
                            "name": "mongo_connect_failure",
                            "type": "except",
                            "line_start": 544, "line_end": 546,
                            "annotation": "Did MongoDB fail to connect? → YES — log a warning to stderr and set client=None; the pipeline continues without opening exemplars.",
                            "on_happy_path": False, "captured": None, "children": []
                        }
                    ]
                },
                {
                    "name": "load_prompt_file",
                    "type": "if",
                    "line_start": 548, "line_end": 551,
                    "annotation": "Was --prompt-file given and does it exist? → YES — read its contents into extra / NO — leave extra empty.",
                    "on_happy_path": False, "captured": None, "children": []
                },
                {
                    "name": "load_arcs_and_summary",
                    "type": "block",
                    "line_start": 553, "line_end": 555,
                    "annotation": "Load the arcs CSV into rows and build the audio summary string; log it to stderr for debugging.",
                    "on_happy_path": True, "captured": None, "children": []
                },
                {
                    "name": "log_setup",
                    "type": "block",
                    "line_start": 557, "line_end": 570,
                    "annotation": "Set up the optional dashboard log — logrec() appends timestamped JSONL events to the log file; it's a no-op if --log wasn't passed.",
                    "on_happy_path": True, "captured": None, "children": []
                },
                {
                    "name": "build_inference_messages",
                    "type": "block",
                    "line_start": 572, "line_end": 585,
                    "annotation": "Build the system and user messages for the inference turn — the user message contains the audio trend summary (raw sampled rows are dropped to keep the prompt shorter on CPU boxes).",
                    "on_happy_path": True, "captured": None, "children": []
                },
                {
                    "name": "inference_call",
                    "type": "block",
                    "line_start": 597, "line_end": 623,
                    "annotation": "Call the inference model up to 2 times to get MAPPING/SHAPE reasoning and a POINTS array, streaming reasoning live through ReasonRouter.",
                    "on_happy_path": True, "captured": None,
                    "children": [
                        {
                            "name": "inference_exception",
                            "type": "except",
                            "line_start": 604, "line_end": 606,
                            "annotation": "Did the model call raise? → YES — emit an error event and exit; cannot proceed without the inference turn.",
                            "on_happy_path": False, "captured": None, "children": []
                        },
                        {
                            "name": "inference_retry_nudge",
                            "type": "if",
                            "line_start": 616, "line_end": 619,
                            "annotation": "Is this the first attempt and no POINTS were found? → YES — append a nudge message and retry / NO — both attempts failed.",
                            "on_happy_path": False, "captured": None, "children": []
                        },
                        {
                            "name": "fallback_to_audio",
                            "type": "if",
                            "line_start": 621, "line_end": 623,
                            "annotation": "Did both attempts produce no usable POINTS? → YES — derive the arc directly from the audio as a last resort / NO — use the model's points.",
                            "on_happy_path": False, "captured": None, "children": []
                        }
                    ]
                },
                {
                    "name": "emit_waypoints",
                    "type": "block",
                    "line_start": 625, "line_end": 636,
                    "annotation": "Clamp each VAD point to 1–9, label it with a plain-English feeling, and emit a 'lookup' event — these become the seeds in the UI's left-pane timeline.",
                    "on_happy_path": True, "captured": None, "children": []
                },
                {
                    "name": "no_seeds_guard",
                    "type": "if",
                    "line_start": 641, "line_end": 643,
                    "annotation": "Is the seed list empty? → YES — emit an error and exit; this should never happen in practice.",
                    "on_happy_path": False, "captured": None, "children": []
                },
                {
                    "name": "prose_pass_fn",
                    "type": "block",
                    "line_start": 647, "line_end": 666,
                    "annotation": "Define prose_pass() — a reusable single streaming writing pass: clear the pane, stream the model through ProseRouter, return the emitted text.",
                    "on_happy_path": True, "captured": None,
                    "children": [
                        {
                            "name": "prose_exception",
                            "type": "except",
                            "line_start": 662, "line_end": 663,
                            "annotation": "Did the writer model call raise? → YES — emit an error and exit; no story can be produced.",
                            "on_happy_path": False, "captured": None, "children": []
                        }
                    ]
                },
                {
                    "name": "load_openings_and_brief",
                    "type": "block",
                    "line_start": 669, "line_end": 682,
                    "annotation": "Emit the arc spine to the reasoning pane, load one random opening exemplar, build the writer's user prompt and brief display.",
                    "on_happy_path": True, "captured": None, "children": []
                },
                {
                    "name": "write_story",
                    "type": "block",
                    "line_start": 683, "line_end": 684,
                    "annotation": "Call prose_pass() at temperature 0.85 to produce the story in a single drafting pass.",
                    "on_happy_path": True, "captured": None, "children": []
                },
                {
                    "name": "final_emit",
                    "type": "block",
                    "line_start": 686, "line_end": 689,
                    "annotation": "Emit 'status: Done', the 'final' event with seed count and story length, and log both to the dashboard JSONL if enabled.",
                    "on_happy_path": True, "captured": None, "children": []
                }
            ]
        }
    ]
}


# ── server.py ────────────────────────────────────────────────────────────────

SERVER_ANNOTATIONS = {
    1:   "Module docstring — describes the local backend: HTTP server, job pipeline, persistence to MongoDB, and the API surface.",
    31:  "Import os, sys, json, uuid for process and data handling; threading for concurrent jobs; subprocess for spawning child processes; urllib.parse for URL decoding.",
    33:  "HERE — absolute path of this script's directory, used to locate sibling files reliably.",
    34:  "UPLOAD_ROOT — the directory where uploaded audio files and job working directories land.",
    35:  "PORT — the port the server listens on (8765).",
    36:  "PY — the same Python interpreter that started server.py, so child processes use the same environment.",
    37:  "_NO_WINDOW — Windows-only flag that prevents child process windows from flashing; zero on non-Windows.",
    39:  "ALLOWED_EXT — the set of audio file extensions the server will accept; everything else is rejected.",
    40:  "MAX_UPLOAD — hard cap on upload size at 40 MB.",
    41:  "MAX_CONCURRENT — maximum simultaneous pipeline jobs (effectively unlimited for single-user demo use).",
    42:  "TOKEN — optional shared secret read from the environment; if set, all requests must include it as X-Token.",
    46:  "MongoDB connection settings for persisting finished stories — database name and collection name read from the environment.",
    51:  "save_story() — persist a finished run (story prose, reasoning, audio arcs, source song) to MongoDB so it can be replayed instantly later.",
    62:  "Is this a library song? → YES — it lives on disk under Songs/, so skip GridFS and key the result by library_file / NO — it's an upload, stash the audio bytes in GridFS.",
    77:  "Build the MongoDB document — story text, reasoning, audio arcs, lexicon seeds, source filename, library key, GridFS song id, and creation timestamp.",
    87:  "Is this a library song? → YES — upsert by library_file so re-baking replaces the old result / NO — insert a new doc for each uploaded run.",
    92:  "Log the persistence result to stderr.",
    94:  "Did saving fail? → YES — log and swallow the error; a save failure must never break a job that already finished.",
    98:  "SONGS_DIR — path to the Songs/ directory holding catalog mp3 files.",
    99:  "CATALOG_PATH — path to songs_catalog.json, the editable song library.",
    101: "load_catalog() — read songs_catalog.json and return its genres and songs; return an empty shell if the file is absent or malformed.",
    109: "prebaked_files() — query MongoDB for the set of catalog filenames that already have a stored result, for the UI 'ready' badge.",
    114: "Did the query fail? → YES — return an empty set so the UI still works, just without ready badges / NO — return the set of filenames.",
    120: "load_result() — fetch a pre-baked run for a catalog song from MongoDB, or return None.",
    122: "Is the library_file blank? → YES — nothing to look up, return None / NO — query MongoDB.",
    132: "Was a matching doc found? → YES — return story, reasoning, audio arcs, and seeds / NO — return None.",
    139: "JOBS — shared dict mapping job_id to job state; LOCK — the threading lock that protects it.",
    140: "RUNNING — count of currently active pipeline jobs.",
    141: "set_job() — thread-safely update a job's state fields.",
    143: "get_job() — thread-safely return a snapshot of a job's state.",
    147: "GRAPH_COLS — the seven audio features surfaced in the left-hand graph, mapping CSV column names to short UI keys.",
    160: "audio_series() — downsample the seven core audio features from the arcs CSV to ~n points, normalized to 1–9 range, for the left-hand graph.",
    182: "run_pipeline() — run the full extract→generate pipeline in a background thread for one job.",
    185: "arcs — path where the extractor will write the arcs CSV.",
    187: "Set the job to 'extracting' state and emit a status message.",
    189: "Spawn extract_arcs_hpss.py as a subprocess, capturing its stdout for progress lines.",
    195: "Read extraction progress lines and surface '[extract]' stage lines as live status updates.",
    202: "Did the extractor fail or produce no arcs file? → YES — raise a RuntimeError with the log tail / NO — continue.",
    205: "Read the arcs CSV into an audio_series dict and attach it to the job for the graph.",
    208: "Set the job to 'generating' state.",
    210: "Build the command to run story_generator.py with the arcs, author, word count, model, and log file.",
    218: "Spawn story_generator.py as a subprocess, reading its newline-delimited JSON events on stdout.",
    222: "Read and translate each JSON event into job state updates.",
    231: "Is this a 'story' event? → YES — append to story_buf and update partial / NO — check other event types.",
    233: "Is this a 'story_reset' event? → YES — clear story_buf and partial / NO — check next.",
    235: "Is this a 'reasoning' event? → YES — append to reason_buf / NO — check next.",
    237: "Is this a 'lookup' event? → YES — append a seed to words_list / NO — check next.",
    241: "Is this a 'status' event? → YES — update the job message / NO — check next.",
    243: "Is this an 'error' event? → YES — save the error message / NO — ignore.",
    247: "Wait for the generator to finish and check for errors.",
    252: "Assemble the final story text and set the job to 'done'.",
    255: "Persist the finished run to MongoDB.",
    269: "Did the pipeline fail? → YES — set the job to 'error' state with the exception message.",
    273: "Always decrement RUNNING when the job finishes, success or failure.",
    276: "Handler — the HTTP request handler class; implements do_GET and do_POST.",
    277: "_send() — send an HTTP response with a body, setting Content-Type to JSON or HTML as appropriate.",
    288: "_authed() — return True if no token is required, or if the request includes the correct X-Token header.",
    291: "do_GET() — route GET requests to the appropriate handler.",
    293: "Is the path / or /index.html? → YES — serve index.html / NO — check next route.",
    296: "Is the path /status? → YES — return the job state dict for the given job id / NO — check next.",
    299: "Is the path /prompts.txt? → YES — serve the editable default prompt file / NO — check next.",
    308: "Is the path /library? → YES — return the catalog with 'ready' flags / NO — check next.",
    313: "Is the path /result? → YES — return the pre-baked result for a catalog song / NO — check next.",
    316: "Is the path /song? → YES — stream the catalog mp3 / NO — return 404.",
    320: "_serve_song() — serve a catalog mp3 from Songs/ with Range request support for seeking.",
    322: "Validate the filename — basename only, no path traversal.",
    325: "Does the file exist? → YES — serve it / NO — return 404.",
    328: "Was a Range header sent? → YES — serve the requested byte range (206 Partial Content) / NO — serve the full file.",
    358: "do_POST() — route POST requests to /upload or /process.",
    362: "Is the request authorized? → YES — continue / NO — return 401.",
    364: "Is this /upload? → YES — save the uploaded audio file / NO — check /process.",
    365: "Validate the file extension against ALLOWED_EXT and the file size against MAX_UPLOAD.",
    370: "Is the extension not allowed? → YES — return 400 / NO — check size.",
    372: "Is the file too large or empty? → YES — return 413 / NO — proceed.",
    373: "Generate a unique upload id, create its job directory, and write the audio file.",
    381: "Save the original filename to source_name.txt for persistence.",
    384: "Is this /process? → YES — start the pipeline / NO — return 404.",
    388: "Is a library_file specified? → YES — copy the song from Songs/ into a job dir / NO — use the uploaded file.",
    390: "Validate the library filename — basename only.",
    392: "Does the library song exist? → YES — continue / NO — return 400.",
    396: "Create a job directory and copy the library song into it.",
    402: "Find the uploaded audio file in the job directory.",
    408: "Is the server at capacity? → YES — return 429 / NO — increment RUNNING and continue.",
    413: "Parse author, model, word count, and optional prompt from the request body.",
    419: "Was a prompt supplied? → YES — write it to prompt.txt in the job dir / NO — skip.",
    422: "Create the job record, start the pipeline thread, and return the job_id.",
    434: "Suppress the default request log line — the parent process handles logging.",
    436: "Entry point — create the uploads directory and start the ThreadingHTTPServer on localhost.",
}

SERVER_TREE = {
    "name": "server.py",
    "type": "file",
    "children": [
        {
            "name": "module_header",
            "type": "block",
            "line_start": 1, "line_end": 44,
            "annotation": "Module docstring describing the server's role, API surface, and security model; imports; and all configuration constants (port, upload limits, token auth, MongoDB settings).",
            "on_happy_path": True, "captured": None, "children": []
        },
        {
            "name": "save_story",
            "type": "function",
            "line_start": 51, "line_end": 95,
            "annotation": "Persist a finished run to MongoDB — story prose, model reasoning, audio arcs, seeds, and the source audio. Library songs are keyed by filename (upsert); uploads go into GridFS. Failures are logged and swallowed so they never break a completed job.",
            "on_happy_path": True, "captured": None,
            "children": [
                {
                    "name": "gridfs_for_uploads",
                    "type": "if",
                    "line_start": 62, "line_end": 76,
                    "annotation": "Is this an uploaded (non-library) song? → YES — store the audio bytes in GridFS so the result is self-contained / NO — library songs live on disk, skip GridFS.",
                    "on_happy_path": False, "captured": None, "children": []
                },
                {
                    "name": "upsert_vs_insert",
                    "type": "if",
                    "line_start": 87, "line_end": 90,
                    "annotation": "Is this a library song? → YES — upsert so re-baking replaces the old doc / NO — insert a fresh doc for each uploaded run.",
                    "on_happy_path": True, "captured": None, "children": []
                },
                {
                    "name": "save_failure_handler",
                    "type": "except",
                    "line_start": 94, "line_end": 95,
                    "annotation": "Did saving fail? → YES — log and swallow the error; persistence failures must never break a job that already completed.",
                    "on_happy_path": False, "captured": None, "children": []
                }
            ]
        },
        {
            "name": "catalog_and_prebake_helpers",
            "type": "block",
            "line_start": 98, "line_end": 137,
            "annotation": "Three helpers for the song library: load_catalog() reads songs_catalog.json, prebaked_files() queries MongoDB for the set of already-baked songs, load_result() fetches a pre-baked run for instant replay.",
            "on_happy_path": True, "captured": None, "children": []
        },
        {
            "name": "job_state_helpers",
            "type": "block",
            "line_start": 139, "line_end": 144,
            "annotation": "Thread-safe job state management — JOBS dict, RUNNING counter, set_job() and get_job() use a lock so concurrent pipeline threads don't corrupt each other's state.",
            "on_happy_path": True, "captured": None, "children": []
        },
        {
            "name": "audio_series",
            "type": "function",
            "line_start": 147, "line_end": 179,
            "annotation": "Downsample the seven core audio features from the arcs CSV to ~64 points each, normalized to a 1–9 range — this is the data that drives the left-hand graph in the UI.",
            "on_happy_path": True, "captured": None, "children": []
        },
        {
            "name": "run_pipeline",
            "type": "function",
            "line_start": 182, "line_end": 273,
            "annotation": "Run the full two-stage pipeline in a background thread: spawn extract_arcs_hpss.py to analyze the audio, then spawn story_generator.py to infer the emotional arc and write the story, translating JSON events into live job state updates.",
            "on_happy_path": True, "captured": None,
            "children": [
                {
                    "name": "extractor_stage",
                    "type": "block",
                    "line_start": 187, "line_end": 206,
                    "annotation": "Extraction stage — spawn extract_arcs_hpss.py, forward its progress lines as status updates, and verify it produced an arcs CSV.",
                    "on_happy_path": True, "captured": None,
                    "children": [
                        {
                            "name": "extractor_failure",
                            "type": "if",
                            "line_start": 202, "line_end": 204,
                            "annotation": "Did the extractor fail or produce no output? → YES — raise a RuntimeError with the last 1500 chars of its log / NO — continue.",
                            "on_happy_path": False, "captured": None, "children": []
                        }
                    ]
                },
                {
                    "name": "generator_stage",
                    "type": "block",
                    "line_start": 208, "line_end": 268,
                    "annotation": "Generation stage — spawn story_generator.py and translate each JSON event it emits into a live update on the job state dict.",
                    "on_happy_path": True, "captured": None,
                    "children": [
                        {
                            "name": "generator_failure",
                            "type": "if",
                            "line_start": 247, "line_end": 251,
                            "annotation": "Did the generator emit an error or exit non-zero? → YES — raise a RuntimeError / NO — assemble the story and persist.",
                            "on_happy_path": False, "captured": None, "children": []
                        }
                    ]
                },
                {
                    "name": "pipeline_exception_handler",
                    "type": "except",
                    "line_start": 269, "line_end": 272,
                    "annotation": "Did the pipeline raise at any stage? → YES — set the job to 'error' state with the exception message.",
                    "on_happy_path": False, "captured": None, "children": []
                }
            ]
        },
        {
            "name": "Handler",
            "type": "function",
            "line_start": 276, "line_end": 434,
            "annotation": "HTTP request handler — routes GET requests to file/status/library/song/result endpoints and POST requests to upload/process; enforces optional token auth and validates all inputs.",
            "on_happy_path": True, "captured": None,
            "children": [
                {
                    "name": "do_GET_routing",
                    "type": "block",
                    "line_start": 291, "line_end": 319,
                    "annotation": "Route GET requests: / → index.html, /status → job state, /prompts.txt → editable prompt, /library → catalog with ready flags, /result → pre-baked story, /song → catalog mp3 stream.",
                    "on_happy_path": True, "captured": None, "children": []
                },
                {
                    "name": "serve_song_range",
                    "type": "if",
                    "line_start": 328, "line_end": 356,
                    "annotation": "Did the request include a Range header? → YES — serve the requested byte range with a 206 response so the browser audio element can seek / NO — serve the full file.",
                    "on_happy_path": True, "captured": None, "children": []
                },
                {
                    "name": "do_POST_upload",
                    "type": "block",
                    "line_start": 364, "line_end": 382,
                    "annotation": "Handle /upload — validate extension and size, create a unique job directory, and write the audio file.",
                    "on_happy_path": True, "captured": None,
                    "children": [
                        {
                            "name": "upload_validation_failure",
                            "type": "if",
                            "line_start": 370, "line_end": 372,
                            "annotation": "Is the file type not allowed or the size invalid? → YES — return 400 or 413 / NO — proceed.",
                            "on_happy_path": False, "captured": None, "children": []
                        }
                    ]
                },
                {
                    "name": "do_POST_process",
                    "type": "block",
                    "line_start": 384, "line_end": 430,
                    "annotation": "Handle /process — resolve the audio source (library song or upload), check concurrency cap, start the pipeline thread, and return the job_id.",
                    "on_happy_path": True, "captured": None,
                    "children": [
                        {
                            "name": "concurrency_cap",
                            "type": "if",
                            "line_start": 408, "line_end": 412,
                            "annotation": "Is the server at the concurrent job limit? → YES — return 429 / NO — increment RUNNING and start the pipeline.",
                            "on_happy_path": False, "captured": None, "children": []
                        }
                    ]
                }
            ]
        },
        {
            "name": "server_entrypoint",
            "type": "block",
            "line_start": 436, "line_end": 440,
            "annotation": "Entry point — create the uploads directory if needed, print a startup message, and start the ThreadingHTTPServer on localhost.",
            "on_happy_path": True, "captured": None, "children": []
        }
    ]
}


# ── extract_arcs_hpss.py ─────────────────────────────────────────────────────

EXTRACT_ANNOTATIONS = {
    1:   "Module docstring — describes this pure-NumPy audio extractor: decodes via ffmpeg, derives 7 acoustic feature arcs from a single STFT, and writes them to a CSV.",
    14:  "Import sys and os for process I/O, shutil for finding ffmpeg on PATH, subprocess for running it, and time for progress timestamps.",
    15:  "Import numpy — the only non-stdlib dependency; all audio math is done here.",
    17:  "SR — sample rate (22050 Hz); N_FFT — FFT window size (2048 samples); HOP — hop size (2048 = no overlap, matching the old extractor's windowing).",
    21:  "WIN_S — each output window covers 0.5 seconds; DECODE_TIMEOUT — ffmpeg is killed after 3 minutes if it hangs.",
    22:  "_NO_WINDOW — Windows-only subprocess flag that prevents a console window from flashing; zero on other platforms.",
    26:  "_p() — print a progress message tagged with '[extract]' to stderr so server.py can surface it as a live status update.",
    31:  "_ffmpeg_exe() — locate the ffmpeg executable by checking imageio_ffmpeg first, then PATH, then common Windows install locations.",
    32:  "Try imageio_ffmpeg — the preferred source since it ships a bundled binary.",
    38:  "Is imageio_ffmpeg unavailable or its path invalid? → YES — fall back to shutil.which.",
    39:  "Try shutil.which to find ffmpeg on the system PATH.",
    40:  "Is ffmpeg not on PATH? → YES — try common Windows installation paths / NO — return it.",
    46:  "Is ffmpeg nowhere to be found? → YES — return None so load_audio() can raise a descriptive error.",
    49:  "load_audio() — decode an audio file to a mono float64 waveform using ffmpeg.",
    50:  "Is ffmpeg available? → YES — run it / NO — raise a descriptive error telling the user to install imageio-ffmpeg.",
    54:  "Build the ffmpeg command — decode to mono, resample to SR, output raw 32-bit float PCM to stdout.",
    56:  "Run ffmpeg with a 3-minute timeout; capture all output.",
    58:  "Did ffmpeg fail? → YES — raise a RuntimeError with the first 300 chars of its stderr / NO — continue.",
    60:  "Convert the raw bytes to a numpy float64 array.",
    61:  "Did ffmpeg produce no samples? → YES — raise an error (empty or corrupt file) / NO — return the array.",
    67:  "stft_mag() — compute a Short-Time Fourier Transform and return the magnitude spectrogram, frequency bins, and windowed frames.",
    68:  "Create a Hanning window to taper each frame and reduce spectral leakage.",
    69:  "Is the audio shorter than one FFT window? → YES — zero-pad it to length / NO — use as-is.",
    71:  "Compute the number of frames and build an index matrix for efficient frame extraction.",
    72:  "Apply the window to each frame.",
    74:  "Compute the real FFT of all frames at once and take the magnitude.",
    76:  "Compute the frequency bin centers in Hz.",
    77:  "Return the magnitude spectrogram, frequency bins, and windowed frames.",
    80:  "chroma12() — fold FFT magnitude bins into 12 pitch classes (cheap chroma) for harmonic flux computation.",
    82:  "Convert frequency bins to MIDI note numbers.",
    83:  "Map each MIDI note to a pitch class (0–11) by taking mod 12.",
    85:  "Suppress the DC bin (frequency 0) by setting its pitch class to -1.",
    86:  "Accumulate magnitude into a 12-bin chroma matrix.",
    91:  "Normalize each frame's chroma to sum to 1 so absolute loudness doesn't dominate.",
    95:  "windowed() — downsample an array by averaging non-overlapping windows of fpw frames each.",
    96:  "Trim to a multiple of fpw and reshape into windows; return the mean of each window.",
    98:  "Is the array shorter than one window? → YES — return the global mean as a single value / NO — reshape and average.",
    102: "main() — run the full extraction pipeline on one audio file.",
    103: "Start the timer for progress reporting.",
    106: "Decode the audio file to a raw waveform via ffmpeg.",
    108: "Log the decoded duration and start the STFT.",
    110: "Compute the STFT magnitude spectrogram, frequency bins, and frames.",
    113: "Add a small epsilon to prevent log-zero errors in downstream computations.",
    116: "energy — RMS loudness per frame.",
    117: "centroid — spectral centroid (brightness) — the amplitude-weighted mean frequency.",
    118: "flux — spectral flux (frame-to-frame change in spectrum), used as the overall onset rate.",
    121: "hi/lo — frequency band masks: hi (≥3 kHz) captures percussive transients, lo captures harmonic content.",
    123: "perc_onset — onset strength in the high-frequency band — tracks rhythmic/percussive drive.",
    126: "chroma12() — fold the spectrogram into 12 pitch classes.",
    127: "harm_flux — frame-to-frame change in the chroma vector — tracks harmonic movement.",
    130: "Restrict pitch detection to the melody band (80–1000 Hz).",
    132: "For each frame, find the dominant frequency bin within the melody band.",
    133: "melody_f0 — dominant melody pitch in Hz per frame.",
    138: "logm — log-magnitude spectrogram; clip to avoid log(0).",
    140: "contrast — difference between the 90th and 10th percentile of log magnitude per frame — measures spectral clarity.",
    142: "Log the feature computation time and start writing the CSV.",
    143: "fpw — frames per window, converting from the frame rate to the 0.5-second window rate.",
    144: "Average each feature into 0.5-second windows.",
    153: "T — the number of complete windows (the shortest series length).",
    154: "Build the time axis in seconds.",
    156: "Output filename — same base name as the input, with '_arcs.csv' suffix.",
    157: "Write the CSV header and one row per time window.",
    162: "Print the output filename, window count, and total duration.",
    165: "Entry point guard — run main() only when called directly.",
    167: "Is a filename argument missing? → YES — print usage and exit / NO — call main().",
}

EXTRACT_TREE = {
    "name": "extract_arcs_hpss.py",
    "type": "file",
    "children": [
        {
            "name": "module_header",
            "type": "block",
            "line_start": 1, "line_end": 23,
            "annotation": "Module docstring describing the pure-NumPy approach; imports; and constants for sample rate, FFT parameters, window size, and the Windows-only no-console-window flag.",
            "on_happy_path": True, "captured": None, "children": []
        },
        {
            "name": "_p",
            "type": "function",
            "line_start": 26, "line_end": 27,
            "annotation": "Print a '[extract]' prefixed progress message to stderr so server.py can surface each stage as a live status update.",
            "on_happy_path": True, "captured": None, "children": []
        },
        {
            "name": "_ffmpeg_exe",
            "type": "function",
            "line_start": 31, "line_end": 46,
            "annotation": "Locate the ffmpeg executable — tries imageio_ffmpeg first (bundled binary), then PATH, then common Windows install locations. Returns None if not found.",
            "on_happy_path": True, "captured": None,
            "children": [
                {
                    "name": "imageio_ffmpeg_missing",
                    "type": "except",
                    "line_start": 37, "line_end": 38,
                    "annotation": "Is imageio_ffmpeg unavailable or its path invalid? → YES — fall through to shutil.which.",
                    "on_happy_path": False, "captured": None, "children": []
                },
                {
                    "name": "ffmpeg_not_found",
                    "type": "if",
                    "line_start": 46, "line_end": 46,
                    "annotation": "Is ffmpeg nowhere to be found? → YES — return None so the caller can raise a descriptive error.",
                    "on_happy_path": False, "captured": None, "children": []
                }
            ]
        },
        {
            "name": "load_audio",
            "type": "function",
            "line_start": 49, "line_end": 63,
            "annotation": "Decode an audio file to a mono float64 waveform using ffmpeg — bounded at 3 minutes, raises descriptive errors if ffmpeg is missing, fails, or produces no output.",
            "on_happy_path": True, "captured": None,
            "children": [
                {
                    "name": "ffmpeg_missing",
                    "type": "if",
                    "line_start": 50, "line_end": 53,
                    "annotation": "Is ffmpeg not found? → YES — raise a descriptive error telling the user to install imageio-ffmpeg.",
                    "on_happy_path": False, "captured": None, "children": []
                },
                {
                    "name": "ffmpeg_failure",
                    "type": "if",
                    "line_start": 58, "line_end": 59,
                    "annotation": "Did ffmpeg exit with a non-zero code? → YES — raise a RuntimeError with the first 300 chars of ffmpeg's stderr.",
                    "on_happy_path": False, "captured": None, "children": []
                },
                {
                    "name": "empty_output",
                    "type": "if",
                    "line_start": 61, "line_end": 62,
                    "annotation": "Did ffmpeg produce no samples? → YES — raise an error; the file is empty or corrupt.",
                    "on_happy_path": False, "captured": None, "children": []
                }
            ]
        },
        {
            "name": "stft_mag",
            "type": "function",
            "line_start": 67, "line_end": 77,
            "annotation": "Compute the STFT magnitude spectrogram using a Hanning window — returns the magnitude array, frequency bins, and windowed frames. All downstream features are derived from this single STFT.",
            "on_happy_path": True, "captured": None,
            "children": [
                {
                    "name": "short_audio_pad",
                    "type": "if",
                    "line_start": 69, "line_end": 70,
                    "annotation": "Is the audio shorter than one FFT window? → YES — zero-pad it so the STFT has at least one frame.",
                    "on_happy_path": False, "captured": None, "children": []
                }
            ]
        },
        {
            "name": "chroma12",
            "type": "function",
            "line_start": 80, "line_end": 92,
            "annotation": "Fold FFT magnitude bins into 12 pitch classes for harmonic flux computation — converts frequency bins to MIDI pitch classes, accumulates magnitude, and normalizes each frame.",
            "on_happy_path": True, "captured": None, "children": []
        },
        {
            "name": "windowed",
            "type": "function",
            "line_start": 95, "line_end": 99,
            "annotation": "Downsample an array to 0.5-second windows by averaging fpw frames per window — aligns all feature series to the same time axis.",
            "on_happy_path": True, "captured": None, "children": []
        },
        {
            "name": "main",
            "type": "function",
            "line_start": 102, "line_end": 162,
            "annotation": "Run the full extraction pipeline — decode audio, compute a single STFT, derive all 7 feature arcs (energy, centroid, onset, harm_flux, perc_onset, melody_f0, contrast), and write them to a CSV.",
            "on_happy_path": True, "captured": None,
            "children": [
                {
                    "name": "decode_audio",
                    "type": "block",
                    "line_start": 103, "line_end": 110,
                    "annotation": "Decode the audio file to a waveform via ffmpeg, then compute the STFT.",
                    "on_happy_path": True, "captured": None, "children": []
                },
                {
                    "name": "compute_features",
                    "type": "block",
                    "line_start": 113, "line_end": 140,
                    "annotation": "Derive all 7 features from the STFT: RMS energy, spectral centroid, spectral flux (onset), high-band percussive onset, chroma-based harmonic flux, dominant melody pitch, and spectral contrast.",
                    "on_happy_path": True, "captured": None, "children": [
                        {
                            "name": "melody_band_empty",
                            "type": "if",
                            "line_start": 135, "line_end": 136,
                            "annotation": "Are there no frequency bins in the melody band? → YES — set melody_f0 to all zeros / NO — find the dominant bin per frame.",
                            "on_happy_path": False, "captured": None, "children": []
                        }
                    ]
                },
                {
                    "name": "write_csv",
                    "type": "block",
                    "line_start": 142, "line_end": 162,
                    "annotation": "Average each feature into 0.5-second windows, build the time axis, and write the CSV with one row per window.",
                    "on_happy_path": True, "captured": None, "children": []
                }
            ]
        }
    ]
}


# ── build_openings.py ────────────────────────────────────────────────────────

BUILD_OPENINGS_ANNOTATIONS = {
    1:   "Module docstring — describes this seeder: fetches opening pages from Project Gutenberg at run time and upserts them into MongoDB as style exemplars for the writer model.",
    19:  "Import argparse for CLI, hashlib for stable document IDs, os and re for file and text operations, sys for exit, and urllib for HTTP.",
    21:  "MongoDB connection settings — read from environment with defaults.",
    23:  "TARGET_WORDS — target length for the extracted opening page, approximately one printed page.",
    26:  "BOOKS — the curated list of public-domain sci-fi/dark fiction works, each with author, title, Gutenberg id, and a marker phrase where the narrative begins.",
    37:  "gut_urls() — build the two candidate Gutenberg URLs for a given book id (cache mirror first, then the files mirror).",
    41:  "fetch() — download a Gutenberg text by id, trying both URLs; raise a RuntimeError if both fail.",
    52:  "first_page() — extract the opening page from a raw Gutenberg text by finding the narrative start marker and taking whole paragraphs up to TARGET_WORDS.",
    55:  "Find the '*** START OF' marker and discard the Gutenberg header.",
    59:  "Find the narrative start marker, tolerant of line wraps and case differences.",
    61:  "Is the marker not found? → YES — raise a RuntimeError so the book is skipped / NO — continue.",
    64:  "Back up to the start of the line containing the marker.",
    66:  "Walk forward paragraph by paragraph, accumulating text until TARGET_WORDS is reached.",
    76:  "Is the extracted text empty? → YES — raise a RuntimeError / NO — return it.",
    81:  "main() — connect to MongoDB, optionally drop the collection, optionally list existing entries, then fetch and upsert each book.",
    86:  "Connect to MongoDB and ping to verify the connection.",
    88:  "Is MongoDB unreachable? → YES — exit with a descriptive error / NO — continue.",
    93:  "Was --list given? → YES — print each stored opening's author, title, and word count, then exit / NO — continue.",
    97:  "Was --drop given? → YES — drop the collection before loading / NO — skip.",
    100: "For each book in BOOKS, fetch its text, extract the opening page, and upsert it.",
    101: "Did fetch or first_page fail? → YES — print a skip message and continue to the next book / NO — build the document.",
    103: "Build the document — stable _id from a SHA-1 of the title, plus author, title, Gutenberg id, source URL, text, and word count.",
    105: "Upsert the document by _id so re-running is idempotent.",
    107: "Print a success line with the author, title, and word count.",
    108: "Print the final tally.",
}

BUILD_OPENINGS_TREE = {
    "name": "build_openings.py",
    "type": "file",
    "children": [
        {
            "name": "module_header",
            "type": "block",
            "line_start": 1, "line_end": 35,
            "annotation": "Module docstring, imports, MongoDB config constants, and the BOOKS list — five curated public-domain dark/sci-fi works with Gutenberg ids and narrative start markers.",
            "on_happy_path": True, "captured": None, "children": []
        },
        {
            "name": "fetch_utilities",
            "type": "block",
            "line_start": 37, "line_end": 50,
            "annotation": "gut_urls() builds the two candidate Gutenberg URLs for a book id. fetch() tries both and raises if both fail.",
            "on_happy_path": True, "captured": None,
            "children": [
                {
                    "name": "both_urls_failed",
                    "type": "block",
                    "line_start": 48, "line_end": 50,
                    "annotation": "Did both Gutenberg URLs fail? → YES — raise a RuntimeError so the book is skipped gracefully.",
                    "on_happy_path": False, "captured": None, "children": []
                }
            ]
        },
        {
            "name": "first_page",
            "type": "function",
            "line_start": 52, "line_end": 79,
            "annotation": "Extract the opening page from a raw Gutenberg text — find the START marker, locate the narrative start phrase (tolerant of line wraps), then collect whole paragraphs up to TARGET_WORDS.",
            "on_happy_path": True, "captured": None,
            "children": [
                {
                    "name": "marker_not_found",
                    "type": "if",
                    "line_start": 61, "line_end": 62,
                    "annotation": "Is the narrative start marker not found in the text? → YES — raise a RuntimeError so the book is skipped.",
                    "on_happy_path": False, "captured": None, "children": []
                },
                {
                    "name": "empty_result",
                    "type": "if",
                    "line_start": 76, "line_end": 77,
                    "annotation": "Did paragraph extraction produce empty text? → YES — raise a RuntimeError.",
                    "on_happy_path": False, "captured": None, "children": []
                }
            ]
        },
        {
            "name": "main",
            "type": "function",
            "line_start": 81, "line_end": 121,
            "annotation": "CLI entry point — connect to MongoDB, handle --list and --drop flags, then iterate over BOOKS fetching and upserting each opening page.",
            "on_happy_path": True, "captured": None,
            "children": [
                {
                    "name": "mongo_unreachable",
                    "type": "if",
                    "line_start": 88, "line_end": 89,
                    "annotation": "Is MongoDB unreachable? → YES — exit with a descriptive error; this tool requires a live database.",
                    "on_happy_path": False, "captured": None, "children": []
                },
                {
                    "name": "list_mode",
                    "type": "if",
                    "line_start": 93, "line_end": 99,
                    "annotation": "Was --list given? → YES — print stored openings and exit without fetching or writing anything.",
                    "on_happy_path": False, "captured": None, "children": []
                },
                {
                    "name": "drop_mode",
                    "type": "if",
                    "line_start": 97, "line_end": 98,
                    "annotation": "Was --drop given? → YES — drop the collection before loading so it's rebuilt from scratch.",
                    "on_happy_path": False, "captured": None, "children": []
                },
                {
                    "name": "fetch_and_upsert_loop",
                    "type": "loop",
                    "line_start": 100, "line_end": 117,
                    "annotation": "For each book in BOOKS — fetch the Gutenberg text, extract the opening page, build the document, and upsert it by stable _id.",
                    "on_happy_path": True, "captured": None,
                    "children": [
                        {
                            "name": "fetch_failure",
                            "type": "except",
                            "line_start": 101, "line_end": 102,
                            "annotation": "Did fetching or page extraction fail? → YES — print a skip message and continue; one bad book doesn't stop the rest.",
                            "on_happy_path": False, "captured": None, "children": []
                        }
                    ]
                }
            ]
        }
    ]
}


# ── prebake.py ───────────────────────────────────────────────────────────────

PREBAKE_ANNOTATIONS = {
    1:   "Module docstring — describes this batch tool: generates and persists stories for all catalog songs using the real pipeline, so picking a catalog song in the UI is instant.",
    23:  "Import os, sys, uuid for process and id utilities; time and shutil for timing and file copying; argparse for CLI.",
    25:  "Import server — gives access to the real pipeline (run_pipeline, save_story) and catalog helpers without starting the HTTP server.",
    30:  "parse_args() — define and parse CLI arguments: genre filter, substring filter, limit, word count, model tag, author, force re-bake flag, and list-only flag.",
    43:  "select() — filter the catalog down to the songs that need baking this run.",
    44:  "For each song, apply the genre filter, substring filter, and already-baked check.",
    45:  "Is the genre filter active and this song is a different genre? → YES — skip it / NO — continue.",
    46:  "Is the substring filter active and the title/artist doesn't match? → YES — skip it / NO — continue.",
    47:  "Is --force not set and this song is already baked? → YES — skip it / NO — include it.",
    50:  "Apply the --limit cap after filtering.",
    53:  "main() — entry point: load the catalog, filter to the todo list, print a summary, then bake each song.",
    55:  "Load the catalog from songs_catalog.json.",
    57:  "Is the catalog empty? → YES — print a message and return / NO — continue.",
    59:  "Build the set of already-baked songs (empty if --force).",
    60:  "Filter to the songs that need baking this run.",
    62:  "Print the catalog summary and the bake counts.",
    63:  "Was --list given or is the todo list empty? → YES — print the list and return without baking / NO — proceed.",
    68:  "Ensure the uploads root directory exists.",
    70:  "Iterate over the todo list, baking each song synchronously.",
    71:  "Build the source path and a progress header string.",
    72:  "Is the source file missing from disk? → YES — print a skip message and count it as failed / NO — bake it.",
    75:  "Create a unique job directory under uploads/ and copy the song into it.",
    78:  "Call run_pipeline() synchronously — this is the real pipeline, not a subprocess.",
    80:  "Check the job state after the pipeline returns.",
    81:  "Did the job finish with a story? → YES — print timing and char count, increment ok / NO — print the error and increment fail.",
    85:  "Did run_pipeline() raise? → YES — print the exception and increment fail.",
    87:  "Always clean up the temporary job directory after each song.",
    89:  "Print the final tally — ok count, fail count, and total elapsed time.",
}

PREBAKE_TREE = {
    "name": "prebake.py",
    "type": "file",
    "children": [
        {
            "name": "module_header",
            "type": "block",
            "line_start": 1, "line_end": 26,
            "annotation": "Module docstring, imports, and the import of server.py — which gives access to the real pipeline and catalog helpers without starting the HTTP server.",
            "on_happy_path": True, "captured": None, "children": []
        },
        {
            "name": "parse_args",
            "type": "function",
            "line_start": 30, "line_end": 41,
            "annotation": "Define CLI arguments — genre filter, substring filter, limit, word count, model tag, author, --force re-bake, and --list dry-run mode.",
            "on_happy_path": True, "captured": None, "children": []
        },
        {
            "name": "select",
            "type": "function",
            "line_start": 43, "line_end": 56,
            "annotation": "Filter the catalog to the songs that need baking this run — apply genre, substring, already-baked, and limit filters.",
            "on_happy_path": True, "captured": None, "children": []
        },
        {
            "name": "main",
            "type": "function",
            "line_start": 59, "line_end": 116,
            "annotation": "Batch baking loop — load the catalog, filter to the todo list, then for each song create a job directory, call the real pipeline synchronously, and clean up.",
            "on_happy_path": True, "captured": None,
            "children": [
                {
                    "name": "empty_catalog",
                    "type": "if",
                    "line_start": 57, "line_end": 58,
                    "annotation": "Is the catalog empty? → YES — print a message and return; nothing to bake.",
                    "on_happy_path": False, "captured": None, "children": []
                },
                {
                    "name": "list_mode",
                    "type": "if",
                    "line_start": 63, "line_end": 67,
                    "annotation": "Was --list given or is the todo list empty? → YES — print what would be baked and return without running the pipeline.",
                    "on_happy_path": False, "captured": None, "children": []
                },
                {
                    "name": "bake_loop",
                    "type": "loop",
                    "line_start": 70, "line_end": 109,
                    "annotation": "For each song in the todo list — copy it to a temp job dir, call run_pipeline() synchronously, check the result, and clean up.",
                    "on_happy_path": True, "captured": None,
                    "children": [
                        {
                            "name": "missing_file",
                            "type": "if",
                            "line_start": 72, "line_end": 73,
                            "annotation": "Is the source mp3 missing from disk? → YES — print a skip message and count it as failed.",
                            "on_happy_path": False, "captured": None, "children": []
                        },
                        {
                            "name": "pipeline_exception",
                            "type": "except",
                            "line_start": 85, "line_end": 86,
                            "annotation": "Did run_pipeline() raise an unexpected exception? → YES — print the error and count it as failed.",
                            "on_happy_path": False, "captured": None, "children": []
                        },
                        {
                            "name": "cleanup",
                            "type": "block",
                            "line_start": 87, "line_end": 88,
                            "annotation": "Always remove the temporary job directory after each song, success or failure, to keep the uploads folder clean.",
                            "on_happy_path": True, "captured": None, "children": []
                        }
                    ]
                },
                {
                    "name": "final_tally",
                    "type": "block",
                    "line_start": 89, "line_end": 91,
                    "annotation": "Print the final bake results — ok count, fail count, and total elapsed seconds.",
                    "on_happy_path": True, "captured": None, "children": []
                }
            ]
        }
    ]
}


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default=None, help="only seed this file (basename)")
    ap.add_argument("--drop", action="store_true", help="drop Annotations and ControlFlow first")
    args = ap.parse_args()

    print(f"Connecting to {MONGO_URI} -> {DB}")
    database = db()

    if args.drop:
        database["Annotations"].drop()
        database["ControlFlow"].drop()
        print("Dropped Annotations and ControlFlow.")

    files = [
        ("story_generator.py", STORY_GEN_ANNOTATIONS,  STORY_GEN_TREE),
        ("server.py",          SERVER_ANNOTATIONS,      SERVER_TREE),
        ("extract_arcs_hpss.py", EXTRACT_ANNOTATIONS,  EXTRACT_TREE),
        ("build_openings.py",  BUILD_OPENINGS_ANNOTATIONS, BUILD_OPENINGS_TREE),
        ("prebake.py",         PREBAKE_ANNOTATIONS,     PREBAKE_TREE),
    ]

    for filename, annotations, tree in files:
        if args.file and args.file != filename:
            continue
        print(f"\n{filename}")
        upsert_annotations(database, filename, annotations)
        upsert_control_flow(database, filename, tree)

    print("\nDone.")

if __name__ == "__main__":
    main()
