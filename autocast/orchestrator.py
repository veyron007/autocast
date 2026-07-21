"""The orchestrator — runs the stage chain in order, threading ONE spine.

Responsibilities (and nothing else — stages do the work):
- Knows the canonical stage order (the ONLY thing that does).
- RESUMABLE: loads an existing run.json and SKIPS stages already `completed`.
- Writes `runs/<run_id>/run.json` after EVERY stage (crash-safe, inspectable).
- On a stage failure: records `failed` + the error, saves, and stops the chain —
  but the partial spine is still written (a failed run is history too).
- Updates the manifest at the end (history + GitHub-Actions keep-alive).

Run it: `python -m autocast.orchestrator --dry-run`
"""

from __future__ import annotations

import argparse
import logging
from datetime import date

from autocast.config import Config, load_config
from autocast.spine import STAGE_ORDER, Run, StageSkipped, StageStatus
from autocast.stages import (
    assets,
    direction,
    images,
    script,
    thumbnail,
    topic,
    tts,
    upload,
    video,
)
from autocast.util.logging import setup_logging
from autocast.util.manifest import update_manifest

# Map stage name -> its module. The orchestrator owns this ordering, not stages.
_STAGES = {
    "topic": topic,
    "script": script,
    "direction": direction,
    "images": images,
    "tts": tts,
    "assets": assets,
    "video": video,
    "thumbnail": thumbnail,
    "upload": upload,
}

log = logging.getLogger("autocast.orchestrator")


def _load_or_new(cfg: Config, run_id: str) -> Run:
    """Resume an existing run.json if present, else start a fresh spine."""
    path = cfg.run_json_path(run_id)
    if path.exists():
        log.info("orchestrator: resuming existing run %s", run_id)
        return Run.load(path)
    log.info("orchestrator: new run %s", run_id)
    return Run.new(run_id)


def run_pipeline(run_id: str, cfg: Config, *, dry_run: bool = False) -> Run:
    """Execute the full chain for one run_id. Returns the final spine."""
    run_json = cfg.run_json_path(run_id)
    spine = _load_or_new(cfg, run_id)
    # Mirror render settings into the spine snapshot.
    spine.config_snapshot.voice = cfg.voice
    spine.config_snapshot.aspect = f"{cfg.width}x{cfg.height}"
    spine.config_snapshot.target_len_s = cfg.target_len_s
    spine.save(run_json)

    for name in STAGE_ORDER:
        if spine.is_completed(name):
            log.info("stage %s: already completed -> skip", name)
            continue

        module = _STAGES[name]
        spine.mark_running(name)
        spine.save(run_json)
        try:
            spine = module.run(spine, cfg, dry_run=dry_run)
            spine.mark_completed(name)
            spine.save(run_json)
            log.info("stage %s: completed", name)
        except StageSkipped as skip:
            spine.mark_skipped(name, str(skip))
            spine.save(run_json)
            log.info("stage %s: skipped -> %s", name, skip)
            continue  # an intentional skip is not a failure; keep going
        except Exception as exc:  # noqa: BLE001 - record + stop, don't crash silently
            spine.mark_failed(name, f"{type(exc).__name__}: {exc}")
            spine.save(run_json)
            log.error("stage %s: FAILED -> %s", name, exc)
            break  # blast radius: this day only; tomorrow's cron is unaffected

    # History + keep-alive: always update the manifest, success or partial.
    update_manifest(cfg.manifest_path(), spine)
    return spine


def _summary(spine: Run) -> str:
    parts = [f"{rec.name}={rec.status.value}" for rec in spine.stages]
    return " ".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(prog="autocast", description="AutoCast daily pipeline")
    parser.add_argument(
        "--run-id",
        default=date.today().isoformat(),
        help="run id = date (YYYY-MM-DD). Defaults to today (UTC-naive local date).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="no network / no FFmpeg / no keys — flow the spine end-to-end with stubs.",
    )
    args = parser.parse_args()

    cfg = load_config()
    run_log = cfg.run_dir(args.run_id) / "run.log.jsonl"
    setup_logging(run_log)

    log.info("=== AutoCast run %s (dry_run=%s) ===", args.run_id, args.dry_run)
    spine = run_pipeline(args.run_id, cfg, dry_run=args.dry_run)

    log.info("=== done: %s ===", _summary(spine))
    # Success = nothing FAILED. A SKIPPED stage (e.g. upload with no creds on a
    # keyless local render) is an intentional, non-failing outcome.
    ok = not any(rec.status is StageStatus.FAILED for rec in spine.stages)
    print(f"run {spine.run_id}: {_summary(spine)}")
    print(f"run.json -> {cfg.run_json_path(spine.run_id)}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
