"""End-to-end dry-run: prove the spine flows through every stage to `completed`,
and prove resumability (a second run skips completed stages)."""

from __future__ import annotations

from autocast.config import Config
from autocast.orchestrator import run_pipeline
from autocast.spine import Run, StageStatus


def _cfg(tmp_path) -> Config:
    return Config(runs_dir=tmp_path / "runs", queue_path=tmp_path / "queue" / "topics.json")


def test_dry_run_completes_all_stages(tmp_path):
    cfg = _cfg(tmp_path)
    spine = run_pipeline("2026-07-21", cfg, dry_run=True)

    assert all(rec.status is StageStatus.COMPLETED for rec in spine.stages)
    assert spine.topic is not None
    assert len(spine.shots) == 3
    assert all(s.image_path and s.clip_path for s in spine.shots)
    assert spine.video is not None and spine.video.final_path == "assets/final.mp4"
    assert spine.upload is not None and spine.upload.privacy == "private"
    assert spine.upload.youtube_video_id == "DRYRUN_VIDEO_ID"

    # run.json exists and re-loads (valid).
    reloaded = Run.load(cfg.run_json_path("2026-07-21"))
    assert reloaded.is_completed("upload")


def test_resume_skips_completed_stages(tmp_path):
    cfg = _cfg(tmp_path)
    run_pipeline("2026-07-21", cfg, dry_run=True)
    # Second invocation should find everything completed and skip.
    spine2 = run_pipeline("2026-07-21", cfg, dry_run=True)
    assert all(rec.attempts == 1 for rec in spine2.stages)  # never re-ran


def test_manifest_written(tmp_path):
    cfg = _cfg(tmp_path)
    run_pipeline("2026-07-21", cfg, dry_run=True)
    assert cfg.manifest_path().exists()
