r"""
diag_extract.py — pinpoint WHERE extraction hangs on this machine.

Runs the same librosa stages the real extractor uses, printing each one as it
starts and how long it took. When it stalls, the LAST line printed (a "-> ..."
with no matching time) is the stage that is hanging.

  & "C:\Program Files\Python312\python.exe" diag_extract.py "uploads\<id>\input.mp3"

Also try, to test whether numba's JIT is the culprit:
  $env:NUMBA_DISABLE_JIT=1 ; & "C:\Program Files\Python312\python.exe" diag_extract.py "uploads\<id>\input.mp3"
  (then  Remove-Item Env:\NUMBA_DISABLE_JIT  to undo)
If it COMPLETES only with JIT disabled, the hang is numba, not librosa logic.
"""
import sys, os, time, subprocess
import numpy as np

SR, HOP = 22050, 180  # HOP overwritten below; kept import-light
HOP = 2048

def stamp(msg):
    print(f"   {msg}", flush=True)

def stage(name):
    print(f"-> {name} ...", flush=True)
    return time.time()

def done(t0):
    print(f"   done in {time.time()-t0:.2f}s", flush=True)

def load_audio(path, sr=SR):
    # soundfile first (fast, no subprocess)
    try:
        import soundfile as sf
        stamp(f"soundfile {sf.__version__} | libsndfile {sf.__libsndfile_version__}")
        y, fsr = sf.read(path, dtype="float32", always_2d=True)
        import librosa
        y = y.mean(axis=1)
        if fsr != sr:
            y = librosa.resample(y, orig_sr=fsr, target_sr=sr)
        return np.ascontiguousarray(y, dtype=np.float32)
    except Exception as e:
        stamp(f"soundfile path failed ({type(e).__name__}: {e}); trying ffmpeg")
    cmd = ["ffmpeg","-nostdin","-v","error","-i",path,"-ac","1","-ar",str(sr),"-f","f32le","-"]
    proc = subprocess.run(cmd, capture_output=True, timeout=180)
    if proc.returncode != 0:
        raise RuntimeError("ffmpeg failed: " + proc.stderr.decode("utf-8","replace")[:300])
    return np.frombuffer(proc.stdout, dtype="<f4").copy()

def main(mp3):
    print(f"python {sys.version.split()[0]}  pid {os.getpid()}", flush=True)
    print(f"NUMBA_DISABLE_JIT={os.environ.get('NUMBA_DISABLE_JIT','(unset)')}", flush=True)

    t = stage("import librosa")
    import librosa
    stamp(f"librosa {librosa.__version__}")
    try:
        import numba; stamp(f"numba {numba.__version__}")
    except Exception as e:
        stamp(f"numba import: {e}")
    done(t)

    t = stage("decode audio (load_audio)")
    y = load_audio(mp3, SR); stamp(f"{len(y)} samples = {len(y)/SR:.1f}s"); done(t)

    t = stage("hpss (harmonic/percussive split)")
    yh, yp = librosa.effects.hpss(y); done(t)

    t = stage("rms (energy)");        librosa.feature.rms(y=y, hop_length=HOP); done(t)
    t = stage("spectral_centroid");   librosa.feature.spectral_centroid(y=y, sr=SR, hop_length=HOP); done(t)
    t = stage("spectral_contrast");   librosa.feature.spectral_contrast(y=y, sr=SR, hop_length=HOP); done(t)
    t = stage("onset_strength (perc)"); librosa.onset.onset_strength(y=yp, sr=SR, hop_length=HOP); done(t)
    t = stage("chroma_cqt");          librosa.feature.chroma_cqt(y=yh, sr=SR, hop_length=HOP); done(t)
    t = stage("onset_strength (full)"); librosa.onset.onset_strength(y=y, sr=SR, hop_length=HOP); done(t)
    fmin, fmax = librosa.note_to_hz("C2"), librosa.note_to_hz("C7")
    t = stage("yin (pitch)");         librosa.yin(yh, fmin=fmin, fmax=fmax, sr=SR, hop_length=HOP); done(t)

    print("\nALL STAGES COMPLETED — extraction is healthy on this machine.", flush=True)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit('usage: python diag_extract.py "uploads\\<id>\\input.mp3"')
    main(sys.argv[1])
