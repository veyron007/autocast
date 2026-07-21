"""The run manifest — append/update `runs/manifest.json`, the history store.

Double duty (per CTO doc §4):
1. The UI reads this ONE file to render its history list, then lazy-loads a
   specific run.json on click.
2. Committing it every run is the GitHub-Actions keep-alive (a scheduled workflow
   auto-disables after 60 days of no commits).

The manifest is a list of small rows, one per run, keyed by run_id. Re-running a
day UPDATES that day's row rather than appending a duplicate.
"""

from __future__ import annotations

import json
from pathlib import Path

from autocast.spine import Run


def _row_from_run(run: Run) -> dict:
    """The small row the UI needs: metadata + thumb + link, no heavy blobs."""
    return {
        "run_id": run.run_id,
        "title": run.topic.title if run.topic else None,
        "status": _overall_status(run),
        "youtube_video_id": run.upload.youtube_video_id if run.upload else None,
        "privacy": run.upload.privacy if run.upload else None,
        "thumb_path": run.thumbnail.path if run.thumbnail else None,
        "created_at": run.created_at,
    }


def _overall_status(run: Run) -> str:
    """A one-word rollup for the history list."""
    statuses = [rec.status.value for rec in run.stages]
    if any(s == "failed" for s in statuses):
        return "failed"
    if all(s == "completed" for s in statuses):
        return "completed"
    # Everything either done or intentionally skipped (e.g. upload without creds):
    # the video is rendered even though it wasn't published.
    if all(s in ("completed", "skipped") for s in statuses) and any(s == "skipped" for s in statuses):
        return "rendered"
    if any(s in ("running", "completed", "skipped") for s in statuses):
        return "partial"
    return "pending"


def update_manifest(manifest_path: Path, run: Run) -> None:
    """Insert-or-replace this run's row, keeping the list sorted by run_id desc."""
    rows: list[dict] = []
    if manifest_path.exists():
        try:
            rows = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            rows = []  # corrupt manifest should not kill the run; rebuild the row

    rows = [r for r in rows if r.get("run_id") != run.run_id]
    rows.append(_row_from_run(run))
    rows.sort(key=lambda r: r.get("run_id", ""), reverse=True)

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
