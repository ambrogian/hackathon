#!/usr/bin/env python3
"""Generate augmented demo images. Re-runnable (seeded). Run with the repo .venv python.
Outputs to ./augmented/ . Augmentations are for demo/testing only, not ground truth."""
import io, os, subprocess, random, json
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
TH = os.path.abspath(os.path.join(HERE, "..", ".."))
OUT = os.path.join(HERE, "augmented")
os.makedirs(OUT, exist_ok=True)
Q = 90
SZ = (1280, 720)
VIDEOS = [("good", "working_machine.mp4", 5.066), ("bad", "failure.mp4", 1.005), ("line", "demo/line.mp4", 10.027)]
STILLS = {"good": "working_machine_50.jpg", "bad": "failure_50.jpg"}
rng = np.random.default_rng(42)
random.seed(42)
manifest = []  # (filename, label, how)

def save(img, name, label, how, q=Q):
    img.convert("RGB").save(os.path.join(OUT, name), quality=q)
    manifest.append((name, label, how))

# 1. real frames: 8 evenly spaced (midpoints of 8 equal segments)
for tag, vid, dur in VIDEOS:
    label = {"good": "GOOD", "bad": "BAD", "line": "UNLABELLED (demo line video)"}[tag]
    for i in range(8):
        t = dur * (i + 0.5) / 8
        name = f"{tag}_v{i+1:02d}.jpg"
        tmp = os.path.join(OUT, "_tmp.png")
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.3f}", "-i", os.path.join(TH, vid),
                        "-frames:v", "1", "-vf", "scale=1280:720", tmp], check=True)
        save(Image.open(tmp), name, label, f"real frame of {vid} at t={t:.3f}s (of {dur}s), scaled 1280x720, q{Q}")
        os.remove(tmp)

# 2. augmentations
def bright(im, f): return ImageEnhance.Brightness(im).enhance(f)
def noise(im):
    a = np.asarray(im).astype(np.float32) + rng.normal(0, 12, (im.height, im.width, 1)).astype(np.float32) * 0 + rng.normal(0, 12, (im.height, im.width, 3))
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
def rot(im, d): return im.rotate(d, resample=Image.BICUBIC, expand=False, fillcolor=(0, 0, 0))
def crop85(im):
    w, h = im.size; cw, ch = int(w * .85), int(h * .85); x, y = (w - cw) // 2, (h - ch) // 2
    return im.crop((x, y, x + cw, y + ch)).resize(im.size, Image.LANCZOS)
def hshift(im):
    a = np.asarray(im); s = int(im.width * .05); o = np.empty_like(a); o[:, s:] = a[:, :-s]; o[:, :s] = a[:, :1]  # replicate edge
    return Image.fromarray(o)
def warm(im):
    a = np.asarray(ImageEnhance.Brightness(im).enhance(0.7)).astype(np.float32) * np.array([1.12, 0.97, 0.75])
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
AUGS = [
    ("bright-25", lambda im: bright(im, .75), "brightness x0.75 (PIL Brightness)"),
    ("bright+20", lambda im: bright(im, 1.20), "brightness x1.20 (PIL Brightness)"),
    ("contrast-low", lambda im: ImageEnhance.Contrast(im).enhance(.6), "contrast x0.60 (PIL Contrast)"),
    ("blur", lambda im: im.filter(ImageFilter.GaussianBlur(2.0)), "Gaussian blur radius 2.0"),
    ("noise", noise, "additive Gaussian per-pixel-per-channel noise sigma=12 (seed 42)"),
    ("rot-4", lambda im: rot(im, -4), "rotate -4 deg (clockwise), bicubic, black corners"),
    ("rot+4", lambda im: rot(im, 4), "rotate +4 deg (counter-clockwise), bicubic, black corners"),
    ("crop85", crop85, "center 85% crop resized back to 1280x720 (Lanczos)"),
    ("shift5", hshift, "horizontal shift right by 64 px (5%), left edge replicated"),
    ("jpeg-q20", None, "re-encoded at JPEG quality 20"),
    ("dimwarm", warm, "brightness x0.70 then RGB gain (1.12, 0.97, 0.75): dim warm factory light"),
]
for tag, fn in STILLS.items():
    base = Image.open(os.path.join(HERE, fn)).convert("RGB").resize(SZ, Image.LANCZOS)
    lab = tag.upper()
    for suf, f, how in AUGS:
        name = f"{tag}_50_{suf}.jpg"
        if suf == "jpeg-q20":
            save(base, name, lab, f"from {fn}: {how}", q=20)
        else:
            save(f(base), name, lab, f"from {fn}: {how}, saved q{Q}")

