"""Final mux: concat the Ken Burns clips, add voice + (ducked) music, burn captions.

Two command builders, both returning inspectable argv lists:
- `build_concat_cmd`: stitch per-shot clips into one silent reel via the concat
  demuxer (a concat list file, the boring robust way).
- `build_mux_cmd`: overlay voice + optional music (side-chain ducked) and burn the
  .ass captions onto the reel -> final.mp4.
"""

from __future__ import annotations

from pathlib import Path


def write_concat_list(list_path: Path, clip_paths: list[str]) -> Path:
    """Write the concat demuxer list file. Paths must be quoted per FFmpeg rules."""
    list_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"file '{p}'" for p in clip_paths]
    list_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return list_path


def build_concat_cmd(*, concat_list_path: str, out_path: str) -> list[str]:
    """Concat silent clips into one reel (stream copy — fast, lossless)."""
    return [
        "ffmpeg",
        "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", concat_list_path,
        "-c", "copy",
        out_path,
    ]


def build_mux_cmd(
    *,
    reel_path: str,
    voice_path: str,
    out_path: str,
    music_path: str | None = None,
    captions_path: str | None = None,
    music_gain_db: float = -18.0,
) -> list[str]:
    """Combine the silent reel + voice (+ ducked music) (+ burned captions).

    Inputs: 0=reel(video), 1=voice, [2=music]. We lower music by `music_gain_db`
    and mix with voice; the video is stream-copied unless we must burn captions
    (subtitles filter forces a re-encode of the video stream).
    """
    cmd = ["ffmpeg", "-y", "-i", reel_path, "-i", voice_path]
    fil: list[str] = []
    map_audio = "1:a"

    if music_path:
        cmd += ["-i", music_path]
        # Duck: reduce music, then amix with voice. (Real sidechain ducking is a
        # Phase-4 polish; static gain is the honest crude default.)
        filt = (
            f"[2:a]volume={music_gain_db}dB[bg];"
            f"[1:a][bg]amix=inputs=2:duration=first:dropout_transition=2[aout]"
        )
        fil.append(filt)
        map_audio = "[aout]"

    video_map = "0:v"
    if captions_path:
        # Burning subtitles re-encodes video; chain it into the filtergraph.
        sub = f"[0:v]subtitles='{captions_path}'[vout]"
        fil.append(sub)
        video_map = "[vout]"

    if fil:
        cmd += ["-filter_complex", ";".join(fil)]

    cmd += ["-map", video_map, "-map", map_audio]

    if video_map == "0:v":
        cmd += ["-c:v", "copy"]  # no caption burn -> keep the reel as-is
    else:
        cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p"]

    cmd += ["-c:a", "aac", "-b:a", "192k", "-shortest", out_path]
    return cmd
