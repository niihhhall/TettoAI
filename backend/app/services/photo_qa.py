"""Field-photo quality control (PRD State 3): blur, exposure, and duplicate detection.

These are classical computer-vision checks — NOT an LLM. They are fast, deterministic,
free, and reliable, which is exactly what you want for exposure/blur/duplicate gating:

  * Blur      — variance of the Laplacian (low variance == few sharp edges == blurry).
  * Exposure  — mean luminance (too dark / blown out).
  * Duplicate — dHash perceptual hash + Hamming distance vs already-accepted photos.

A vision LLM would only be warranted for *semantic* checks (e.g. "is this a roof, is the
damage visible") — a separate, optional upgrade, not needed for these three gates.

Pure-Pillow implementation (no numpy/OpenCV) to keep the dependency surface small.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field

from PIL import Image, ImageFilter, ImageStat

# Default thresholds. NOTE: this uses Pillow's Kernel filter, which clamps the Laplacian to
# 0-255, so the variance scale is much smaller than OpenCV's float Laplacian — a threshold of
# ~10-15 here is roughly OpenCV's ~100. WhatsApp also recompresses photos, further lowering
# sharpness, so the blur floor is intentionally low to avoid rejecting real field photos.
# These are overridable per-call (RealServices passes the values from Settings/.env).
BLUR_VARIANCE_MIN = 12.0    # below this the image is treated as blurry
DARK_MEAN_MAX = 20.0        # mean luminance below this = too dark
BRIGHT_MEAN_MIN = 245.0     # mean luminance above this = blown out
DUP_HAMMING_MAX = 5         # dHash Hamming distance <= this = duplicate

_LAPLACIAN = ImageFilter.Kernel((3, 3), [0, 1, 0, 1, -4, 1, 0, 1, 0], scale=1)


def _grayscale(image_bytes: bytes) -> Image.Image:
    return Image.open(io.BytesIO(image_bytes)).convert("L")


def blur_variance(gray: Image.Image) -> float:
    """Variance of the Laplacian — the standard focus/sharpness measure.

    Pillow copies the 1px border through the kernel unfiltered, which would inflate the
    variance on low-detail images, so we crop the border before measuring.
    """
    lap = gray.filter(_LAPLACIAN)
    w, h = lap.size
    if w > 2 and h > 2:
        lap = lap.crop((1, 1, w - 1, h - 1))
    return float(ImageStat.Stat(lap).var[0])


def mean_luminance(gray: Image.Image) -> float:
    return float(ImageStat.Stat(gray).mean[0])


def dhash(gray: Image.Image, hash_size: int = 8) -> int:
    """Difference hash: resize to (hash_size+1 x hash_size), compare adjacent columns."""
    small = gray.resize((hash_size + 1, hash_size))
    px = list(small.getdata())
    w = hash_size + 1
    bits = 0
    for row in range(hash_size):
        for col in range(hash_size):
            left = px[row * w + col]
            right = px[row * w + col + 1]
            bits = (bits << 1) | (1 if left > right else 0)
    return bits


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


@dataclass
class PhotoQC:
    ok: bool
    blur: float
    brightness: float
    dhash: int
    reasons: list[str] = field(default_factory=list)


def assess(image_bytes: bytes, seen_hashes: list[int] | tuple[int, ...] = (), *,
           blur_min: float = BLUR_VARIANCE_MIN, dark_max: float = DARK_MEAN_MAX,
           bright_min: float = BRIGHT_MEAN_MIN, dup_hamming: int = DUP_HAMMING_MAX) -> PhotoQC:
    """Assess one photo. `seen_hashes` are dHashes of already-accepted photos this session.
    Thresholds are injectable so they can be tuned from Settings/.env without a code change."""
    try:
        gray = _grayscale(image_bytes)
    except Exception:
        return PhotoQC(ok=False, blur=0.0, brightness=0.0, dhash=0, reasons=["unreadable image"])

    bv = blur_variance(gray)
    lum = mean_luminance(gray)
    h = dhash(gray)

    reasons: list[str] = []
    if bv < blur_min:
        reasons.append("blurry")
    if lum < dark_max:
        reasons.append("too dark")
    if lum > bright_min:
        reasons.append("overexposed")
    if any(hamming(h, prev) <= dup_hamming for prev in seen_hashes):
        reasons.append("duplicate")

    return PhotoQC(ok=not reasons, blur=bv, brightness=lum, dhash=h, reasons=reasons)
