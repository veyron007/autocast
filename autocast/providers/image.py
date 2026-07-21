"""Image provider cascade: gemini-image -> pollinations[keyless] -> cloudflare-flux.

Each provider, given a prompt + an output path, writes a PNG to that path and
returns the path. In dry-run we synthesize a placeholder PNG (solid color via
Pillow if available, else an empty file) so the video stage has a real file.
"""

from __future__ import annotations

import logging
import struct
import zlib
from pathlib import Path
from urllib.parse import quote

from autocast.config import Config
from autocast.providers.cascade import Provider
from autocast.util.net import get_bytes

log = logging.getLogger("autocast.providers.image")

# Keyless Flux via Pollinations. `nologo` drops the watermark; `model=flux` is the
# best free model; a deterministic per-shot seed keeps re-runs stable yet distinct.
_POLLINATIONS = "https://image.pollinations.ai/prompt/{prompt}"

# Reject obviously-bad downloads (HTML error pages, truncated bodies).
_MIN_IMAGE_BYTES = 2000
_IMAGE_MAGIC = (b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n", b"RIFF", b"GIF8")


def _write_solid_png(path: Path, *, width: int, height: int, rgb: tuple[int, int, int]) -> None:
    """Write a solid-color PNG. Uses Pillow if present; otherwise hand-rolls a
    minimal valid PNG with the stdlib (zlib+struct) so dry-run needs NO Pillow."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        from PIL import Image  # type: ignore

        Image.new("RGB", (width, height), rgb).save(path, "PNG")
        return
    except Exception:  # noqa: BLE001 - Pillow optional; fall back to stdlib PNG
        pass

    _write_solid_png_stdlib(path, width=width, height=height, rgb=rgb)


def _write_solid_png_stdlib(path: Path, *, width: int, height: int, rgb: tuple[int, int, int]) -> None:
    """Minimal valid solid-color PNG using only the standard library."""

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)  # 8-bit RGB
    row = b"\x00" + bytes(rgb) * width  # filter byte 0 + pixels
    raw = row * height
    idat = zlib.compress(raw, 9)
    path.write_bytes(sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b""))


def _dry_image(out_path: str, *, width: int, height: int, idx: int) -> str:
    # Rotate a few muted colors so shots are visually distinguishable.
    palette = [(40, 44, 52), (60, 40, 70), (30, 60, 60), (70, 55, 30)]
    _write_solid_png(Path(out_path), width=width, height=height, rgb=palette[idx % len(palette)])
    return out_path


def _looks_like_image(data: bytes) -> bool:
    return len(data) >= _MIN_IMAGE_BYTES and any(data.startswith(m) for m in _IMAGE_MAGIC)


def _pollinations(prompt: str, out_path: str, *, idx: int, width: int, height: int) -> str:
    """Keyless Flux image. GET the rendered bytes and write them to out_path.

    Pollinations may return JPEG regardless of the .png extension — FFmpeg detects
    the container by content, so the extension is cosmetic. We validate the magic
    bytes so an HTML error page never masquerades as an image downstream.
    """
    url = _POLLINATIONS.format(prompt=quote(prompt))
    data = get_bytes(
        url,
        timeout=60.0,
        retries=2,
        params={
            "width": width,
            "height": height,
            "nologo": "true",
            "model": "flux",
            "seed": 1000 + idx,  # deterministic per shot; stable re-runs
        },
    )
    if not _looks_like_image(data):
        raise ValueError(f"pollinations returned non-image body ({len(data)} bytes)")
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    log.info("image: pollinations wrote %s (%d bytes)", p.name, len(data))
    return out_path


# TODO(real): cloudflare flux fallback: POST .../ai/run/@cf/black-forest-labs/flux-1-schnell
# TODO(real): gemini-image as a higher-quality keyed primary once a key exists.


def build_image_providers(
    cfg: Config,
    *,
    prompt: str,
    out_path: str,
    idx: int,
    width: int,
    height: int,
    dry_run: bool = False,
) -> list[Provider[str]]:
    if dry_run:
        return [
            Provider(
                "dry-solid-png",
                lambda: _dry_image(out_path, width=width, height=height, idx=idx),
            )
        ]

    # Pollinations needs no key -> the reliable keyless default. Cloudflare Flux is
    # a paid-overage fallback, guarded by the budget kill-switch.
    providers: list[Provider[str]] = [
        Provider(
            "pollinations-flux",
            lambda: _pollinations(prompt, out_path, idx=idx, width=width, height=height),
        )
    ]
    if cfg.cloudflare_api_token and cfg.cloudflare_budget_cents > 0:
        providers.append(Provider("cloudflare-flux", lambda: _not_impl("cloudflare-flux")))
    return providers


def _not_impl(name: str) -> str:
    raise NotImplementedError(f"image provider {name!r} not implemented yet (Cycle 4)")
