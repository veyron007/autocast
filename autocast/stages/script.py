"""Stage: script — topic -> narration text.

Reads `spine.topic`, writes `spine.script`. The LLM call is behind the cascade;
in dry-run we return a deterministic placeholder script so `direction` and `tts`
have real text to flow.
"""

from __future__ import annotations

import logging

from autocast.config import Config
from autocast.providers.llm import build_llm_providers, try_llm
from autocast.seeds import TEMPLATE_SEED, generic_script, seed_for_title
from autocast.spine import Run, Script

log = logging.getLogger("autocast.stages.script")

STAGE = "script"

# Narration length that lands near the target runtime once spoken. Kept as a
# guardrail against a runaway LLM, not a hard truncation.
_MIN_WORDS = 60
_MAX_WORDS = 320


def _script_prompt(title: str, target_len_s: int) -> str:
    return (
        f"Write a {target_len_s}-second YouTube narration script about: {title}\n\n"
        "Rules:\n"
        "- Return ONLY the spoken narration — no headings, no stage directions, no "
        "'[music]' cues, no markdown, no speaker labels.\n"
        "- Hook the viewer in the first sentence.\n"
        "- Conversational, vivid, faceless-documentary tone.\n"
        f"- About {max(1, target_len_s // 4)} short paragraphs; end with a memorable line.\n"
    )


def _clean_script(text: str) -> str:
    """Strip markdown/label noise an LLM sometimes adds around the narration."""
    lines = []
    for raw in text.splitlines():
        # Drop heading marks and markdown emphasis outright — narration is spoken
        # text, so a literal '*' or '#' is always noise, wherever it sits.
        line = raw.strip().lstrip("#").strip().replace("*", "")
        low = line.lower()
        # Drop bracketed production cues entirely ("[music]", "[cut to ...]").
        if low.startswith("["):
            continue
        # Strip a leading speaker/section label ("Narration:", "Script:", "Title:").
        if low.startswith(("title:", "script:", "narration:")):
            line = line.split(":", 1)[-1].strip()
        if line:
            lines.append(line)
    return " ".join(lines).strip()


def run(spine: Run, cfg: Config, *, dry_run: bool = False) -> Run:
    if spine.topic is None:
        raise ValueError("script stage: spine.topic missing (run topic first)")

    title = spine.topic.title
    prompt = _script_prompt(title, cfg.target_len_s)
    providers = build_llm_providers(cfg, prompt=prompt, kind="script", dry_run=dry_run)
    llm_text, provider = try_llm(providers)

    if dry_run or not llm_text:
        # No live LLM: prefer the topic's bespoke seed narration (distinct per
        # topic) over the generic placeholder, so keyless days aren't identical.
        # The generic fallback shares its narration with the direction stage's
        # generic shots, so script<->shots stay coherent for non-seed titles too.
        seed = seed_for_title(title)
        if seed is not None:
            text = seed.script
            provider = TEMPLATE_SEED
        else:
            text = generic_script(title)
    else:
        text = _clean_script(llm_text)
        wc = len(text.split())
        if wc < _MIN_WORDS:
            log.warning("script: LLM output too short (%d words); using template", wc)
            text = generic_script(title)
        elif wc > _MAX_WORDS:
            text = " ".join(text.split()[:_MAX_WORDS])

    spine.script = Script(
        full_text=text,
        word_count=len(text.split()),
        provider=provider,
    )
    spine.stage(STAGE).provider_used = provider
    log.info("script: %d words via %s", spine.script.word_count, provider)
    return spine
