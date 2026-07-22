"""Seed-content regression tests (Cycle 9).

These lock in the fix for the "every keyless video is byte-identical" bug: each
evergreen seed must carry a DISTINCT bespoke script + shot list, the topic stage
must ROTATE through them by date, and the script/direction stages must actually
use the day's seed on a keyless run.
"""

from __future__ import annotations

from autocast.config import Config
from autocast.seeds import (
    SEED_TITLES,
    SEEDS,
    TEMPLATE_SEED,
    generic_script,
    generic_shots,
    pick_seed_index,
    rotated_seed_titles,
    seed_for_title,
)
from autocast.spine import Run
from autocast.stages import direction, script, topic

_MOTIONS = {"zoom_in", "zoom_out", "pan_left", "pan_right"}
_SHOT_KEYS = {"narration", "image_prompt", "motion", "caption", "duration_s"}


# ---- seed data integrity ----

def test_seed_titles_unique():
    # Cycle 11 doubled the keyless rotation 5 -> 10; Cycle 13 grew it 10 -> 15;
    # Cycle 23 grew it 15 -> 20 (crypto/navigation/neuroscience/chemistry/geology
    # seeds). Guard against regressions that would silently shrink the channel's
    # pre-repeat runway back down.
    assert len(SEED_TITLES) == len(set(SEED_TITLES)) >= 20


def test_every_seed_shot_is_wellformed():
    for seed in SEEDS:
        assert len(seed.shots) >= 3
        for shot in seed.shots:
            assert _SHOT_KEYS <= set(shot)
            assert shot["motion"] in _MOTIONS
            assert shot["narration"].strip() and shot["image_prompt"].strip()
            assert float(shot["duration_s"]) > 0


def test_every_caption_is_five_words_or_fewer():
    # Captions burn onto the video as ≤5-word beats — a long one overflows the
    # lower third. Lock the constraint so a future seed can't quietly break it.
    for seed in SEEDS:
        for shot in seed.shots:
            assert 1 <= len(shot["caption"].split()) <= 5, seed.title


def test_seed_script_reconstructs_shot_narrations():
    # The LLM contract the direction prompt demands: narrations, in order, ARE
    # the script. Holds for templates too.
    for seed in SEEDS:
        assert seed.script == " ".join(s["narration"] for s in seed.shots)


# ---- the actual bug: content must be DISTINCT across seeds ----

def test_all_seed_scripts_are_byte_distinct():
    scripts = [seed.script for seed in SEEDS]
    assert len(set(scripts)) == len(scripts)


def test_all_seed_image_prompt_sets_are_distinct():
    # No two seeds share the same ordered image-prompt list -> visually different.
    fingerprints = [tuple(s["image_prompt"] for s in seed.shots) for seed in SEEDS]
    assert len(set(fingerprints)) == len(fingerprints)


def test_generic_shots_differ_from_every_seed():
    generic = tuple(s["narration"] for s in generic_shots("Any Title"))
    for seed in SEEDS:
        assert tuple(s["narration"] for s in seed.shots) != generic


def test_generic_script_is_coherent_with_generic_shots():
    # The generic fallback must satisfy the same invariant as a seed: the script
    # is exactly the shot narrations joined (keeps captions/TTS/beats aligned).
    title = "A Topic With No Bespoke Seed"
    assert generic_script(title) == " ".join(
        s["narration"] for s in generic_shots(title)
    )
    assert title in generic_script(title)  # generic narration still names the topic


# ---- rotation ----

def test_pick_seed_index_is_in_range_and_deterministic():
    n = len(SEED_TITLES)
    assert pick_seed_index("2026-07-21", n) == pick_seed_index("2026-07-21", n)
    assert 0 <= pick_seed_index("2026-07-21", n) < n


def test_pick_seed_index_bad_date_defaults_to_zero():
    assert pick_seed_index("not-a-date", len(SEED_TITLES)) == 0


