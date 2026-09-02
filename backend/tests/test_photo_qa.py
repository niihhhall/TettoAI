"""Photo-QA tests: prove blur / exposure / duplicate detection on generated images.

No network. Uses Pillow to synthesize a sharp (high-frequency) image, a heavily blurred
copy, a near-black frame, and a duplicate, then asserts the classifier flags each.
"""

from __future__ import annotations

import io

from PIL import Image, ImageFilter

from app.services.photo_qa import assess, dhash, _grayscale


def _png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


# High-frequency noise = sharp; a Gaussian blur destroys the high frequencies.
_NOISE = Image.effect_noise((160, 160), 90).convert("L")
SHARP = _png(_NOISE)
BLURRY = _png(_NOISE.filter(ImageFilter.GaussianBlur(8)))
DARK = _png(Image.new("L", (160, 160), 8))
# A near-featureless frame — reliably below any sharpness threshold.
FLAT = _png(Image.new("L", (160, 160), 120))


def test_sharp_photo_passes():
    qc = assess(SHARP)
    assert qc.ok, qc.reasons
    assert qc.blur >= 100.0


def test_blur_metric_drops_when_blurred():
    # Mechanism check independent of the (camera-tunable) threshold: blurring lowers sharpness.
    assert assess(SHARP).blur > assess(BLURRY).blur


def test_low_detail_photo_flagged_blurry():
    # A featureless/out-of-focus frame has no edges -> below threshold -> rejected.
    assert "blurry" in assess(FLAT).reasons


def test_dark_photo_flagged():
    assert "too dark" in assess(DARK).reasons


def test_duplicate_detected():
    first = dhash(_grayscale(SHARP))
    qc = assess(SHARP, seen_hashes=[first])
    assert "duplicate" in qc.reasons


def test_distinct_photo_not_duplicate():
    other = dhash(_grayscale(DARK))
    qc = assess(SHARP, seen_hashes=[other])
    assert "duplicate" not in qc.reasons


def test_unreadable_bytes_rejected():
    qc = assess(b"not an image")
    assert not qc.ok and "unreadable image" in qc.reasons
