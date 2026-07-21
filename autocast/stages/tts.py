"""Stage: tts — script -> voice.wav + per-shot timing.

Reads `spine.script` + `spine.shots`, writes `spine.audio` and back-fills each
shot's `audio_start_s`/`audio_end_s`.

REAL path (the sync keystone): synthesize EACH shot's narration separately, measure
its actual audio length, and SET that shot's `duration_s` to it (+ a short tail).
The video stage then renders each Ken Burns clip to exactly that length, so audio
and visuals stay locked no matter how long the narration turns out to be. The
per-shot wavs are padded to their shot duration and concatenated into one voice.wav
whose total length equals the reel's total — perfect A/V alignment.

DRY path: unchanged — touch a wav, fabricate evenly-spaced word timings, and lay
shots end-to-end on their existing durations (keeps the dry pipeline + tests stable).
Cascade: kokoro -> edge-tts -> macOS say.
"""

from __future__ import annotations

import json
import logging

from autocast.config import Config
from autocast.ffmpeg.run import concat_audio, pad_audio_to, probe_duration
from autocast.providers.cascade import run_with_fallback
from autocast.providers.tts import build_synth_providers, build_tts_providers
from autocast.spine import Audio, Run

log = logging.getLogger("autocast.stages.tts")

STAGE = "tts"

# A short breath after each shot's narration so scene changes don't feel clipped,
# and a floor so a very short line still lingers on screen.
_TAIL_PAD_S = 0.45
_MIN_SHOT_S = 2.0


def _assign_shot_audio_windows(spine: Run) -> float:
    """Lay shots end-to-end on the timeline using their durations. Returns total."""
    cursor = 0.0
    for shot in spine.shots:
        shot.audio_start_s = round(cursor, 3)
        cursor += shot.duration_s
        shot.audio_end_s = round(cursor, 3)
    return round(cursor, 3)


def _run_dry(spine: Run, cfg: Config) -> Run:
    total_len = _assign_shot_audio_windows(spine) or float(cfg.target_len_s)
    assets_dir = cfg.assets_dir(spine.run_id)
    providers = build_tts_providers(
        cfg,
        text=spine.script.full_text,
        out_wav=str(assets_dir / "voice.wav"),
        target_len_s=total_len,
        dry_run=True,
    )
    result = run_with_fallback(providers)
    _wav_path, timings = result.value

    if timings is not None:
        (assets_dir / "words.json").write_text(
            json.dumps(timings, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    spine.audio = Audio(
        voice_path="assets/voice.wav",
        duration_s=total_len,
        word_timings_path="assets/words.json" if timings is not None else None,
        provider=result.provider_used,
    )
    spine.stage(STAGE).provider_used = result.provider_used
    log.info("tts[dry]: %.1fs voice via %s", total_len, result.provider_used)
    return spine


def _run_real(spine: Run, cfg: Config) -> Run:
    assets_dir = cfg.assets_dir(spine.run_id)
    assets_dir.mkdir(parents=True, exist_ok=True)

    padded_wavs: list[str] = []
    providers_used: set[str] = set()

    for shot in spine.shots:
        base = str(assets_dir / f"voice_raw_{shot.idx:03d}")
        result = run_with_fallback(build_synth_providers(cfg, text=shot.narration, base=base))
        providers_used.add(result.provider_used)

        raw_path = result.value
        measured = probe_duration(raw_path)
        # The measured narration length DRIVES this shot's on-screen duration.
        shot.duration_s = max(round(measured + _TAIL_PAD_S, 3), _MIN_SHOT_S)

        padded = str(assets_dir / f"voice_{shot.idx:03d}.wav")
        pad_audio_to(raw_path, padded, shot.duration_s)
        padded_wavs.append(padded)
        log.info("tts: shot %d narration %.2fs -> clip %.2fs", shot.idx, measured, shot.duration_s)

    # Windows now reflect the REAL (audio-driven) durations.
    total_len = _assign_shot_audio_windows(spine)

    voice_abs = assets_dir / "voice.wav"
    concat_audio(padded_wavs, voice_abs, assets_dir / "voice_concat.txt")

    provider_used = ",".join(sorted(providers_used))
    spine.audio = Audio(
        voice_path="assets/voice.wav",
        duration_s=round(probe_duration(voice_abs) or total_len, 3),
        word_timings_path=None,  # TODO(real): WhisperX forced alignment -> word-level captions
        provider=provider_used,
    )
    spine.stage(STAGE).provider_used = provider_used
    log.info("tts: %.1fs voice via %s (%d shots)", spine.audio.duration_s, provider_used, len(spine.shots))
    return spine


def run(spine: Run, cfg: Config, *, dry_run: bool = False) -> Run:
    if spine.script is None:
        raise ValueError("tts stage: spine.script missing (run script first)")
    if not spine.shots:
        raise ValueError("tts stage: spine.shots empty (run direction first)")

    return _run_dry(spine, cfg) if dry_run else _run_real(spine, cfg)
