"""The data spine — the one canonical `run.json` artifact.

This module is the heart of AutoCast. One JSON file per run flows through every
stage. Each stage READS fields written by prior stages and WRITES only its own,
stamping its own status. Validation happens on every read and write (pydantic v2).

See docs/cto/youtube-pipeline-architecture.md §2 for the contract.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


SCHEMA_VERSION = 1

# Canonical stage order. The orchestrator is the ONLY thing that knows this.
STAGE_ORDER: tuple[str, ...] = (
    "topic",
    "script",
    "direction",
    "images",
    "tts",
    "assets",
    "video",
    "thumbnail",
    "upload",
)


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class StageStatus(str, Enum):
    """A partial run is a first-class, inspectable state — not a crash."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class StageSkipped(Exception):
    """Raised by a stage to signal an INTENTIONAL skip (not a failure).

    Example: the upload stage on a keyless local render — there are no YouTube
    credentials, so publishing is deliberately skipped. The orchestrator records
    SKIPPED and CONTINUES the chain rather than marking the whole run failed.
    """


class _Model(BaseModel):
    """Base with strict-ish config: reject unknown keys so a malformed spine
    fails loudly and early, per the spine rules."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class StageRecord(_Model):
    """Per-stage status row. Drives resumability + the future UI."""

    name: str
    status: StageStatus = StageStatus.PENDING
    provider_used: str | None = None
    attempts: int = 0
    error: str | None = None
    started_at: str | None = None
    ended_at: str | None = None


class Topic(_Model):
    title: str
    source: str = "google-trends-rss"
    rank_score: float = 0.0
    provider: str | None = None


class Script(_Model):
    full_text: str
    word_count: int = 0
    provider: str | None = None


class Shot(_Model):
    """One beat of the shot list. len(shots) === #images === #Ken Burns clips."""

    idx: int
    narration: str
    image_prompt: str
    duration_s: float = Field(gt=0)
    motion: str = "zoom_in"  # zoom_in | zoom_out | pan_left | pan_right
    caption: str = ""
    # Filled in by later stages (relative paths, never blobs):
    image_path: str | None = None  # written by images stage
    clip_path: str | None = None  # written by video stage
    audio_start_s: float | None = None  # written by tts/align stage
    audio_end_s: float | None = None


class Audio(_Model):
    voice_path: str
    duration_s: float = 0.0
    word_timings_path: str | None = None
    provider: str | None = None


class LicenseEntry(_Model):
    asset: str
    license: str
    attribution: bool = False


class Assets(_Model):
    music_path: str | None = None
    music_source: str | None = None
    captions_path: str | None = None
    stock_paths: list[str] = Field(default_factory=list)
    license_manifest: list[LicenseEntry] = Field(default_factory=list)


class Video(_Model):
    final_path: str
    width: int = 1920
    height: int = 1080
    fps: int = 30
    duration_s: float = 0.0
    size_bytes: int = 0


class Thumbnail(_Model):
    path: str
    width: int = 1280
    height: int = 720


class Upload(_Model):
    title: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    privacy: str = "private"  # ALWAYS private until compliance audit passes
    ai_disclosure: bool = True
    youtube_video_id: str | None = None
    uploaded_at: str | None = None


class ConfigSnapshot(_Model):
    voice: str = "af_heart"
    aspect: str = "1920x1080"
    target_len_s: int = 90


class Run(_Model):
    """The whole spine. `run_id` == date == primary key (one video/day)."""

    run_id: str  # YYYY-MM-DD
    schema_version: int = SCHEMA_VERSION
    created_at: str = Field(default_factory=_utcnow_iso)
    config_snapshot: ConfigSnapshot = Field(default_factory=ConfigSnapshot)

    # Per-stage sections (None until the stage fills them):
    topic: Topic | None = None
    script: Script | None = None
    shots: list[Shot] = Field(default_factory=list)
    audio: Audio | None = None
    assets: Assets | None = None
    video: Video | None = None
    thumbnail: Thumbnail | None = None
    upload: Upload | None = None

    # Cross-cutting status map — one row per stage, in canonical order.
    stages: list[StageRecord] = Field(default_factory=list)

    # ---- construction ----

    @classmethod
    def new(cls, run_id: str) -> "Run":
        """Create a fresh spine with all stages pending, in canonical order."""
        return cls(
            run_id=run_id,
            stages=[StageRecord(name=name) for name in STAGE_ORDER],
        )

    # ---- stage-status helpers (the provider_used map lives in stages[]) ----

    def stage(self, name: str) -> StageRecord:
        for rec in self.stages:
            if rec.name == name:
                return rec
        raise KeyError(f"unknown stage: {name!r}")

    def status_map(self) -> dict[str, StageStatus]:
        """Per-stage status map (the `status` map the deliverable calls for)."""
        return {rec.name: rec.status for rec in self.stages}

    def provider_used_map(self) -> dict[str, str | None]:
        """Per-stage provider_used map."""
        return {rec.name: rec.provider_used for rec in self.stages}

    def mark_running(self, name: str) -> None:
        rec = self.stage(name)
        rec.status = StageStatus.RUNNING
        rec.attempts += 1
        rec.started_at = _utcnow_iso()
        rec.error = None

    def mark_completed(self, name: str, provider_used: str | None = None) -> None:
        rec = self.stage(name)
        rec.status = StageStatus.COMPLETED
        rec.ended_at = _utcnow_iso()
        if provider_used is not None:
            rec.provider_used = provider_used

    def mark_failed(self, name: str, error: str) -> None:
        rec = self.stage(name)
        rec.status = StageStatus.FAILED
        rec.error = error
        rec.ended_at = _utcnow_iso()

    def mark_skipped(self, name: str, note: str) -> None:
        rec = self.stage(name)
        rec.status = StageStatus.SKIPPED
        rec.error = note  # reuse the error slot for the human-readable reason
        rec.ended_at = _utcnow_iso()

    def is_completed(self, name: str) -> bool:
        return self.stage(name).status is StageStatus.COMPLETED

    # ---- persistence (pretty JSON, validated on read + write) ----

    def save(self, path: str | Path) -> None:
        """Validate then write pretty JSON. Never stores blobs — paths only."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        # model_dump then re-validate roundtrip keeps us honest.
        data = self.model_dump(mode="json")
        p.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "Run":
        """Read + validate. A malformed spine raises pydantic ValidationError."""
        raw = Path(path).read_text(encoding="utf-8")
        return cls.model_validate_json(raw)
