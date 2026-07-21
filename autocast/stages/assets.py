"""Stage: assets — background music, optional stock, and burned-caption file.

Reads `spine.shots` (captions + timing windows) and `spine.audio`, writes
`spine.assets` (music path/source, captions .ass path, license manifest). Music
is Pixabay (no attribution); stock is Pexels. Both stubbed in dry-run. The .ass
captions ARE built for real from the shot timing windows — that's cheap and it
proves the sync path.

License provenance matters (research §6): every asset gets a license_manifest row
so compliance is auditable.
"""

from __future__ import annotations

import logging

from autocast.config import Config
from autocast.spine import Assets, LicenseEntry, Run

log = logging.getLogger("autocast.stages.assets")

STAGE = "assets"

_ASS_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Outline, Shadow, Alignment, MarginV
Style: Cap, Arial, 54, &H00FFFFFF, &H00000000, &H64000000, 1, 3, 1, 2, 90

[Events]
Format: Layer, Start, End, Style, Text
"""


def _ass_time(seconds: float) -> str:
    """Format seconds as ASS timestamp H:MM:SS.cs."""
    cs = int(round(seconds * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _build_ass(spine: Run, width: int, height: int) -> str:
    """Build an .ass subtitle file from each shot's caption + timing window."""
    lines = [_ASS_HEADER.format(w=width, h=height)]
    for shot in spine.shots:
        start = _ass_time(shot.audio_start_s or 0.0)
        end = _ass_time(shot.audio_end_s or (shot.duration_s))
        text = shot.caption.replace("\n", " ")
        lines.append(f"Dialogue: 0,{start},{end},Cap,,{text}")
    return "\n".join(lines) + "\n"


def run(spine: Run, cfg: Config, *, dry_run: bool = False) -> Run:
    if not spine.shots:
        raise ValueError("assets stage: spine.shots empty (run direction first)")

    assets_dir = cfg.assets_dir(spine.run_id)
    assets_dir.mkdir(parents=True, exist_ok=True)

    # Captions: built for real from shot timing windows.
    ass_text = _build_ass(spine, cfg.width, cfg.height)
    (assets_dir / "captions.ass").write_text(ass_text, encoding="utf-8")

    license_manifest: list[LicenseEntry] = []
    music_path: str | None = None
    music_source: str | None = None

    if dry_run:
        # TODO(real): Pixabay Music API pick + download; else pre-staged YTAL pool.
        (assets_dir / "music.mp3").touch()
        music_path = "assets/music.mp3"
        music_source = "dryrun-stub"
        license_manifest.append(LicenseEntry(asset="music.mp3", license="stub", attribution=False))
    else:
        # TODO(real): fetch Pixabay music + optional Pexels stock; append real
        #             license rows. Guard behind cfg.pixabay_api_key / pexels_api_key.
        log.warning("assets: live music/stock fetch not implemented (Cycle 4)")

    spine.assets = Assets(
        music_path=music_path,
        music_source=music_source,
        captions_path="assets/captions.ass",
        stock_paths=[],
        license_manifest=license_manifest,
    )
    log.info("assets: captions + music_source=%s", music_source)
    return spine
