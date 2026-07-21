"""JSONL logger per run. No log platform — logs are files committed to the repo.

Each run gets `runs/<run_id>/run.log.jsonl`: one JSON object per line, appended
as the pipeline progresses. Also mirrors to stderr for live Action output.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path


class _JsonlFileHandler(logging.Handler):
    """Append each record as a single JSON line."""

    def __init__(self, path: Path) -> None:
        super().__init__()
        path.parent.mkdir(parents=True, exist_ok=True)
        self._path = path

    def emit(self, record: logging.LogRecord) -> None:
        try:
            entry = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "msg": record.getMessage(),
            }
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:  # noqa: BLE001 - logging must never crash the run
            self.handleError(record)


def setup_logging(run_log_path: Path, *, level: int = logging.INFO) -> logging.Logger:
    """Configure the `autocast` logger to write JSONL + stderr. Idempotent."""
    logger = logging.getLogger("autocast")
    logger.setLevel(level)
    logger.handlers.clear()  # idempotent: safe to call once per run

    stream = logging.StreamHandler()
    stream.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    logger.addHandler(stream)

    logger.addHandler(_JsonlFileHandler(run_log_path))
    logger.propagate = False
    return logger
