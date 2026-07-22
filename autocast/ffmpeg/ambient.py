"""Synthesize a CC0 ambient music bed with FFmpeg — no key, no network, no
attribution trap.

Keyless renders were previously scored in silence (the `assets` stage never
produced a music file without a Pixabay/Freesound key). A procedurally
synthesized sine pad has no copyright and needs no attribution — it is the
cleanest zero-cost, ToS-clean bed available: fully offline, deterministic, and
free. It is deliberately crude (a soft drone, not a composition) per the standing
directive's "one working end-to-end chain over polishing a single stage".

The command *builder* is pure and inspectable (like kenburns.py / mux.py); the
side-effecting `run_ffmpeg` in run.py actually shells out.
"""

from __future__ import annotations

# A soft, slow drone: root A2, fifth E3, octave A3, plus a slightly detuned A3.
# The ~0.6 Hz beat between 220 and 220.6 Hz gives the pad gentle, seam-free
# movement WITHOUT an LFO/tremolo filter — so it works on minimal FFmpeg builds
# that ship only the core filters.
_CHORD_HZ: tuple[float, ...] = (110.0, 164.81, 220.0, 220.6)

# amix normalizes by dividing across its inputs (peak ~ -12 dBFS for 4 tones);
# this makeup gain brings the bed back to ~ -6 dBFS like a normally-mastered
# music track. The mux (build_mux_cmd) then ducks it by its own -18 dB so the
# bed sits well under the narration. Keeping the level here full-scale means the
# mux's music_gain_db stays the single source of truth for the final bed level.
_MAKEUP_GAIN = 4.0
_LOWPASS_HZ = 900          # sines carry no harmonics; this just smooths amix seams
_MAX_FADE_S = 1.5          # gentle fade in AND out so the bed never clicks on/off


def build_ambient_cmd(
    *,
    out_path: str,
    duration_s: float,
    sample_rate: int = 24000,
    channels: int = 1,
) -> list[str]:
    """Build the FFmpeg argv that renders a `duration_s`-second CC0 ambient bed.

    The bed fades in and out (fade length scales down for very short clips so the
    two fades never overlap or reference a negative start time). Output is a
    mono/24k PCM WAV by default — the same format the voice track uses, so the
    mux mixes them without a resample surprise.
    """
    dur = max(0.5, float(duration_s))
    fade = min(_MAX_FADE_S, dur / 4.0)
    fade_out_start = max(0.0, dur - fade)

    cmd = ["ffmpeg", "-y"]
    for hz in _CHORD_HZ:
        cmd += ["-f", "lavfi", "-i", f"sine=frequency={hz}:duration={dur:.3f}"]

    labels = "".join(f"[{i}]" for i in range(len(_CHORD_HZ)))
    filt = (
        f"{labels}amix=inputs={len(_CHORD_HZ)}:duration=longest,"
        f"volume={_MAKEUP_GAIN},"
        f"lowpass=f={_LOWPASS_HZ},"
        f"afade=t=in:st=0:d={fade:.3f},"
        f"afade=t=out:st={fade_out_start:.3f}:d={fade:.3f}[a]"
    )

    cmd += [
        "-filter_complex", filt,
        "-map", "[a]",
        "-ar", str(sample_rate),
        "-ac", str(channels),
        "-t", f"{dur:.3f}",
        "-c:a", "pcm_s16le",
        out_path,
    ]
    return cmd
