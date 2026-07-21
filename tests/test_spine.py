"""Golden round-trip + validation tests for the spine (Phase 0 mandate)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from autocast.spine import STAGE_ORDER, Run, Shot, StageStatus, Topic


def test_new_run_has_all_stages_pending():
    run = Run.new("2026-07-21")
    assert run.run_id == "2026-07-21"
    assert [s.name for s in run.stages] == list(STAGE_ORDER)
    assert all(s.status is StageStatus.PENDING for s in run.stages)


def test_save_load_roundtrip_is_lossless(tmp_path):
    run = Run.new("2026-07-21")
    run.topic = Topic(title="Why the Roman Concrete Recipe Was Lost", provider="dry-stub")
    run.shots = [
        Shot(idx=0, narration="a", image_prompt="p0", duration_s=5.5, motion="zoom_in", caption="c0"),
        Shot(idx=1, narration="b", image_prompt="p1", duration_s=5.0, motion="pan_right", caption="c1"),
    ]
    run.mark_running("topic")
    run.mark_completed("topic", provider_used="dry-stub")

    path = tmp_path / "run.json"
    run.save(path)
    loaded = Run.load(path)

    assert loaded.model_dump() == run.model_dump()
    assert loaded.is_completed("topic")
    assert loaded.provider_used_map()["topic"] == "dry-stub"


def test_status_and_provider_maps():
    run = Run.new("2026-07-21")
    run.mark_running("script")
    run.mark_completed("script", provider_used="groq-fallback")
    assert run.status_map()["script"] is StageStatus.COMPLETED
    assert run.provider_used_map()["script"] == "groq-fallback"


def test_malformed_spine_rejected(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text('{"run_id": "x", "unknown_field": 1}', encoding="utf-8")
    with pytest.raises(ValidationError):
        Run.load(bad)


def test_shot_requires_positive_duration():
    with pytest.raises(ValidationError):
        Shot(idx=0, narration="a", image_prompt="p", duration_s=0)


def test_unknown_stage_raises():
    run = Run.new("2026-07-21")
    with pytest.raises(KeyError):
        run.stage("does-not-exist")
