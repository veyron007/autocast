"""TTS provider cascade: kokoro -> edge-tts -> macOS `say`.

Two concerns, both tool-independent:
- SYNTH: text -> a voice audio file. Kokoro is the commercial-safe (Apache-2.0)
  primary when installed; edge-tts is the light, keyless, cross-platform default
  (works in CI); macOS `say` is the zero-dependency local dev fallback.
- TIMINGS: word-level timestamps (a future WhisperX forced-alignment pass). The
  render currently syncs on SHOT windows (each Ken Burns clip == its narration's
  measured length), so word timings are optional polish, not on the render path.

Each real synth writes an engine-native container (mp3/aiff/wav) to `base.<ext>`
and returns the actual path. The tts stage then normalizes + pads it to the shot
duration with FFmpeg, so the container here is an implementation detail.

Dry-run keeps the original behavior: touch an empty wav + fabricate timings.
"""

from __future__ import annotations

import logging
import platform
import shutil
import subprocess
from pathlib import Path

from autocast.config import Config
from autocast.providers.cascade import Provider

log = logging.getLogger("autocast.providers.tts")

# A dry synth provider returns (wav_path, provider-native word timings | None).
SynthResult = tuple[str, list[dict] | None]

# edge-tts voice for the keyless path (cfg.voice defaults to a Kokoro voice name,
# which edge-tts would reject). Warm, neutral US male narrator — good for faceless.
_EDGE_VOICE = "en-US-AndrewNeural"


def _dry_synth(text: str, out_wav: str, *, target_len_s: float) -> SynthResult:
    """Touch an empty wav and fabricate evenly-spaced word timings."""
    Path(out_wav).parent.mkdir(parents=True, exist_ok=True)
    Path(out_wav).touch()

    words = text.split()
    if not words:
        return out_wav, []
    per = target_len_s / len(words)
    timings = [
        {"word": w, "start": round(i * per, 3), "end": round((i + 1) * per, 3)}
        for i, w in enumerate(words)
    ]
    return out_wav, timings


def build_tts_providers(
    cfg: Config,
    *,
    text: str,
    out_wav: str,
    target_len_s: float,
    dry_run: bool = False,
) -> list[Provider[SynthResult]]:
    """Dry-run only: the whole-script stub (kept for the dry pipeline + tests)."""
    return [
        Provider("dry-tts", lambda: _dry_synth(text, out_wav, target_len_s=target_len_s)),
    ]


# ---- real per-text synth engines (used by the tts stage, one call per shot) ----


def _synth_kokoro(text: str, base: str, voice: str) -> str:
    """Kokoro-82M -> base.wav. Commercial-safe primary; skipped if not installed."""
    try:
        import numpy as np  # type: ignore
        import soundfile as sf  # type: ignore
        from kokoro import KPipeline  # type: ignore
    except Exception as exc:  # noqa: BLE001 - optional heavy dep; cascade moves on
        raise RuntimeError(f"kokoro unavailable: {exc}") from exc

    pipe = KPipeline(lang_code="a")
    chunks = [audio for _gs, _ps, audio in pipe(text, voice=voice)]
    if not chunks:
        raise RuntimeError("kokoro produced no audio")
    out = f"{base}.wav"
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    sf.write(out, np.concatenate(chunks), 24000)
    return out


def _synth_edge(text: str, base: str, voice: str) -> str:
    """edge-tts -> base.mp3. Light, keyless, cross-platform (the CI default)."""
    try:
        import asyncio

        import edge_tts  # type: ignore
    except Exception as exc:  # noqa: BLE001 - optional dep; cascade moves on
        raise RuntimeError(f"edge-tts unavailable: {exc}") from exc

    out = f"{base}.mp3"
    Path(out).parent.mkdir(parents=True, exist_ok=True)

    async def _go() -> None:
        await edge_tts.Communicate(text, voice).save(out)

    asyncio.run(_go())
    if not Path(out).exists() or Path(out).stat().st_size == 0:
        raise RuntimeError("edge-tts wrote no audio")
    return out


def _synth_say(text: str, base: str) -> str:
    """macOS `say` -> base.aiff. Zero-dependency local dev fallback (darwin only)."""
    if platform.system() != "Darwin" or not shutil.which("say"):
        raise RuntimeError("macOS `say` unavailable on this platform")
    out = f"{base}.aiff"
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(["say", "-o", out, text], capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"say failed: {proc.stderr.strip()}")
    return out


def build_synth_providers(cfg: Config, *, text: str, base: str) -> list[Provider[str]]:
    """Ordered real synth providers for ONE piece of text. Each returns the path
    of the audio file it wrote. Import/availability failures fall through."""
    voice = cfg.voice
    return [
        Provider("kokoro-82m", lambda: _synth_kokoro(text, base, voice)),
        Provider("edge-tts", lambda: _synth_edge(text, base, _EDGE_VOICE)),
        Provider("macos-say", lambda: _synth_say(text, base)),
    ]
