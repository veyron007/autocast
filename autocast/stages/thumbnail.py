"""Stage: thumbnail — a designed 1280x720 CTR thumbnail (Pillow).

Reads `spine.topic` (+ `spine.shots[0]` for the hero frame), writes
`spine.thumbnail`. This is a *composed* thumbnail, not a flat text card:

  1. Background = the film's own hero frame (shot 0), cover-cropped to 16:9 — the
     video's best image sells the click. No hero on disk (e.g. a keyless dry-run)
     degrades to a deep, per-video gradient, never a dead flat color.
  2. A cinematic grade + a bottom-anchored scrim gradient guarantees the title is
     legible over ANY image (bright skies included).
  3. Hierarchy: a small accent keyline + eyebrow over a big auto-fit title anchored
     lower-left (editorial), not a centered blob.
  4. Type: Arial Black (heavier/more characterful than Arial Bold) that **auto-fits**
     — the size shrinks and the title wraps until it always fits the safe area.
     This fixes the old fixed-96px card that ran long titles off the canvas.

The accent colour is derived deterministically from the title, so each video gets
its own look with zero randomness (renders stay reproducible).

Specs (research §7): 1280x720, <= 2 MB, JPG q~88.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from autocast.config import Config
from autocast.spine import Run, Thumbnail

log = logging.getLogger("autocast.stages.thumbnail")

STAGE = "thumbnail"
_W, _H = 1280, 720
_MARGIN = 70  # safe-area inset (px) on every side
_MAX_TITLE_LINES = 3
_MAX_TITLE_PX = 132  # largest display size we ever try
_MIN_TITLE_PX = 44  # never go smaller than this — readability floor
_MAX_BYTES = 2 * 1024 * 1024  # research §7 hard cap
_EYEBROW = "AUTOCAST"

# Bold display faces, most-characterful first. Linux (GitHub Actions) has no
# Arial, so DejaVu/Liberation bold are the CI fallbacks; a scalable default font
# is the last resort so auto-fit still works with zero fonts installed.
_DISPLAY_FONTS = (
    "/System/Library/Fonts/Supplemental/Arial Black.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
)

# Curated strong accents that stay legible on a dark, graded frame.
_ACCENTS: tuple[tuple[int, int, int], ...] = (
    (240, 138, 58),   # amber
    (46, 196, 182),   # teal
    (240, 192, 64),   # gold
    (226, 74, 92),    # crimson
    (74, 158, 244),   # azure
    (158, 122, 240),  # violet
    (150, 206, 76),   # lime
    (255, 111, 97),   # coral
)


def _accent_for(title: str) -> tuple[int, int, int]:
    """Deterministic accent colour from the title (stable across renders)."""
    h = hashlib.sha1(title.encode("utf-8")).digest()[0]
    return _ACCENTS[h % len(_ACCENTS)]


def _load_font(size: int):
    """Best available bold display face at `size`, degrading gracefully."""
    from PIL import ImageFont  # local import: Pillow is optional at module load

    for path in _DISPLAY_FONTS:
        try:
            return ImageFont.truetype(path, size)
        except Exception:  # noqa: BLE001 - try the next candidate
            continue
    try:
        return ImageFont.load_default(size=size)  # Pillow >= 10 scales the default
    except TypeError:  # pragma: no cover - very old Pillow
        return ImageFont.load_default()


def _hero_background(hero_path: Path | None, size: tuple[int, int]):
    """Cover-crop the hero frame to `size`, or None if unavailable/unreadable."""
    if hero_path is None or not hero_path.exists():
        return None
    try:
        from PIL import Image

        src = Image.open(hero_path).convert("RGB")
    except Exception as exc:  # noqa: BLE001 - a bad image must not fail the run
        log.warning("thumbnail: hero frame unreadable (%s) -> gradient fallback", exc)
        return None

    w, h = size
    iw, ih = src.size
    scale = max(w / iw, h / ih)
    new = (max(w, round(iw * scale)), max(h, round(ih * scale)))
    src = src.resize(new, Image.LANCZOS)
    left = (src.width - w) // 2
    top = (src.height - h) // 2
    return src.crop((left, top, left + w, top + h))


def _gradient_background(size: tuple[int, int], accent: tuple[int, int, int]):
    """A deep vertical gradient (accent-tinted top -> near-black) for keyless
    renders — depth instead of a dead flat colour."""
    from PIL import Image

    w, h = size
    ar, ag, ab = accent
    top = (max(ar // 5, 10), max(ag // 5, 12), max(ab // 5, 18))  # dim accent tint
    bottom = (8, 9, 12)
    grad = Image.new("RGB", (1, h))
    px = grad.load()
    for y in range(h):
        t = y / max(h - 1, 1)
        px[0, y] = (
            round(top[0] + (bottom[0] - top[0]) * t),
            round(top[1] + (bottom[1] - top[1]) * t),
            round(top[2] + (bottom[2] - top[2]) * t),
        )
    return grad.resize((w, h))


def _apply_grade(img, accent: tuple[int, int, int]):
    """Darken globally + lay a bottom scrim and a top vignette so text is always
    legible and varied hero frames read as one channel."""
    from PIL import Image, ImageEnhance

    img = ImageEnhance.Brightness(img).enhance(0.82)
    img = ImageEnhance.Color(img).enhance(1.06)

    w, h = img.size
    # Bottom scrim: transparent at the top -> near-opaque black at the base, so
    # the lower-third title area is always dark enough for white type.
    scrim = Image.new("L", (1, h), 0)
    spx = scrim.load()
    for y in range(h):
        t = y / max(h - 1, 1)
        spx[0, y] = round(235 * (t ** 1.7))
    scrim = scrim.resize((w, h))
    black = Image.new("RGB", (w, h), (6, 7, 10))
    img = Image.composite(black, img, scrim)

    # A whisper of top vignette for depth.
    top_v = Image.new("L", (1, h), 0)
    tpx = top_v.load()
    for y in range(h):
        t = 1.0 - (y / max(h - 1, 1))
        tpx[0, y] = round(70 * (t ** 2.2))
    top_v = top_v.resize((w, h))
    img = Image.composite(Image.new("RGB", (w, h), (0, 0, 0)), img, top_v)
    return img


def _line_height(font) -> int:
    ascent, descent = font.getmetrics()
    return ascent + descent


def _wrap(draw, words: list[str], font, max_width: int) -> list[str]:
    """Greedy word-wrap to `max_width` (a single over-long word is let through)."""
    lines: list[str] = []
    cur = ""
    for word in words:
        trial = word if not cur else f"{cur} {word}"
        if not cur or draw.textlength(trial, font=font) <= max_width:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def _layout_title(draw, title: str, max_width: int, max_height: int):
    """Largest font size at which the title wraps into <= _MAX_TITLE_LINES lines
    that all fit `max_width` and whose block fits `max_height`.

    Returns (font, lines). Guaranteed to return SOMETHING (min size, clamped
    lines) so a pathological title can never overflow or raise.
    """
    words = title.split()
    for size in range(_MAX_TITLE_PX, _MIN_TITLE_PX - 1, -4):
        font = _load_font(size)
        lines = _wrap(draw, words, font, max_width)
        if len(lines) > _MAX_TITLE_LINES:
            continue
        widest = max((draw.textlength(ln, font=font) for ln in lines), default=0)
        block_h = len(lines) * round(_line_height(font) * 1.04)
        if widest <= max_width and block_h <= max_height:
            return font, lines

    # Floor: smallest size, hard-clamped to the line budget so we never overflow.
    font = _load_font(_MIN_TITLE_PX)
    lines = _wrap(draw, words, font, max_width)[:_MAX_TITLE_LINES]
    return font, lines


def _draw_title_block(base, lines: list[str], font, accent: tuple[int, int, int]) -> None:
    """Eyebrow + accent keyline + title, anchored lower-left in the safe area."""
    from PIL import Image, ImageDraw

    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    line_h = round(_line_height(font) * 1.04)
    block_h = len(lines) * line_h
    baseline_bottom = _H - _MARGIN
    y = baseline_bottom - block_h

    # Eyebrow (small, letter-spaced) + accent keyline above the title.
    eb_font = _load_font(34)
    eb_h = _line_height(eb_font)
    keyline_y = y - eb_h - 34
    draw.rounded_rectangle(
        [_MARGIN, keyline_y, _MARGIN + 88, keyline_y + 10], radius=5, fill=accent + (255,)
    )
    draw.text(
        (_MARGIN, keyline_y + 22),
        " ".join(_EYEBROW),  # cheap letter-spacing
        font=eb_font,
        fill=(235, 238, 245, 255),
    )

    # Title lines: soft drop shadow + heavy stroke for legibility on any frame.
    for line in lines:
        draw.text((_MARGIN + 5, y + 6), line, font=font, fill=(0, 0, 0, 150))
        draw.text(
            (_MARGIN, y),
            line,
            font=font,
            fill=(255, 255, 255, 255),
            stroke_width=6,
            stroke_fill=(8, 8, 12, 255),
        )
        y += line_h

    base.alpha_composite(overlay)


def _compose_with_pillow(out_path: Path, title: str, hero_path: Path | None) -> bool:
    """Compose + save the thumbnail. Returns True if Pillow was available."""
    try:
        from PIL import Image
    except Exception:  # noqa: BLE001 - Pillow optional
        return False

    accent = _accent_for(title)
    bg = _hero_background(hero_path, (_W, _H)) or _gradient_background((_W, _H), accent)
    bg = _apply_grade(bg, accent).convert("RGBA")

    from PIL import ImageDraw

    # Reserve the top third for the graded frame / eyebrow; fit the title in the
    # lower band so the block never collides with the eyebrow keyline.
    font, lines = _layout_title(ImageDraw.Draw(bg), title, _W - 2 * _MARGIN, _H - 3 * _MARGIN)
    _draw_title_block(bg, lines, font, accent)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    final = bg.convert("RGB")
    # Save under the 2 MB cap, stepping quality down only if a busy frame overflows.
    for quality in (88, 82, 74, 66):
        final.save(out_path, "JPEG", quality=quality, optimize=True)
        if out_path.stat().st_size <= _MAX_BYTES:
            break
    return True


def _hero_abs(spine: Run, cfg: Config) -> Path | None:
    """Absolute path to shot 0's rendered image, if the images stage produced it."""
    if not spine.shots:
        return None
    rel = spine.shots[0].image_path
    if not rel:
        return None
    return cfg.run_dir(spine.run_id) / rel


def run(spine: Run, cfg: Config, *, dry_run: bool = False) -> Run:
    if spine.topic is None:
        raise ValueError("thumbnail stage: spine.topic missing (run topic first)")

    out_abs = cfg.assets_dir(spine.run_id) / "thumb.jpg"
    composed = _compose_with_pillow(out_abs, spine.topic.title, _hero_abs(spine, cfg))

    if not composed:
        # Stub file keeps the pipeline shape without Pillow.
        out_abs.parent.mkdir(parents=True, exist_ok=True)
        out_abs.touch()
        log.warning("thumbnail: Pillow unavailable; touched stub %s", out_abs.name)

    spine.thumbnail = Thumbnail(path="assets/thumb.jpg", width=_W, height=_H)
    log.info("thumbnail: %s (pillow=%s)", spine.thumbnail.path, composed)
    return spine
