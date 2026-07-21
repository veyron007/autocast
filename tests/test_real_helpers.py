"""Unit tests for the real-path helpers (no network, no FFmpeg).

These cover the fragile parsing/degradation logic added in Cycle 4: LLM shot-list
parsing, text cleaning, the template-fallback cascade, and the skip rollup.
"""

from __future__ import annotations

import pytest

from autocast.config import Config
from autocast.ffmpeg.kenburns import build_kenburns_cmd
from autocast.providers.cascade import Provider
from autocast.providers.image import _looks_like_image
from autocast.providers.llm import TEMPLATE_FALLBACK, build_llm_providers, try_llm
from autocast.spine import Run, StageStatus
from autocast.stages.direction import _coerce_shots, _extract_json_array
from autocast.stages.script import _clean_script
from autocast.stages.topic import _clean_title
from autocast.util.manifest import _overall_status


# ---- direction: JSON shot-list extraction ----

def test_extract_json_array_bare():
    got = _extract_json_array('[{"a": 1}, {"b": 2}]')
    assert got == [{"a": 1}, {"b": 2}]


def test_extract_json_array_fenced():
    text = 'Here is your shot list:\n```json\n[{"narration": "x"}]\n```\nHope it helps!'
    assert _extract_json_array(text) == [{"narration": "x"}]


def test_extract_json_array_prose_wrapped():
    text = 'Sure!\n[{"narration": "a"}, {"narration": "b"}]\nLet me know if you want changes.'
    assert len(_extract_json_array(text)) == 2


def test_extract_json_array_raises_without_array():
    with pytest.raises(ValueError):
        _extract_json_array("no json here at all")


# ---- direction: shot coercion ----

def _raw(n: int) -> list[dict]:
    return [
        {"narration": f"line {i}", "image_prompt": f"prompt {i}", "motion": "zoom_in", "caption": "c"}
        for i in range(n)
    ]


def test_coerce_shots_normalizes_bad_motion():
    raw = _raw(3)
    raw[0]["motion"] = "spin_around"  # invalid -> coerced to an allowed motion
    shots = _coerce_shots(raw)
    assert all(s["motion"] in ("zoom_in", "zoom_out", "pan_left", "pan_right") for s in shots)


def test_coerce_shots_drops_incomplete_entries():
    raw = _raw(4)
    raw[1] = {"narration": "", "image_prompt": "x"}  # missing narration -> dropped
    shots = _coerce_shots(raw)
    assert len(shots) == 3


def test_coerce_shots_requires_minimum():
    with pytest.raises(ValueError):
        _coerce_shots(_raw(2))


def test_coerce_shots_provisional_duration_positive():
    shots = _coerce_shots(_raw(3))
    assert all(s["duration_s"] > 0 for s in shots)


# ---- script / topic text cleaning ----

def test_clean_script_strips_markdown_and_labels():
    raw = "# Title\n**Narration:** Once upon a time.\nThe end."
    cleaned = _clean_script(raw)
    assert "#" not in cleaned and "**" not in cleaned
    assert "Once upon a time." in cleaned


def test_clean_title_takes_first_meaningful_line():
    assert _clean_title('  "The Lost Roman Recipe"  ') == "The Lost Roman Recipe"


def test_clean_title_strips_numbering():
    assert _clean_title("1. How Bridges Survive Earthquakes") == "How Bridges Survive Earthquakes"


# ---- image magic-byte validation ----

def test_looks_like_image_accepts_jpeg():
    assert _looks_like_image(b"\xff\xd8\xff" + b"\x00" * 3000)


def test_looks_like_image_rejects_html_error_page():
    assert not _looks_like_image(b"<html>429 Too Many Requests</html>")


# ---- Ken Burns command construction (zoompan `d` regression) ----

def _vf(cmd: list[str]) -> str:
    return cmd[cmd.index("-vf") + 1]


