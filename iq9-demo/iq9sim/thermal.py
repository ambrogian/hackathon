"""Thermal frame simulator: real temperatures (deg C) per pixel at 32x24."""
import numpy as np

from .geometry import H, W


def _blur(a):
    k = np.array([1, 4, 6, 4, 1], float) / 16
    ap = np.pad(a, 2, mode="edge")
    t = sum(k[i] * ap[:, i:i + a.shape[1]] for i in range(5))
    return sum(k[i] * t[i:i + a.shape[0], :] for i in range(5))


def render(comps, ambient, hot, noise_c, rng):
    """comps: [(Component, rise_c)]; hot: [(cx, cy, delta_c, sigma_px)]. Hot spots are added after the
    optics blur, so the injected delta is what the centre pixel shows."""
    yy, xx = np.mgrid[0:H, 0:W]
    T = np.full((H, W), ambient, float)
    for c, rise in comps:
        m = (np.abs(xx - c.cx) <= c.w / 2) & (np.abs(yy - c.cy) <= c.h / 2)
        T[m] += rise
    T = _blur(T)
    for cx, cy, d, s in hot:
        T += d * np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * s * s))
    return T + rng.normal(0, noise_c, T.shape)
