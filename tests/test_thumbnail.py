"""Thumbnail stage: composition, auto-fit, hero compositing, and hard limits.

These guard the CTR asset the way the seed/caption tests guard content: the
thumbnail must be a real 1280x720 JPG, must never overflow the canvas on a long
title, must use the film's own hero frame when present, and must stay under the
2 MB spec cap.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PIL")

from PIL import Image  # noqa: E402

from autocast.config import Config  # noqa: E402
from autocast.spine import Run, Shot, Thumbnail, Topic  # noqa: E402
from autocast.stages import thumbnail  # noqa: E402


def _spine(title: str, *, with_hero: bool = False, cfg: Config | None = None) -> Run:
    run = Run.new("2026-07-22")
    run.topic = Topic(title=title)
    if with_hero:
        assert cfg is not None
        run.shots = [
            Shot(idx=0, narration="n", image_prompt="p", duration_s=5.0, image_path="assets/shot_000.png")
        ]
    return run


def _write_hero(cfg: Config, run_id: str) -> None:
    """A vivid pure-red hero frame so 'was the hero used?' is testable — no
    gradient fallback or scrim ever produces a bright (r>90, g=b=0) red."""
    assets = cfg.assets_dir(run_id)
    assets.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (1920, 1080), (255, 0, 0)).save(assets / "shot_000.png")


def test_composes_real_jpg_of_exact_dimensions(tmp_path):
    cfg = Config(runs_dir=tmp_path)
    spine = _spine("Roman Concrete Still Baffles Engineers")
    thumbnail.run(spine, cfg)

    out = cfg.assets_dir(spine.run_id) / "thumb.jpg"
    assert out.exists() and out.stat().st_size > 0
    with Image.open(out) as img:
        assert img.format == "JPEG"
        assert img.size == (1280, 720)
    assert spine.thumbnail == Thumbnail(path="assets/thumb.jpg", width=1280, height=720)


def test_long_title_autofits_without_overflow(tmp_path):
    """A very long title must shrink + wrap to fit the safe area, not run off."""
    from PIL import ImageDraw

    long_title = (
        "The Ancient Roman Engineering Secret That Modern Scientists "
        "Still Cannot Fully Explain After Two Thousand Years"
    )
    max_w = 1280 - 2 * thumbnail._MARGIN
    max_h = 720 - 3 * thumbnail._MARGIN
    scratch = ImageDraw.Draw(Image.new("RGB", (1280, 720)))
    font, lines = thumbnail._layout_title(scratch, long_title, max_w, max_h)

    assert 1 <= len(lines) <= thumbnail._MAX_TITLE_LINES
    for line in lines:
        assert scratch.textlength(line, font=font) <= max_w
    # And the whole stage still emits a valid 1280x720 file for the long title.
    cfg = Config(runs_dir=tmp_path)
    spine = _spine(long_title)
    thumbnail.run(spine, cfg)
    with Image.open(cfg.assets_dir(spine.run_id) / "thumb.jpg") as img:
        assert img.size == (1280, 720)


def test_short_title_uses_a_large_font(tmp_path):
    """Scale contrast: a short title should get a big display size, not the floor."""
    from PIL import ImageDraw

    scratch = ImageDraw.Draw(Image.new("RGB", (1280, 720)))
    font, _ = thumbnail._layout_title(
        scratch, "Deep Sea", 1280 - 2 * thumbnail._MARGIN, 720 - 3 * thumbnail._MARGIN
    )
    assert font.size >= 100


def test_hero_frame_is_composited_when_present(tmp_path):
    """With a saturated red hero on disk, the frame's colour must survive into the
    thumbnail — proving we composite the film's image, not a flat card."""
    cfg = Config(runs_dir=tmp_path)
    spine = _spine("Volcano Winter", with_hero=True, cfg=cfg)
    _write_hero(cfg, spine.run_id)
    thumbnail.run(spine, cfg)

    with Image.open(cfg.assets_dir(spine.run_id) / "thumb.jpg") as img:
        # Sample the upper band (above the scrim) where the graded hero shows.
        top = img.crop((0, 0, 1280, 180)).getcolors(maxcolors=1_000_000) or []
    reddish = sum(n for n, (r, g, b) in top if r > 90 and r > g + 30 and r > b + 30)
    assert reddish > 0, "hero frame colour did not survive compositing"


def test_accent_is_deterministic_and_varies(tmp_path):
    assert thumbnail._accent_for("Roman Concrete") == thumbnail._accent_for("Roman Concrete")
    # Across many titles the palette is actually exercised (not one constant).
    seen = {thumbnail._accent_for(f"Title number {i}") for i in range(40)}
    assert len(seen) >= 3


def test_stays_under_two_megabytes(tmp_path):
    cfg = Config(runs_dir=tmp_path)
    spine = _spine("Roman Concrete Still Baffles Engineers", with_hero=True, cfg=cfg)
    _write_hero(cfg, spine.run_id)
    thumbnail.run(spine, cfg)
    assert (cfg.assets_dir(spine.run_id) / "thumb.jpg").stat().st_size <= thumbnail._MAX_BYTES


def test_no_topic_raises(tmp_path):
    cfg = Config(runs_dir=tmp_path)
    with pytest.raises(ValueError, match="topic"):
        thumbnail.run(Run.new("2026-07-22"), cfg)
