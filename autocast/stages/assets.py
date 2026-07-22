"""Stage: assets — background music, optional stock, and burned-caption file.

Reads `spine.shots` (captions + timing windows) and `spine.audio`, writes
`spine.assets` (music path/source, captions .ass path, license manifest). Music
is a procedurally synthesized **CC0 ambient bed** (no key, no network, no
attribution) so even a fully keyless render is scored instead of silent; a keyed
Pixabay/Freesound pick can layer in later. Stock is Pexels (still stubbed). The
.ass captions ARE built for real from the shot timing windows — that's cheap and
it proves the sync path.

License provenance matters (research §6): every asset gets a license_manifest row
so compliance is auditable.
"""

from __future__ import annotations

import logging

from autocast.config import Config
from autocast.ffmpeg.ambient import build_ambient_cmd
from autocast.ffmpeg.run import FFmpegError, run_ffmpeg
from autocast.spine import Assets, LicenseEntry, Run

log = logging.getLogger("autocast.stages.assets")

STAGE = "assets"

# Bespoke synthesized bed: no copyright, no attribution obligation.
_MUSIC_FILE = "music.wav"
_MUSIC_SOURCE = "synth-ambient-cc0"
_MUSIC_LICENSE = "CC0-1.0"

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
        # Stub the bed (zero bytes) so the dry-run spine has the same shape as a
        # real render without shelling out to FFmpeg.
        (assets_dir / _MUSIC_FILE).touch()
        music_path = f"assets/{_MUSIC_FILE}"
        music_source = "dryrun-stub"
        license_manifest.append(LicenseEntry(asset=_MUSIC_FILE, license="stub", attribution=False))
    else:
        # Synthesize a CC0 ambient bed the length of the narration. No key, no
        # network, no attribution — a keyless render is now scored, not silent.
        # A synth failure degrades to a still-rendered (silent) video rather than
        # failing the run: the spine treats a partial result as first-class.
        # TODO(keyed): a Pixabay/Freesound pick can override this when a key exists.
        duration_s = spine.audio.duration_s if spine.audio else float(cfg.target_len_s)
        music_out = assets_dir / _MUSIC_FILE
        try:
            run_ffmpeg(build_ambient_cmd(out_path=str(music_out), duration_s=duration_s))
            music_path = f"assets/{_MUSIC_FILE}"
            music_source = _MUSIC_SOURCE
            license_manifest.append(
                LicenseEntry(asset=_MUSIC_FILE, license=_MUSIC_LICENSE, attribution=False)
            )
        except (FFmpegError, FileNotFoundError, OSError) as exc:
            log.warning("assets: ambient bed synth failed (%s) -> rendering without music", exc)

    spine.assets = Assets(
        music_path=music_path,
        music_source=music_source,
        captions_path="assets/captions.ass",
        stock_paths=[],
        license_manifest=license_manifest,
    )
    log.info("assets: captions + music_source=%s", music_source)
    return spine
