"""Stage: video — per-shot Ken Burns clips, concat, then final mux.

Reads each shot's `image_path` + motion + duration, writes each shot's
`clip_path` and the final `spine.video`. The FFmpeg command construction is REAL
and visible (see autocast/ffmpeg/*). In dry-run we log every command and touch
placeholder clip/reel/final files instead of shelling out to FFmpeg.
"""

from __future__ import annotations

import logging
from pathlib import Path

from autocast.config import Config
from autocast.ffmpeg.kenburns import build_kenburns_cmd
from autocast.ffmpeg.mux import build_concat_cmd, build_mux_cmd, write_concat_list
from autocast.ffmpeg.run import has_filter, run_ffmpeg
from autocast.spine import Run, Video

log = logging.getLogger("autocast.stages.video")

STAGE = "video"


def _run_or_log(cmd: list[str], *, dry_run: bool, touch: Path | None = None) -> None:
    """Run the FFmpeg command, or (dry-run) log it and touch the output file."""
    if dry_run:
        log.info("ffmpeg cmd: %s", " ".join(cmd))
        if touch is not None:
            touch.parent.mkdir(parents=True, exist_ok=True)
            touch.touch()
        return
    run_ffmpeg(cmd)  # surfaces FFmpeg stderr on failure


def run(spine: Run, cfg: Config, *, dry_run: bool = False) -> Run:
    if not spine.shots:
        raise ValueError("video stage: spine.shots empty (run direction first)")
    if spine.audio is None:
        raise ValueError("video stage: spine.audio missing (run tts first)")

    run_dir = cfg.run_dir(spine.run_id)
    assets_dir = cfg.assets_dir(spine.run_id)

    # 1. One Ken Burns clip per shot.
    clip_abs_paths: list[str] = []
    for shot in spine.shots:
        if not shot.image_path:
            raise ValueError(f"video stage: shot {shot.idx} has no image_path")
        img_abs = str(run_dir / shot.image_path)
        clip_abs = str(assets_dir / f"shot_{shot.idx:03d}.mp4")

        cmd = build_kenburns_cmd(
            image_path=img_abs,
            out_path=clip_abs,
            duration_s=shot.duration_s,
            motion=shot.motion,
            width=cfg.width,
            height=cfg.height,
            fps=cfg.fps,
        )
        _run_or_log(cmd, dry_run=dry_run, touch=Path(clip_abs))
        shot.clip_path = f"assets/shot_{shot.idx:03d}.mp4"
        clip_abs_paths.append(clip_abs)

    # 2. Concat the clips into one silent reel.
    concat_list = write_concat_list(assets_dir / "concat.txt", clip_abs_paths)
    reel_abs = str(assets_dir / "reel.mp4")
    concat_cmd = build_concat_cmd(concat_list_path=str(concat_list), out_path=reel_abs)
    _run_or_log(concat_cmd, dry_run=dry_run, touch=Path(reel_abs))

    # 3. Mux voice + optional music + burned captions -> final.mp4.
    voice_abs = str(run_dir / spine.audio.voice_path)
    music_abs = str(run_dir / spine.assets.music_path) if (spine.assets and spine.assets.music_path) else None
    caps_abs = str(run_dir / spine.assets.captions_path) if (spine.assets and spine.assets.captions_path) else None
    # Caption burning needs the `subtitles` filter (libass). Some FFmpeg builds
    # (e.g. a minimal Homebrew one) lack it; CI's apt ffmpeg has it. When it's
    # missing on a real render, skip the burn instead of crashing the whole video.
    if caps_abs and not dry_run and not has_filter("subtitles"):
        log.warning("video: `subtitles` filter unavailable (no libass) -> skipping caption burn")
        caps_abs = None
    final_abs = str(assets_dir / "final.mp4")

    mux_cmd = build_mux_cmd(
        reel_path=reel_abs,
        voice_path=voice_abs,
        out_path=final_abs,
        music_path=music_abs,
        captions_path=caps_abs,
    )
    _run_or_log(mux_cmd, dry_run=dry_run, touch=Path(final_abs))

    size_bytes = Path(final_abs).stat().st_size if Path(final_abs).exists() else 0
    spine.video = Video(
        final_path="assets/final.mp4",
        width=cfg.width,
        height=cfg.height,
        fps=cfg.fps,
        duration_s=spine.audio.duration_s,
        size_bytes=size_bytes,
    )
    log.info("video: built final.mp4 (%d clips, %d bytes)", len(spine.shots), size_bytes)
    return spine
