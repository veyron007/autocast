"""Ambient music bed: pure command construction, assets-stage wiring, graceful
degradation, and a real render guard that the muxed MP4 is NOT silent (Cycle 14).

The fast tests run everywhere. The one real-FFmpeg test is skipped when `ffmpeg`
is not on PATH (dry-run environments), so `pytest` stays green without it.
"""

from __future__ import annotations

import shutil
import subprocess

import pytest

from autocast.config import Config
from autocast.ffmpeg.ambient import build_ambient_cmd
from autocast.ffmpeg.mux import build_mux_cmd
from autocast.ffmpeg.run import FFmpegError, detect_volume, run_ffmpeg
from autocast.spine import Audio, Run, Shot
from autocast.stages import assets

_HAVE_FFMPEG = shutil.which("ffmpeg") is not None


# ---- pure command construction (no FFmpeg) ----

def test_build_ambient_cmd_layers_multiple_tones():
    cmd = build_ambient_cmd(out_path="bed.wav", duration_s=90.0)
    # Four detuned sine sources are mixed into one bed.
    assert cmd.count("-i") == 4
    assert all(part.startswith("sine=frequency=") for part in cmd if part.startswith("sine="))
    fx = cmd[cmd.index("-filter_complex") + 1]
    assert "amix=inputs=4" in fx
    assert cmd[-1] == "bed.wav"
    assert "pcm_s16le" in cmd  # same PCM family as the voice track


def test_build_ambient_cmd_has_fade_in_and_out():
    cmd = build_ambient_cmd(out_path="bed.wav", duration_s=90.0)
    fx = cmd[cmd.index("-filter_complex") + 1]
    assert "afade=t=in" in fx and "afade=t=out" in fx


def test_build_ambient_cmd_matches_requested_duration():
    cmd = build_ambient_cmd(out_path="bed.wav", duration_s=42.5)
    assert cmd[cmd.index("-t") + 1] == "42.500"


def test_build_ambient_cmd_short_clip_never_negative_fade_start():
    """A very short bed must not produce a negative afade `st` (would fail parse)
    or overlapping in/out fades. The fade length scales with duration."""
    fx = build_ambient_cmd(out_path="bed.wav", duration_s=1.0)
    fx_str = fx[fx.index("-filter_complex") + 1]
    out_start = float(fx_str.split("afade=t=out:st=")[1].split(":")[0])
    fade_len = float(fx_str.split("afade=t=in:st=0:d=")[1].split(",")[0])
    assert out_start >= 0.0
    assert out_start + fade_len <= 1.0 + 1e-6  # out fade fits inside the clip


# ---- assets stage wiring (FFmpeg mocked) ----

def _spine_ready_for_assets() -> Run:
    run = Run.new("2026-07-21")
    run.shots = [
        Shot(idx=i, narration=f"line {i}", image_prompt=f"p{i}", duration_s=3.0,
             caption="cap", audio_start_s=float(i * 3), audio_end_s=float(i * 3 + 3))
        for i in range(3)
    ]
    run.audio = Audio(voice_path="assets/voice.wav", duration_s=9.0)
    return run


def test_assets_synthesizes_cc0_bed_when_not_dry_run(tmp_path, monkeypatch):
    cfg = Config(runs_dir=tmp_path / "runs")
    calls: list[list[str]] = []

    def fake_run(cmd: list[str]) -> None:
        calls.append(cmd)  # would-be FFmpeg invocation

    monkeypatch.setattr(assets, "run_ffmpeg", fake_run)
    spine = assets.run(_spine_ready_for_assets(), cfg, dry_run=False)

    assert spine.assets.music_path == "assets/music.wav"
    assert spine.assets.music_source == "synth-ambient-cc0"
    lic = [e for e in spine.assets.license_manifest if e.asset == "music.wav"]
    assert lic and lic[0].license == "CC0-1.0" and lic[0].attribution is False
    # The bed was requested at the narration length (9.0s).
    assert calls and calls[0][calls[0].index("-t") + 1] == "9.000"


def test_assets_degrades_to_no_music_when_synth_fails(tmp_path, monkeypatch):
    cfg = Config(runs_dir=tmp_path / "runs")

    def boom(cmd: list[str]) -> None:
        raise FFmpegError("ffmpeg blew up")

    monkeypatch.setattr(assets, "run_ffmpeg", boom)
    spine = assets.run(_spine_ready_for_assets(), cfg, dry_run=False)

    # A failed bed must NOT fail the run: captions still built, music absent.
    assert spine.assets.music_path is None
    assert spine.assets.music_source is None
    assert spine.assets.captions_path == "assets/captions.ass"


# ---- real render guard: the muxed MP4 has a NON-SILENT audio track ----

@pytest.mark.skipif(not _HAVE_FFMPEG, reason="ffmpeg not installed")
def test_muxed_video_has_non_silent_audio_track(tmp_path):
    """End-to-end guard for Cycle 14: a synthesized CC0 bed, mixed under the voice
    by the real mux command, yields an MP4 whose audio is measurably NOT silent.
    A silent track reads near -91 dB; we assert the peak is well above that."""
    bed = tmp_path / "music.wav"
    voice = tmp_path / "voice.wav"
    reel = tmp_path / "reel.mp4"
    final = tmp_path / "final.mp4"

    # Real CC0 bed via the production builder.
    run_ffmpeg(build_ambient_cmd(out_path=str(bed), duration_s=2.0))

    # Minimal stand-in voice + silent reel (the pipeline's video/tts outputs).
    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
         "-i", "sine=frequency=300:duration=2", "-ar", "24000", "-ac", "1",
         "-c:a", "pcm_s16le", str(voice)], check=True)
    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
         "-i", "color=c=black:s=320x180:d=2:r=30", "-an", "-c:v", "libx264",
         "-pix_fmt", "yuv420p", str(reel)], check=True)

    run_ffmpeg(build_mux_cmd(
        reel_path=str(reel), voice_path=str(voice), out_path=str(final),
        music_path=str(bed)))

    mean_db, max_db = detect_volume(final)
    assert final.exists() and final.stat().st_size > 0
    assert max_db > -60.0, f"final.mp4 audio looks silent (max_volume={max_db} dB)"


@pytest.mark.skipif(not _HAVE_FFMPEG, reason="ffmpeg not installed")
def test_synthesized_bed_alone_is_non_silent(tmp_path):
    """The bed itself must carry signal (guards against an all-silence synth
    regression, e.g. a bad filtergraph that mutes every tone)."""
    bed = tmp_path / "bed.wav"
    run_ffmpeg(build_ambient_cmd(out_path=str(bed), duration_s=2.0))
    _, max_db = detect_volume(bed)
    assert max_db > -30.0, f"ambient bed is silent (max_volume={max_db} dB)"
