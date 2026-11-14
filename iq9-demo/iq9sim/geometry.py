"""Shared sensor geometry: 32x24 thermal imager (MLX90640-like) and 4x4 MEMS mic array (UMA-16 layout)."""
import numpy as np

FS = 48_000          # mic sample rate, Hz
C_SOUND = 343.0      # m/s
W, H = 32, 24        # thermal pixels
FOV_H, FOV_V = 55.0, 35.0
MIC_PITCH = 0.042    # m
SRC_DIST = 1.5       # m, camera to equipment


def pix_to_angles(x, y):
    """Pixel (column, row) to (azimuth, elevation) in degrees; acoustic grid uses the same pixels."""
    return (x / (W - 1) - 0.5) * FOV_H, -(y / (H - 1) - 0.5) * FOV_V


def angles_to_dir(az, el):
    az, el = np.radians(az), np.radians(el)
    return np.stack([np.sin(az) * np.cos(el), np.sin(el), np.cos(az) * np.cos(el)], axis=-1)


def mic_positions():
    k = (np.arange(4) - 1.5) * MIC_PITCH
    gx, gy = np.meshgrid(k, k)
    return np.stack([gx.ravel(), gy.ravel(), np.zeros(16)], axis=1)


def pixel_dirs():
    """Unit vectors for every pixel, row-major (H*W, 3)."""
    yy, xx = np.mgrid[0:H, 0:W]
    az, el = pix_to_angles(xx.ravel(), yy.ravel())
    return angles_to_dir(az, el)