@pytest.mark.parametrize("motion", ["zoom_in", "zoom_out", "pan_left", "pan_right"])
def test_kenburns_never_references_zoompan_option_d(motion):
    """`d` is a zoompan *option*, not an expression variable — referencing it in
    x/y/z fails at parse time ('Undefined constant ... d-1') and produces a
    0-byte clip. Pans must bake the literal frame count instead. Regression for
    the Cycle-7 real-render bug."""
    vf = _vf(
        build_kenburns_cmd(
            image_path="in.png",
            out_path="out.mp4",
            duration_s=3.732,
            motion=motion,
            width=1920,
            height=1080,
            fps=30,
        )
    )
    zoompan = vf.split("zoompan=", 1)[1]
    # No bare `d` token survives into the eval expressions, and the {last}
    # placeholder was fully substituted (no stray braces).
    assert "d-1" not in zoompan
    assert "{" not in zoompan and "}" not in zoompan


def test_kenburns_pan_bakes_last_frame_index():
    """pan_right ramps on/last from 0->1; last == frames-1 == round(3.732*30)-1."""
    vf = _vf(
        build_kenburns_cmd(
            image_path="in.png",
            out_path="out.mp4",
            duration_s=3.732,
            motion="pan_right",
            width=1920,
            height=1080,
            fps=30,
        )
    )
    assert "on/111" in vf  # round(3.732*30)=112 -> last=111


# ---- LLM cascade: graceful template fallback ----

def test_try_llm_success_returns_value():
    text, provider = try_llm([Provider("ok", lambda: "hello")])
    assert text == "hello" and provider == "ok"


def test_try_llm_all_fail_returns_template_sentinel():
    def boom() -> str:
        raise RuntimeError("down")

    text, provider = try_llm([Provider("a", boom), Provider("b", boom)])
    assert text is None and provider == TEMPLATE_FALLBACK


# ---- LLM cascade: keyed provider selection & ordering (no network) ----

def _cfg(**overrides) -> Config:
    """Build a Config with all LLM keys forced to a known state (so a developer's
    shell env can't leak a key into these ordering assertions)."""
    base = dict(
        gemini_api_key=None,
        groq_api_key=None,
        cerebras_api_key=None,
        cloudflare_api_token=None,
        cloudflare_account_id=None,
        cloudflare_budget_cents=0,
    )
    base.update(overrides)
    return Config(**base)


def _names(cfg: Config, **kw) -> list[str]:
    return [p.name for p in build_llm_providers(cfg, prompt="p", kind="script", **kw)]


def test_llm_providers_keyless_only_without_keys():
    # No key present -> only the keyless final attempt is in the chain.
    assert _names(_cfg()) == ["pollinations-openai"]


def test_llm_providers_dry_run_is_single_stub():
    assert _names(_cfg(), dry_run=True) == ["dry-stub"]


def test_llm_providers_prepends_gemini_when_keyed():
    names = _names(_cfg(gemini_api_key="k"))
    assert names[0] == "gemini" and names[-1] == "pollinations-openai"


def test_llm_providers_documented_order():
    names = _names(_cfg(gemini_api_key="a", groq_api_key="b", cerebras_api_key="c"))
    assert names == ["gemini", "groq", "cerebras", "pollinations-openai"]


def test_llm_providers_excludes_cerebras_for_direction():
    # direction passes allow_cerebras=False (8k context can't hold the shot list).
    assert "cerebras" not in _names(_cfg(cerebras_api_key="c"), allow_cerebras=False)


def test_llm_providers_cloudflare_gated_on_budget():
    creds = dict(cloudflare_api_token="t", cloudflare_account_id="a")
    off = _names(_cfg(**creds, cloudflare_budget_cents=0))
    on = _names(_cfg(**creds, cloudflare_budget_cents=5))
    assert "cloudflare" not in off  # bills on overage -> off until a budget is set
    assert "cloudflare" in on


# ---- skip rollup ----

def test_overall_status_rendered_when_upload_skipped():
    run = Run.new("2026-07-21")
    for rec in run.stages:
        rec.status = StageStatus.COMPLETED
    run.mark_skipped("upload", "no creds")
    assert _overall_status(run) == "rendered"


def test_overall_status_completed_when_all_done():
    run = Run.new("2026-07-21")
    for rec in run.stages:
        rec.status = StageStatus.COMPLETED
    assert _overall_status(run) == "completed"