def test_rotation_covers_all_seeds_across_a_cycle():
    # Over N consecutive days every seed is picked exactly once (full rotation).
    days = [f"2026-07-{d:02d}" for d in range(1, 1 + len(SEED_TITLES))]
    firsts = {rotated_seed_titles(day)[0] for day in days}
    assert firsts == set(SEED_TITLES)


def test_consecutive_days_pick_different_seeds():
    assert rotated_seed_titles("2026-07-21")[0] != rotated_seed_titles("2026-07-22")[0]


def test_seed_for_title_roundtrip_and_miss():
    assert seed_for_title(SEED_TITLES[0]).title == SEED_TITLES[0]
    assert seed_for_title("A Topic With No Bespoke Seed") is None


# ---- stage integration: keyless runs produce different content per day ----

def _keyless_cfg(tmp_path) -> Config:
    # No LLM keys and an out-of-tree queue path -> forces the template path.
    return Config(
        runs_dir=tmp_path / "runs",
        queue_path=tmp_path / "queue" / "topics.json",
        gemini_api_key=None,
        groq_api_key=None,
        cerebras_api_key=None,
        cloudflare_api_token=None,
    )


def _content_for_day(run_id: str, cfg: Config) -> tuple[str, list[str]]:
    """Run topic->script->direction in dry-run for a day; return (script text,
    per-shot image prompts)."""
    spine = Run.new(run_id)
    spine = topic.run(spine, cfg, dry_run=True)
    spine = script.run(spine, cfg, dry_run=True)
    spine = direction.run(spine, cfg, dry_run=True)
    return spine.script.full_text, [s.image_prompt for s in spine.shots]


def test_keyless_days_render_different_scripts_and_images(tmp_path):
    cfg = _keyless_cfg(tmp_path)
    day_a = _content_for_day("2026-07-21", cfg)
    day_b = _content_for_day("2026-07-22", cfg)
    assert day_a[0] != day_b[0]  # different narration
    assert day_a[1] != day_b[1]  # different image prompts


def test_keyless_content_stages_labelled_template_seed(tmp_path):
    cfg = _keyless_cfg(tmp_path)
    spine = Run.new("2026-07-21")
    spine = topic.run(spine, cfg, dry_run=True)
    spine = script.run(spine, cfg, dry_run=True)
    spine = direction.run(spine, cfg, dry_run=True)
    assert spine.script.provider == TEMPLATE_SEED
    assert spine.stage("direction").provider_used == TEMPLATE_SEED
    # And the script <-> shots stay coherent (script == joined shot narrations).
    assert spine.script.full_text == " ".join(s.narration for s in spine.shots)


def test_human_queued_keyless_live_run_stays_coherent(tmp_path, monkeypatch):
    """A human-queued custom topic (no bespoke seed) on a LIVE keyless run
    (dry_run=False, all LLMs down) must still keep script<->shots coherent —
    regression for the generic-fallback desync bug."""
    cfg = _keyless_cfg(tmp_path)
    cfg.queue_path.parent.mkdir(parents=True)
    cfg.queue_path.write_text(
        '{"queued": ["A Topic With No Bespoke Seed"]}', encoding="utf-8"
    )

    # Simulate every LLM provider down without touching the network.
    down = lambda providers: (None, "template-fallback")  # noqa: E731
    monkeypatch.setattr("autocast.stages.topic.try_llm", down)
    monkeypatch.setattr("autocast.stages.script.try_llm", down)
    monkeypatch.setattr("autocast.stages.direction.try_llm", down)

    spine = Run.new("2026-07-21")
    spine = topic.run(spine, cfg, dry_run=False)
    spine = script.run(spine, cfg, dry_run=False)
    spine = direction.run(spine, cfg, dry_run=False)

    assert spine.topic.title == "A Topic With No Bespoke Seed"  # human queue is verbatim
    # The invariant holds even for a non-seed title on the live keyless path.
    assert spine.script.full_text == " ".join(s.narration for s in spine.shots)
