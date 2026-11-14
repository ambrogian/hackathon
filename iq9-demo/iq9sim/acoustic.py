"""16-mic array: source simulation (true spherical delays) and our own delay-and-sum beamformer."""
import functools

import numpy as np

from .geometry import (C_SOUND, FS, H, SRC_DIST, W, angles_to_dir, mic_positions, pix_to_angles,
                       pixel_dirs)

BAND = (2000.0, 6000.0)
NFFT = 1024


def _signal(kind, n, rng):
    if kind == "hiss":            # air leak: steady broadband noise
        s, lo, hi = rng.normal(size=n), 2000, 12000
    elif kind == "pd":            # partial discharge: sparse impulsive crackle
        s = np.zeros(n)
        k = rng.poisson(n * 800 / FS)
        np.add.at(s, rng.integers(0, n, k), rng.lognormal(0, 0.8, k) * rng.choice([-1, 1], k))
        lo, hi = 1000, 20000
    else:
        raise ValueError(kind)
    S = np.fft.rfft(s)
    f = np.fft.rfftfreq(n, 1 / FS)
    S[(f < lo) | (f > hi)] = 0
    s = np.fft.irfft(S, n)
    return s / s.std()


def simulate_mics(sources, rng, n=8192):
    """Returns (16, n). Per-mic broadband SNR of each source is source.snr_db (noise sigma = 1)."""
    mics = mic_positions()
    f = np.fft.rfftfreq(n, 1 / FS)
    X = np.zeros((16, f.size), complex)
    for s in sources:
        S = np.fft.rfft(_signal(s.kind, n, rng))
        az, el = pix_to_angles(s.x, s.y)
        r = np.linalg.norm(SRC_DIST * angles_to_dir(az, el) - mics, axis=1)
        X += S[None, :] * np.exp(-2j * np.pi * f[None, :] * (r / C_SOUND)[:, None]) \
            * (10 ** (s.snr_db / 20) * SRC_DIST / r)[:, None]
    x = np.fft.irfft(X, n, axis=1) if sources else np.zeros((16, n))
    return x + rng.normal(0, 1.0, (16, n))


@functools.lru_cache(maxsize=4)
def _steering(nfft, band):
    f = np.fft.rfftfreq(nfft, 1 / FS)
    sel = (f >= band[0]) & (f <= band[1])
    tau = pixel_dirs() @ mic_positions().T / C_SOUND                      # (G, M)
    return sel, np.exp(2j * np.pi * f[sel][:, None, None] * tau[None])   # (F, G, M)


def analyze(x, band=BAND, nfft=NFFT):
    """Steered-response power map (cross-spectral matrix, diagonal removed so sensor noise cancels).
    coherence = peak coherent power / mean per-mic power: ~0 for noise only, up to ~0.94 for a clean source."""
    M, n = x.shape
    T = n // nfft
    X = np.fft.rfft(x[:, :T * nfft].reshape(M, T, nfft) * np.hanning(nfft), axis=2)
    sel, Wf = _steering(nfft, band)
    Xb = X[:, :, sel]
    R = np.einsum("mtf,ntf->fmn", Xb, Xb.conj()) / T
    diag = np.real(np.einsum("fmm->f", R)) / M
    R[:, np.arange(M), np.arange(M)] = 0
    V = Wf @ R.transpose(0, 2, 1)
    p = np.real(np.einsum("fgm,fgm->g", Wf.conj(), V)) / (M * M)
    coh = p / diag.sum()
    gi = int(np.argmax(coh))
    row, col = divmod(gi, W)
    # beamformed time series at the peak: impulsive (crackle) vs steady (hiss)
    ff = np.fft.rfftfreq(n, 1 / FS)
    a = np.exp(2j * np.pi * ff[None, :] * ((mic_positions() @ pixel_dirs()[gi]) / C_SOUND)[:, None])
    y = (a.conj() * np.fft.rfft(x, axis=1)).sum(0) / M
    y[(ff < band[0]) | (ff > band[1])] = 0
    y = np.fft.irfft(y, n)
    kurt = float(np.mean((y - y.mean()) ** 4) / (y.var() ** 2 + 1e-30))
    return {"map": np.clip(coh / max(coh.max(), 1e-12), 0, 1).reshape(H, W),
            "coherence": float(coh[gi]), "px": (int(col), int(row)), "kurtosis": kurt}
