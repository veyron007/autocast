"""Stage: upload — YouTube Data API v3 videos.insert (PRIVATE) + thumbnails.set.

Reads `spine.topic`, `spine.script`, `spine.video`, `spine.thumbnail`; writes
`spine.upload`. Upload metadata is DERIVED from the script/topic, not re-invented,
so nothing drifts from the shot list.

In dry-run we DO NOT upload — we log the derived title/description/tags and set a
fake video_id. Privacy is ALWAYS "private" until the compliance audit passes.

Auth: refresh token -> access token each run (util/youtube_auth). See the README
human-dependency gate for the Google Cloud + OAuth + audit steps.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from autocast.config import Config
from autocast.spine import Run, StageSkipped, Upload
from autocast.util.youtube_auth import get_access_token

log = logging.getLogger("autocast.stages.upload")

STAGE = "upload"

_DISCLAIMER = (
    "\n\nThis video contains AI-generated visuals and narration.\n"
    "Music & stock credits are listed in the license manifest for this run."
)


def _derive_description(spine: Run) -> str:
    intro = spine.script.full_text[:280] if spine.script else ""
    return intro + _DISCLAIMER


def _derive_tags(spine: Run) -> list[str]:
    title = spine.topic.title if spine.topic else ""
    # Cheap keyword extraction; TODO(real): let the LLM emit tags in direction.
    stop = {"the", "was", "why", "how", "and", "that", "still", "some", "a", "of", "in"}
    words = [w.strip(".,").lower() for w in title.split()]
    return [w for w in words if w and w not in stop][:8]


def _has_yt_creds(cfg: Config) -> bool:
    return bool(cfg.yt_client_id and cfg.yt_client_secret and cfg.yt_refresh_token)


def run(spine: Run, cfg: Config, *, dry_run: bool = False) -> Run:
    if spine.topic is None or spine.video is None:
        raise ValueError("upload stage: needs spine.topic and spine.video")

    title = spine.topic.title
    description = _derive_description(spine)
    tags = _derive_tags(spine)

    # Metadata is DERIVED and recorded regardless of whether we actually upload,
    # so the spine + manifest always show what WOULD be published.
    spine.upload = Upload(
        title=title,
        description=description,
        tags=tags,
        privacy="private",  # NEVER public until the compliance audit clears
        ai_disclosure=True,
        youtube_video_id=None,
        uploaded_at=None,
    )

    if dry_run:
        get_access_token(cfg.yt_client_id, cfg.yt_client_secret, cfg.yt_refresh_token, dry_run=True)
        log.info("upload[DRY-RUN]: would insert video (privacy=private)")
        log.info("  title       = %s", title)
        log.info("  description = %s", description.replace("\n", " ")[:120] + "...")
        log.info("  tags        = %s", tags)
        log.info("  thumbnail   = %s", spine.thumbnail.path if spine.thumbnail else None)
        spine.upload.youtube_video_id = "DRYRUN_VIDEO_ID"
        spine.upload.uploaded_at = datetime.now(timezone.utc).isoformat()
        spine.stage(STAGE).provider_used = "dry-stub"
        log.info("upload: recorded video_id=%s (privacy=private)", spine.upload.youtube_video_id)
        return spine

    # Real render, but publishing is human-gated (OAuth + compliance audit). Without
    # credentials we deliberately SKIP publishing — the video is fully rendered and
    # sits locally, ready to upload as private once the gate clears.
    if not _has_yt_creds(cfg):
        raise StageSkipped(
            "no YouTube credentials (YT_CLIENT_ID/SECRET/REFRESH_TOKEN) — video "
            "rendered locally, publishing skipped. See README human-dependency gate."
        )

    # TODO(real): implement videos.insert (privacyStatus=private) + thumbnails.set +
    #   the synthetic-media disclosure. Until then, even WITH creds we skip rather
    #   than half-upload. This is the Phase-2 gate.
    get_access_token(cfg.yt_client_id, cfg.yt_client_secret, cfg.yt_refresh_token, dry_run=False)
    raise StageSkipped(
        "real YouTube videos.insert not implemented yet (Phase 2). Video rendered; "
        "publishing skipped."
    )
    return spine
