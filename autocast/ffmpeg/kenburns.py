"""Build the FFmpeg `zoompan` (Ken Burns) command for one shot.

Free image + FFmpeg fake-motion is the whole video strategy (research §4): we
generate a still image per shot and pan/zoom it into a short clip. This module
produces a CORRECT, INSPECTABLE arg list — no hidden magic — that `video.py`
either runs (real) or logs (dry-run).

zoompan reference: pan/zoom a single frame over `d` output frames. We pre-scale
the source up (so panning has headroom) then zoompan back down to the target size.
"""

from __future__ import annotations

# Motion presets -> (zoom expression, x expression, y expression) for zoompan.
# `on` is the current output frame index; `zoom` the running zoom factor.
# iw/ih are the (upscaled) input dims; ow/oh are zoompan's output dims.
#
# NOTE: zoompan does NOT expose `d` (the frame count) as an expression variable —
# it's a filter *option*, not an eval symbol. Referencing it fails at parse time
# ("Undefined constant ... 'd-1'"). So pans use a `{last}` placeholder that
# build_kenburns_cmd substitutes with the literal last-frame index (frames - 1),
# giving a clean 0->1 progress ramp across the clip.
_MOTION = {
    "zoom_in": {
        "z": "min(zoom+0.0010,1.30)",
        "x": "iw/2-(iw/zoom/2)",
        "y": "ih/2-(ih/zoom/2)",
    },
    "zoom_out": {
        "z": "if(lte(zoom,1.0),1.30,max(1.001,zoom-0.0010))",
        "x": "iw/2-(iw/zoom/2)",
        "y": "ih/2-(ih/zoom/2)",
    },
    "pan_left": {
        "z": "1.20",
        "x": "(iw-iw/zoom)*(1-on/{last})",
        "y": "ih/2-(ih/zoom/2)",
    },
    "pan_right": {
        "z": "1.20",
        "x": "(iw-iw/zoom)*(on/{last})",
        "y": "ih/2-(ih/zoom/2)",
    },
}

# Upscale factor applied before zoompan so pans/zooms have headroom without
# resampling artifacts.
_UPSCALE = 4


def _preset(motion: str) -> dict[str, str]:
    return _MOTION.get(motion, _MOTION["zoom_in"])


def build_kenburns_cmd(
    *,
    image_path: str,
    out_path: str,
    duration_s: float,
    motion: str,
    width: int,
    height: int,
    fps: int,
) -> list[str]:
    """Return the full FFmpeg argv for one Ken Burns clip.

    The returned list is exactly what `subprocess.run` receives — no shell.
    """
    frames = max(1, round(duration_s * fps))
    # Last output-frame index for the pan progress ramp (on/last spans 0->1).
    # Guard against a 1-frame clip so we never divide by zero.
    last = max(1, frames - 1)
    up_w, up_h = width * _UPSCALE, height * _UPSCALE
    p = _preset(motion)
    z = p["z"].format(last=last)
    x = p["x"].format(last=last)
    y = p["y"].format(last=last)

    # Scale up -> zoompan -> ensure exact output size + fps.
    vf = (
        f"scale={up_w}:{up_h},"
        f"zoompan=z='{z}':x='{x}':y='{y}'"
        f":d={frames}:s={width}x{height}:fps={fps}"
    )

    return [
        "ffmpeg",
        "-y",
        "-loop", "1",
        "-i", image_path,
        "-t", f"{duration_s:.3f}",
        "-vf", vf,
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-r", str(fps),
        out_path,
    ]
