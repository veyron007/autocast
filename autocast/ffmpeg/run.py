"""FFmpeg/ffprobe execution helpers — run commands, probe media, detect filters.

The command *builders* live in kenburns.py / mux.py (pure, inspectable, testable).
This module is the side-effecting layer that actually shells out, and the single
place that surfaces FFmpeg's stderr when something breaks (a silent CalledProcess
error is useless; the last lines of stderr are where the truth is).
"""

from __future__ import annotations

import functools
import logging
import re
import subprocess
from pathlib import Path

log = logging.getLogger("autocast.ffmpeg")


class FFmpegError(RuntimeError):
    """FFmpeg exited non-zero. Carries the tail of stderr so failures are legible."""


def run_ffmpeg(cmd: list[str]) -> None:
    """Run an ffmpeg/ffprobe argv list. Raise FFmpegError with stderr on failure."""
    log.info("ffmpeg: %s", " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        tail = "\n".join(proc.stderr.strip().splitlines()[-12:])
        raise FFmpegError(f"{cmd[0]} exited {proc.returncode}:\n{tail}")


def probe_duration(path: str | Path) -> float:
    """Return media duration in seconds via ffprobe (0.0 if unknown/empty)."""
    proc = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=nokey=1:noprint_wrappers=1",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    out = proc.stdout.strip()
    try:
        return float(out)
    except ValueError:
        return 0.0


_VOL_RE = re.compile(r"(mean|max)_volume:\s*(-?\d+(?:\.\d+)?) dB")


def detect_volume(path: str | Path) -> tuple[float, float]:
    """Return `(mean_db, max_db)` for a media file's audio via FFmpeg's
    `volumedetect`. A silent track reports a floor near -91 dB; a missing/unparsed
    reading returns `-inf`, so callers can assert `max_db > threshold` to prove a
    track is *not* silent. Used by the render guard test (Cycle 14: music bed)."""
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", str(path), "-af", "volumedetect", "-f", "null", "-"],
        capture_output=True,
        text=True,
    )
    readings: dict[str, float] = {}
    for kind, value in _VOL_RE.findall(proc.stderr):
        readings[kind] = float(value)
    return readings.get("mean", float("-inf")), readings.get("max", float("-inf"))


@functools.lru_cache(maxsize=None)
def has_filter(name: str) -> bool:
    """True if this FFmpeg build exposes `name` as a filter.

    Used to decide whether caption burning (the `subtitles` filter, which needs
    libass) is possible. Homebrew's minimal ffmpeg may lack it; apt's ubuntu
    build in CI has it. Cached — `ffmpeg -filters` is invariant per process.
    """
    try:
        proc = subprocess.run(
            ["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True
        )
    except FileNotFoundError:
        return False
    for line in proc.stdout.splitlines():
        # Filter rows look like: " T.. subtitles         V->V  ...". The name is
        # the second whitespace-delimited token.
        parts = line.split()
        if len(parts) >= 2 and parts[1] == name:
            return True
    return False


# ---- audio helpers used by the TTS stage to build a perfectly-synced track ----

# Normalize every synthesized clip to one format so concat-copy is safe and the
# muxed voice track has a single, predictable sample format.
_A_RATE = "24000"
_A_CH = "1"


def pad_audio_to(in_path: str | Path, out_path: str | Path, duration_s: float) -> None:
    """Re-encode `in_path` to a mono 24k WAV padded with trailing silence to
    exactly `duration_s`. Guarantees each shot's audio == its clip length."""
    run_ffmpeg(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(in_path),
            "-af",
            "apad",
            "-t",
            f"{duration_s:.3f}",
            "-ar",
            _A_RATE,
            "-ac",
            _A_CH,
            "-c:a",
            "pcm_s16le",
            str(out_path),
        ]
    )


def concat_audio(wav_paths: list[str], out_path: str | Path, list_path: str | Path) -> None:
    """Concatenate same-format WAVs (from pad_audio_to) into one voice track."""
    lp = Path(list_path)
    lp.parent.mkdir(parents=True, exist_ok=True)
    lp.write_text("\n".join(f"file '{p}'" for p in wav_paths) + "\n", encoding="utf-8")
    run_ffmpeg(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(lp),
            "-ar",
            _A_RATE,
            "-ac",
            _A_CH,
            "-c:a",
            "pcm_s16le",
            str(out_path),
        ]
    )
