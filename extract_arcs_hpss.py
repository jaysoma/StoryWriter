r"""
Pure-NumPy arc extractor - no librosa, no scipy, no numba.

Decodes via a bounded ffmpeg subprocess, then derives the same 7 arcs the rest of
StoryWriter expects from ONE numpy STFT. Nothing here can hang: ffmpeg is bounded,
and numpy's FFT is a fixed-cost operation. This replaces the librosa pipeline whose
hpss/yin calls wedge on some Windows builds.

Columns (unchanged): time_s,energy,centroid,onset,harm_flux,perc_onset,melody_f0,contrast

  python extract_arcs_hpss.py "track.mp3"
Output: <track>_arcs.csv
"""
import sys, os, shutil, subprocess, time
import numpy as np

SR = 22050
N_FFT = 2048
HOP = 2048           # frame rate kept == old extractor so windowing math is identical
WIN_S = 0.5
DECODE_TIMEOUT = 180
# Suppress the console window the ffmpeg child would otherwise flash on Windows
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


def _p(msg):
    print("[extract] " + msg, file=sys.stderr, flush=True)


# ---- decode (bounded ffmpeg; never hangs) -----------------------------------
def _ffmpeg_exe():
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and os.path.exists(exe):
            return exe
    except Exception:
        pass
    onpath = shutil.which("ffmpeg")
    if onpath:
        return onpath
    for c in (r"C:\ffmpeg\bin\ffmpeg.exe", r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
              os.path.expanduser(r"~\ffmpeg\bin\ffmpeg.exe")):
        if os.path.exists(c):
            return c
    return None


def load_audio(path, sr=SR):
    exe = _ffmpeg_exe()
    if not exe:
        raise RuntimeError("No ffmpeg found. Fix: "
                           'pip install imageio-ffmpeg  in the backend interpreter.')
    cmd = [exe, "-nostdin", "-v", "error", "-i", path,
           "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"]
    proc = subprocess.run(cmd, capture_output=True, timeout=DECODE_TIMEOUT,
                          creationflags=_NO_WINDOW)
    if proc.returncode != 0:
        raise RuntimeError("ffmpeg failed: " + proc.stderr.decode("utf-8", "replace")[:300])
    y = np.frombuffer(proc.stdout, dtype="<f4").astype(np.float64).copy()
    if not y.size:
        raise RuntimeError("ffmpeg produced no samples")
    return y


# ---- one STFT, all features from it -----------------------------------------
def stft_mag(y, n_fft=N_FFT, hop=HOP):
    win = np.hanning(n_fft).astype(np.float64)
    if len(y) < n_fft:
        y = np.pad(y, (0, n_fft - len(y)))
    n_frames = 1 + (len(y) - n_fft) // hop
    idx = np.arange(n_fft)[None, :] + hop * np.arange(n_frames)[:, None]
    frames = y[idx] * win                      # (n_frames, n_fft)
    spec = np.fft.rfft(frames, axis=1)
    mag = np.abs(spec)                          # (n_frames, n_bins)
    freqs = np.fft.rfftfreq(n_fft, 1.0 / SR)    # (n_bins,)
    return mag, freqs, frames


def chroma12(mag, freqs):
    """Fold FFT bins into 12 pitch classes (cheap chroma)."""
    f = np.where(freqs > 0, freqs, 1.0)
    midi = 69 + 12 * np.log2(f / 440.0)
    pc = np.mod(np.round(midi).astype(int), 12)
    pc[freqs <= 0] = -1
    C = np.zeros((mag.shape[0], 12))
    for k in range(12):
        sel = pc == k
        if sel.any():
            C[:, k] = mag[:, sel].sum(axis=1)
    nrm = C.sum(axis=1, keepdims=True)
    return C / np.where(nrm > 0, nrm, 1.0)


def windowed(arr, fpw):
    n = (len(arr) // fpw) * fpw
    if n == 0:
        return np.array([float(np.nanmean(arr))]) if len(arr) else np.array([0.0])
    return np.nanmean(arr[:n].reshape(-1, fpw), axis=1)


def main(mp3):
    t0 = time.time()
    lap = lambda m: _p("%s  (+%.1fs)" % (m, time.time() - t0))

    _p("decoding audio (ffmpeg)...")
    y = load_audio(mp3, SR)
    lap("decoded %.0fs; computing STFT..." % (len(y) / SR))

    mag, freqs, frames = stft_mag(y)
    lap("STFT done; deriving features...")

    eps = 1e-9
    msum = mag.sum(axis=1) + eps

    energy   = np.sqrt((frames ** 2).mean(axis=1))                 # RMS per frame
    centroid = (mag * freqs[None, :]).sum(axis=1) / msum           # brightness
    flux     = np.sqrt((np.diff(mag, axis=0, prepend=mag[:1]) .clip(min=0) ** 2).sum(axis=1))
    onset    = flux                                                # overall attack rate

    hi = freqs >= 3000.0                                           # percussive energy lives high
    lo = (freqs > 0) & (freqs < 3000.0)
    perc_flux = np.diff(mag[:, hi], axis=0, prepend=mag[:1, hi]).clip(min=0).sum(axis=1)
    perc_onset = perc_flux

    C = chroma12(mag, freqs)
    harm_flux = np.sqrt((np.diff(C, axis=0, prepend=C[:1]) ** 2).sum(axis=1))   # harmonic movement

    # melody pitch: dominant bin within a melody band (80-1000 Hz)
    band = (freqs >= 80.0) & (freqs <= 1000.0)
    bidx = np.where(band)[0]
    if bidx.size:
        dom = bidx[np.argmax(mag[:, band], axis=1)]
        melody_f0 = freqs[dom]
    else:
        melody_f0 = np.zeros(mag.shape[0])

    # spectral contrast: spread between loud and quiet bins (log domain)
    logm = np.log(mag + eps)
    contrast = np.percentile(logm, 90, axis=1) - np.percentile(logm, 10, axis=1)

    lap("features done; writing csv...")
    fpw = max(1, int(round(WIN_S * SR / HOP)))
    cols = {
        "energy":     windowed(energy, fpw),
        "centroid":   windowed(centroid, fpw),
        "onset":      windowed(onset, fpw),
        "harm_flux":  windowed(harm_flux, fpw),
        "perc_onset": windowed(perc_onset, fpw),
        "melody_f0":  windowed(melody_f0, fpw),
        "contrast":   windowed(contrast, fpw),
    }
    T = min(len(v) for v in cols.values())
    time_s = np.arange(T) * WIN_S
    order = ["energy", "centroid", "onset", "harm_flux", "perc_onset", "melody_f0", "contrast"]
    out = os.path.splitext(os.path.basename(mp3))[0] + "_arcs.csv"
    with open(out, "w") as f:
        f.write("time_s," + ",".join(order) + "\n")
        for i in range(T):
            row = [f"{time_s[i]:.2f}"] + [f"{cols[c][i]:.5f}" for c in order]
            f.write(",".join(row) + "\n")
    print("wrote %s  (%d windows, %ds)" % (out, T, int(T * WIN_S)))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("usage: python extract_arcs_hpss.py <track.mp3>")
    main(sys.argv[1])
