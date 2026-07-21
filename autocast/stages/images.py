"""Stage: images — one image per shot via the image cascade.

Reads `spine.shots` + their `image_prompt`, writes each shot's `image_path`.
Cascade: gemini-image -> pollinations -> cloudflare-flux. In dry-run each shot
gets a solid-color placeholder PNG (Pillow if present, else a stdlib PNG) so the
video stage has a real image file per shot.
"""

from __future__ import annotations

import logging

from autocast.config import Config
from autocast.providers.cascade import run_with_fallback
from autocast.providers.image import build_image_providers
from autocast.spine import Run

log = logging.getLogger("autocast.stages.images")

STAGE = "images"


def run(spine: Run, cfg: Config, *, dry_run: bool = False) -> Run:
    if not spine.shots:
        raise ValueError("images stage: spine.shots empty (run direction first)")

    assets_dir = cfg.assets_dir(spine.run_id)
    providers_used: set[str] = set()

    for shot in spine.shots:
        rel_path = f"assets/shot_{shot.idx:03d}.png"
        abs_path = str(assets_dir / f"shot_{shot.idx:03d}.png")

        providers = build_image_providers(
            cfg,
            prompt=shot.image_prompt,
            out_path=abs_path,
            idx=shot.idx,
            width=cfg.width,
            height=cfg.height,
            dry_run=dry_run,
        )
        result = run_with_fallback(providers)
        providers_used.add(result.provider_used)

        # Store the RELATIVE path in the spine (never absolute, never a blob).
        shot.image_path = rel_path

    # Record a single representative provider for the stage row.
    spine.stage(STAGE).provider_used = ",".join(sorted(providers_used))
    log.info("images: rendered %d images via %s", len(spine.shots), spine.stage(STAGE).provider_used)
    return spine
