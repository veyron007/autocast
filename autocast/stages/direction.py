"""Stage: direction — script -> the shot list (THE keystone).

`shots[]` drives everything downstream: image count, Ken Burns clip count, scene
pacing, caption timing, and total duration. Reads `spine.script`, writes
`spine.shots`. The LLM (Gemini responseSchema) is stubbed behind the cascade;
in dry-run we emit a real, well-formed 3-shot list.

Cerebras is disallowed here (allow_cerebras=False) — its 8k context can't hold
the full script for structured shot-listing (research §1).
"""

from __future__ import annotations

import json
import logging
import re

from autocast.config import Config
from autocast.providers.llm import build_llm_providers, try_llm
from autocast.spine import Run, Shot

log = logging.getLogger("autocast.stages.direction")

STAGE = "direction"

_MOTIONS = ("zoom_in", "zoom_out", "pan_left", "pan_right")
_MIN_SHOTS = 3
_MAX_SHOTS = 12

# Deterministic 3-shot dry-run shot list. Real, downstream-usable data.
_DRY_SHOTS = [
    {
        "narration": "Two thousand years ago, engineers built structures we still cannot fully explain.",
        "image_prompt": "ancient roman harbor at golden hour, dramatic light, cinematic, wide shot",
        "duration_s": 5.5,
        "motion": "zoom_in",
        "caption": "It outlasted empires",
    },
    {
        "narration": "The secret was hidden in a recipe that was lost for centuries.",
        "image_prompt": "close up of weathered ancient stone wall, moody, high detail, cinematic",
        "duration_s": 5.0,
        "motion": "pan_right",
        "caption": "A recipe, lost",
    },
    {
        "narration": "Today, that knowledge is teaching us how to build for the future.",
        "image_prompt": "modern laboratory with glowing samples, futuristic, clean, cinematic",
        "duration_s": 5.5,
        "motion": "zoom_out",
        "caption": "Rediscovered",
    },
]


def _direction_prompt(script: str) -> str:
    return (
        "You are a video director. Break the narration below into a shot list.\n"
        "Return ONLY a JSON array (no prose, no markdown fences). Each element:\n"
        '  {"narration": str,   // the exact words spoken during this shot\n'
        '   "image_prompt": str, // a vivid, cinematic still-image prompt for this beat\n'
        '   "motion": str,       // one of: zoom_in, zoom_out, pan_left, pan_right\n'
        '   "caption": str}      // <=5 words of on-screen text\n'
        "Rules: 4-8 shots. The narration fields, in order, must reconstruct the whole "
        "script with nothing left out and nothing invented. image_prompt must be "
        "concrete and photographic.\n\n"
        f"NARRATION:\n{script}"
    )


def _extract_json_array(text: str) -> list:
    """Pull a JSON array out of an LLM response that may wrap it in fences/prose."""
    fenced = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.DOTALL)
    candidate = fenced.group(1) if fenced else None
    if candidate is None:
        start, end = text.find("["), text.rfind("]")
        if start == -1 or end <= start:
            raise ValueError("no JSON array found in LLM output")
        candidate = text[start : end + 1]
    data = json.loads(candidate)
    if not isinstance(data, list) or not data:
        raise ValueError("parsed JSON is not a non-empty array")
    return data


def _coerce_shots(raw: list) -> list[dict]:
    """Validate + normalize LLM shot dicts into the fields Shot needs."""
    shots: list[dict] = []
    for item in raw[:_MAX_SHOTS]:
        if not isinstance(item, dict):
            continue
        narration = str(item.get("narration", "")).strip()
        image_prompt = str(item.get("image_prompt", "")).strip()
        if not narration or not image_prompt:
            continue
        motion = str(item.get("motion", "zoom_in")).strip().lower()
        if motion not in _MOTIONS:
            motion = _MOTIONS[len(shots) % len(_MOTIONS)]
        shots.append(
            {
                "narration": narration,
                "image_prompt": image_prompt,
                "motion": motion,
                "caption": str(item.get("caption", "")).strip()[:60],
                # Provisional; the tts stage overwrites this with measured audio length.
                "duration_s": float(item.get("duration_s", 5.0)) or 5.0,
            }
        )
    if len(shots) < _MIN_SHOTS:
        raise ValueError(f"only {len(shots)} valid shots parsed (need >= {_MIN_SHOTS})")
    return shots


def run(spine: Run, cfg: Config, *, dry_run: bool = False) -> Run:
    if spine.script is None:
        raise ValueError("direction stage: spine.script missing (run script first)")

    prompt = _direction_prompt(spine.script.full_text)
    providers = build_llm_providers(
        cfg, prompt=prompt, kind="direction", allow_cerebras=False, dry_run=dry_run
    )
    llm_text, provider = try_llm(providers)

    if dry_run or not llm_text:
        raw_shots = _DRY_SHOTS
    else:
        try:
            raw_shots = _coerce_shots(_extract_json_array(llm_text))
            log.info("direction: parsed %d shots from %s", len(raw_shots), provider)
        except Exception as exc:  # noqa: BLE001 - never let the pipeline die on parse
            log.warning("direction: shot-list parse failed (%s); using template shots", exc)
            raw_shots = _DRY_SHOTS
            provider = "template-fallback"

    spine.shots = [
        Shot(
            idx=i,
            narration=s["narration"],
            image_prompt=s["image_prompt"],
            duration_s=float(s["duration_s"]),
            motion=s["motion"],
            caption=s["caption"],
        )
        for i, s in enumerate(raw_shots)
    ]
    spine.stage(STAGE).provider_used = provider
    log.info("direction: %d shots via %s", len(spine.shots), provider)
    return spine
