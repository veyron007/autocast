"""Stage: topic — pick today's video subject.

Selection priority (highest first):
1. The human-editable topic QUEUE (`queue/topics.json`) — the one-lever control
   the future UI writes to. If it has entries, today's topic is dequeued from it.
2. Google Trends RSS (per-geo, keyless) — real trending titles, faceless-filtered.
3. A static evergreen seed list — the always-available offline / dry-run fallback.

Writes `spine.topic`. In dry-run we never touch the network.
"""

from __future__ import annotations

import json
import logging
import xml.etree.ElementTree as ET

from autocast.config import Config
from autocast.providers.llm import build_llm_providers, try_llm
from autocast.spine import Run, Topic
from autocast.util.net import get_text

log = logging.getLogger("autocast.stages.topic")

STAGE = "topic"

# Google Trends RSS (US daily). Keyless. TODO(real): make geo configurable via cfg.
_TRENDS_RSS = "https://trends.google.com/trending/rss?geo=US"

# Fallback seed topics for dry-run / offline. Faceless-friendly, evergreen.
_STATIC_TOPICS = [
    "Why the Roman Concrete Recipe Was Lost",
    "The Deep-Sea Creatures That Glow in the Dark",
    "How Medieval Cities Handled Their Waste",
    "The Forgotten Language That Vanished in a Generation",
    "Why Some Ancient Bridges Still Stand Today",
]


def _read_queue(cfg: Config) -> list[str]:
    """Return queued human-picked topics (may be empty). Never raises."""
    path = cfg.queue_path
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        queued = data.get("queued", []) if isinstance(data, dict) else []
        return [str(t).strip() for t in queued if str(t).strip()]
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("topic: could not read queue %s: %s", path, exc)
        return []


def _fetch_trends_titles() -> list[str]:
    """Fetch trending titles from Google Trends RSS. Returns [] on any failure."""
    try:
        xml = get_text(_TRENDS_RSS, timeout=20.0)
        root = ET.fromstring(xml)
        titles = [
            (item.findtext("title") or "").strip()
            for item in root.iter("item")
        ]
        return [t for t in titles if t]
    except Exception as exc:  # noqa: BLE001 - trends is best-effort; seeds cover us
        log.warning("topic: trends RSS fetch failed (%s); falling back to seeds", exc)
        return []


def _select_candidates(cfg: Config, dry_run: bool) -> tuple[list[str], str]:
    """Return (candidate signals, source label) by the selection priority.

    Trending terms are raw search phrases (names, products) — not video topics —
    so we append the evergreen seeds as anchors and let the LLM craft a real title.
    """
    queued = _read_queue(cfg)
    if queued:
        return queued, "human-queue"
    if dry_run:
        return list(_STATIC_TOPICS), "static-seed"
    trends = _fetch_trends_titles()
    if trends:
        return trends + _STATIC_TOPICS, "google-trends-rss"
    return list(_STATIC_TOPICS), "static-seed"


def _craft_prompt(candidates: list[str]) -> str:
    return (
        "You curate a faceless YouTube channel of short cinematic documentaries about "
        "history, science, and mystery.\n"
        "From the trending signals and evergreen ideas below, produce ONE compelling, "
        "specific video title with strong curiosity appeal.\n"
        "Return ONLY the title text — no quotes, no numbering, no explanation, max 70 chars.\n\n"
        "Signals:\n" + "\n".join(f"- {c}" for c in candidates)
    )


def _clean_title(text: str) -> str:
    """Take the first meaningful line, strip quotes/markdown/numbering."""
    for raw in text.splitlines():
        line = raw.strip().strip("\"'").lstrip("#*-0123456789. ").strip().strip("\"'")
        if len(line) >= 8:
            return line[:100]
    return ""


def run(spine: Run, cfg: Config, *, dry_run: bool = False) -> Run:
    candidates, source = _select_candidates(cfg, dry_run)

    providers = build_llm_providers(
        cfg, prompt=_craft_prompt(candidates), kind="topic-rank", dry_run=dry_run
    )
    llm_text, provider = try_llm(providers)

    # Human-queued topics are used verbatim (that's the whole point of the queue).
    if source == "human-queue" or dry_run:
        chosen = candidates[0]
    elif llm_text:
        # LLM crafts a real title from the raw signals (names/products aren't topics).
        chosen = _clean_title(llm_text) or _STATIC_TOPICS[0]
    else:
        # LLM is down: a raw trend term ("visa bulletin") won't cohere with the
        # deterministic template script/shots downstream, but the evergreen seed
        # WILL — the templates are written around it. Degrade to a coherent whole.
        chosen = _STATIC_TOPICS[0]

    spine.topic = Topic(
        title=chosen,
        source=source,
        rank_score=0.80,
        provider=provider,
    )
    spine.stage(STAGE).provider_used = provider
    log.info("topic: chose %r (source=%s) via %s", chosen, source, provider)
    return spine
