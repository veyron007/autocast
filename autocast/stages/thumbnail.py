"""Stage: thumbnail — 1280x720 JPG with big stroked text (Pillow).

Reads `spine.topic`, writes `spine.thumbnail`. Composition beats end-to-end AI:
a base color/frame + large high-contrast stroked text is what a CTR thumbnail
needs. Implemented for real when Pillow is available; otherwise a stub that
touches the file so the pipeline shape holds.

Specs (research §7): 1280x720, max 2 MB, JPG q~85.
"""

from __future__ import annotations

import logging
from pathlib import Path

from autocast.config import Config
from autocast.spine import Run, Thumbnail

log = logging.getLogger("autocast.stages.thumbnail")

STAGE = "thumbnail"
_W, _H = 1280, 720


def _compose_with_pillow(out_path: Path, title: str) -> bool:
    """Return True if Pillow was available and composed a real thumbnail."""
    try:
        from PIL import Image, ImageDraw, ImageFont  # type: ignore
    except Exception:  # noqa: BLE001 - Pillow optional
        return False

    img = Image.new("RGB", (_W, _H), (18, 20, 28))
    draw = ImageDraw.Draw(img)

    # Accent bar for depth/hierarchy (not a flat centered blob).
    draw.rectangle([0, _H - 90, _W, _H], fill=(230, 90, 60))

    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 96)
    except Exception:  # noqa: BLE001 - fall back to default bitmap font
        font = ImageFont.load_default()

    # Wrap the title to ~2 lines by word count.
    words = title.split()
    mid = (len(words) + 1) // 2
    lines = [" ".join(words[:mid]), " ".join(words[mid:])] if len(words) > 4 else [title]

    y = 180
    for line in lines:
        draw.text(
            (70, y),
            line,
            font=font,
            fill=(255, 255, 255),
            stroke_width=8,
            stroke_fill=(0, 0, 0),
        )
        y += 120

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "JPEG", quality=85)
    return True


def run(spine: Run, cfg: Config, *, dry_run: bool = False) -> Run:
    if spine.topic is None:
        raise ValueError("thumbnail stage: spine.topic missing (run topic first)")

    out_abs = cfg.assets_dir(spine.run_id) / "thumb.jpg"
    composed = _compose_with_pillow(out_abs, spine.topic.title)

    if not composed:
        # TODO(real): a stub thumbnail file keeps the pipeline shape without Pillow.
        out_abs.parent.mkdir(parents=True, exist_ok=True)
        out_abs.touch()
        log.warning("thumbnail: Pillow unavailable; touched stub %s", out_abs.name)

    spine.thumbnail = Thumbnail(path="assets/thumb.jpg", width=_W, height=_H)
    log.info("thumbnail: %s (pillow=%s)", spine.thumbnail.path, composed)
    return spine
