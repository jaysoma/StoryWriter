#!/usr/bin/env python3
"""Make a short demo clip so extraction is near-instant on a slow box.
  python make_clip.py [source_audio] [seconds]
Defaults: newest uploads/*/input.mp3, 45 seconds. Writes demo_clip.wav here.
"""
import sys, os, glob
import librosa, soundfile as sf

src = sys.argv[1] if len(sys.argv) > 1 else max(
    glob.glob(os.path.join("uploads", "*", "input.mp3")), key=os.path.getmtime)
secs = float(sys.argv[2]) if len(sys.argv) > 2 else 45.0

y, sr = librosa.load(src, sr=16000, duration=secs)   # decode only the first `secs`
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "demo_clip.wav")
sf.write(out, y, sr)
print(f"wrote {out}  ({len(y)/sr:.1f}s, from {src})")