# 3. synthetic defects from GOOD still
good = Image.open(os.path.join(HERE, STILLS["good"])).convert("RGB").resize(SZ, Image.LANCZOS)
# approximate sheet polygon (hand-measured on working_machine_50, 1280x720)
TOP = ([0, 560, 1000, 1280], [395, 370, 355, 400])
BOT = ([0, 400, 800, 1280], [570, 520, 470, 415])
def sheet_y(x, f): return (1 - f) * np.interp(x, *TOP) + f * np.interp(x, *BOT)
def sheet_mask():
    m = Image.new("L", SZ, 0); d = ImageDraw.Draw(m)
    xs = list(range(0, 1281, 20))
    d.polygon([(x, float(np.interp(x, *TOP))) for x in xs] + [(x, float(np.interp(x, *BOT))) for x in xs[::-1]], fill=255)
    return m
MASK = sheet_mask()
# exclude the vertical post (x~255-390) occluding the sheet
ImageDraw.Draw(MASK).rectangle((255, 0, 390, 720), fill=0)

def scratch(im):
    ov = Image.new("RGBA", SZ, (0, 0, 0, 0)); d = ImageDraw.Draw(ov)
    for f in (0.22, 0.47, 0.71):
        xs = np.arange(400, 1240, 10)
        pts = [(float(x), float(sheet_y(x, f))) for x in xs]
        d.line(pts, fill=(245, 248, 255, 150), width=2)
    ov = ov.filter(ImageFilter.GaussianBlur(0.7))
    a = ov.split()[3].point(lambda v: v)
    ov.putalpha(Image.fromarray(np.minimum(np.asarray(a), np.asarray(MASK))))
    return Image.alpha_composite(im.convert("RGBA"), ov)
def specks(im):
    r = np.random.default_rng(7); ov = Image.new("RGBA", SZ, (0, 0, 0, 0)); d = ImageDraw.Draw(ov); n = 0
    while n < 28:
        x, y = int(r.integers(400, 1240)), int(r.integers(330, 560))
        if MASK.getpixel((x, y)) == 0: continue
        rad = float(r.uniform(1.2, 3.0)); d.ellipse((x - rad, y - rad, x + rad, y + rad), fill=(20, 20, 25, 215)); n += 1
    return Image.alpha_composite(im.convert("RGBA"), ov.filter(ImageFilter.GaussianBlur(0.6)))
def yellow(im):
    a = np.asarray(im).astype(np.float32); m = np.asarray(MASK.filter(ImageFilter.GaussianBlur(4))).astype(np.float32)[..., None] / 255
    y = a * np.array([1.10, 1.02, 0.50])
    return Image.fromarray(np.clip(a * (1 - .8 * m) + y * .8 * m, 0, 255).astype(np.uint8))
SYN = [
    ("SYN-scratch", scratch, "GOOD", "3 thin bright lines (RGBA 245,248,255 alpha 150, width 2, blur 0.7) along sheet direction at 22/47/71% between sheet edges, x=400..1240, clipped to hand-drawn sheet mask"),
    ("SYN-blackspecks", specks, "GOOD", "28 dark specks (RGBA 20,20,25 alpha 215, radius 1.2-3.0 px, blur 0.6) at random positions inside sheet mask (seed 7)"),
    ("SYN-yellowing", yellow, "GOOD", "sheet-area mask (feather blur 4) blended 80% with RGB gain (1.10, 1.02, 0.50)"),
]
for suf, f, _, how in SYN:
    save(f(good), f"good_50_{suf}.jpg", f"SYNTHETIC-DEFECT ({suf[4:]})", f"from {STILLS['good']}: {how}; saved q{Q}")

# 4. contact sheet + README
from PIL import ImageFont
names = [m[0] for m in manifest]
cols, tw, th_, pad = 6, 320, 180, 22
rows = (len(names) + cols - 1) // cols
cs = Image.new("RGB", (cols * tw, rows * (th_ + pad)), (25, 25, 25)); d = ImageDraw.Draw(cs)
try: font = ImageFont.load_default(size=13)
except TypeError: font = ImageFont.load_default()
for i, n in enumerate(names):
    t = Image.open(os.path.join(OUT, n)).convert("RGB").resize((tw, th_))
    x, y = (i % cols) * tw, (i // cols) * (th_ + pad)
    cs.paste(t, (x, y + pad)); d.text((x + 3, y + 3), n, fill=(255, 255, 255), font=font)
cs.save(os.path.join(OUT, "_contact_sheet.jpg"), quality=85)

with open(os.path.join(OUT, "README.md"), "w") as f:
    f.write("# Augmented demo images\n\nGenerated by `../make_augmented.py` (seeded, re-runnable). All 1280x720 JPEG (q90 unless noted).\n\n"
            "**These are for demo/testing only and are NOT ground truth.** Labels are inherited from the source frame; "
            "augmentations may make a GOOD frame look unlike real production data, and SYNTHETIC-DEFECT images are drawn "
            "artefacts, not real defects. `line_vNN` frames have no label.\n\n"
            "| File | Intended label | How made |\n|---|---|---|\n")
    for n, l, h in manifest:
        f.write(f"| {n} | {l} | {h} |\n")
print(len(manifest), "images")
