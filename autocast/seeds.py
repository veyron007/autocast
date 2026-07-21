"""Bespoke keyless content templates — the evergreen "seed" videos.

Without an LLM key every content stage falls back to a template. Before Cycle 9
that template was a SINGLE generic script plus a SINGLE hardcoded shot list, so
every keyless daily video was byte-for-byte identical. This module gives each
evergreen seed topic its OWN hand-authored narration and shot list, and the
topic stage rotates through them by date — so even a fully keyless channel ships
a different, coherent video every day.

Contract (mirrors the LLM path so downstream stages don't care which produced the
content):
- A ``Seed.script`` is exactly the concatenation of its shot narrations, so the
  "narration fields, in order, reconstruct the whole script" invariant the
  direction prompt demands holds for templates too.
- Each shot dict carries the same keys the direction stage coerces out of the
  LLM: ``narration``, ``image_prompt``, ``motion``, ``caption``, ``duration_s``.
  (``duration_s`` is provisional — the tts stage overwrites it with the measured
  audio length.)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import TypedDict

# Label recorded on a stage when it used a bespoke per-topic seed template
# (distinct from the generic ``template-fallback`` used for unknown topics).
TEMPLATE_SEED = "template-seed"


class ShotDict(TypedDict):
    """The shape the direction stage coerces every shot into. Pinning it here
    catches key typos statically instead of at render time."""

    narration: str
    image_prompt: str
    motion: str
    caption: str
    duration_s: float


@dataclass(frozen=True)
class Seed:
    """One evergreen topic with a hand-authored narration + shot list.

    The ``shots`` dicts are shared, read-only registry data — copy before
    mutating (the direction stage does; see ``_template_shots``)."""

    title: str
    shots: tuple[ShotDict, ...]

    @property
    def script(self) -> str:
        """The full narration = the shot narrations joined, in order."""
        return " ".join(shot["narration"] for shot in self.shots)


SEEDS: tuple[Seed, ...] = (
    Seed(
        title="Why the Roman Concrete Recipe Was Lost",
        shots=(
            {
                "narration": "Along the coast of Italy, Roman harbor walls have stood in crashing seawater for two thousand years. Modern concrete piers poured beside them are already crumbling after fifty. How?",
                "image_prompt": "ancient roman harbor breakwater in crashing turquoise sea at golden hour, massive weathered stone, cinematic wide shot, dramatic light",
                "motion": "zoom_in",
                "caption": "2,000 years in the sea",
                "duration_s": 6.5,
            },
            {
                "narration": "The answer was hidden in the mix. Roman builders folded in chunks of quicklime and volcanic ash, then blended it scorching hot, leaving tiny white reservoirs of self-repair locked inside the stone.",
                "image_prompt": "extreme close up of an ancient roman concrete cross-section showing bright white lime clasts, textured, high detail, museum lighting",
                "motion": "pan_right",
                "caption": "A self-healing mix",
                "duration_s": 6.5,
            },
            {
                "narration": "When a crack forms and water seeps in, that lime dissolves and recrystallizes, sealing the gap before it can spread. The concrete literally heals itself. But the recipe was never written down.",
                "image_prompt": "macro view of a hairline crack in pale stone slowly filling with white crystals, scientific, softly glowing, cinematic",
                "motion": "zoom_in",
                "caption": "Cracks that seal themselves",
                "duration_s": 7.0,
            },
            {
                "narration": "As Rome fell, the knowledge passed away with its engineers, and for over a thousand years it was simply lost. Only now, in modern labs, are we relearning what the Romans somehow already knew.",
                "image_prompt": "modern materials science laboratory with a glowing concrete sample under blue light, futuristic, clean, cinematic",
                "motion": "zoom_out",
                "caption": "Rediscovered at last",
                "duration_s": 7.0,
            },
        ),
    ),
    Seed(
        title="The Deep-Sea Creatures That Glow in the Dark",
        shots=(
            {
                "narration": "Descend past a thousand meters and the sunlight vanishes completely. Yet this crushing darkness is the most lit-up place on Earth, where nine out of ten animals make their own light.",
                "image_prompt": "deep ocean midnight zone, pitch black water pierced by tiny points of blue bioluminescence, eerie, atmospheric, cinematic",
                "motion": "zoom_in",
                "caption": "The midnight zone",
                "duration_s": 6.5,
            },
            {
                "narration": "It is a chemical trick called bioluminescence. A molecule named luciferin reacts with oxygen, and the energy escapes not as heat, but as cold living light, glowing blue-green through the deep.",
                "image_prompt": "macro shot of a translucent jellyfish pulsing electric blue in dark water, bioluminescent, luminous, cinematic detail",
                "motion": "pan_left",
                "caption": "Living light",
                "duration_s": 6.5,
            },
            {
                "narration": "Every glow has a purpose. Anglerfish dangle a lure to trap prey. Others flash to find a mate, or erase their own shadow from below in a vanishing act called counter-illumination.",
                "image_prompt": "deep sea anglerfish with a single glowing lure hovering in black water, menacing, highly detailed, cinematic wildlife shot",
                "motion": "zoom_in",
                "caption": "A reason to glow",
                "duration_s": 7.0,
            },
            {
                "narration": "By borrowing these very molecules, scientists now light up living cells, track diseases, and watch tumors grow. The deep sea's quiet glow is quietly rewriting modern medicine.",
                "image_prompt": "microscope image of living cells glowing green against a black field, scientific, luminous, cinematic",
                "motion": "zoom_out",
                "caption": "From abyss to lab",
                "duration_s": 6.5,
            },
        ),
    ),
    Seed(
        title="How Medieval Cities Handled Their Waste",
        shots=(
            {
                "narration": "Picture a medieval city: fifty thousand people packed inside stone walls, and not a single sewer. The most pressing question wasn't war or plague. It was simply, where does it all go?",
                "image_prompt": "crowded medieval european city street at dusk, timber houses leaning overhead, muddy lane, atmospheric haze, cinematic",
                "motion": "pan_right",
                "caption": "50,000 people, no sewers",
                "duration_s": 7.0,
            },
            {
                "narration": "The answer was a grim economy. Households used cesspits dug beneath their homes. When they filled, the night-soil men, the gong farmers, emptied them by hand after dark and hauled the waste beyond the walls.",
                "image_prompt": "lantern-lit medieval alley at night, a cloaked figure with a cart and shovel, moody, candlelight, cinematic",
                "motion": "zoom_in",
                "caption": "The gong farmers",
                "duration_s": 7.0,
            },
            {
                "narration": "It was dangerous, low-paid, and constant. When the system failed, waste ran into the same rivers people drank from, and the diseases that followed could empty a city faster than any siege.",
                "image_prompt": "murky medieval river running past stone city walls, refuse floating, grey overcast light, grim, cinematic",
                "motion": "pan_left",
                "caption": "When it failed",
                "duration_s": 6.5,
            },
            {
                "narration": "Every flush you take today traces back to these grim lessons. Modern sanitation was never a sudden invention. It was built, painfully, on centuries of getting it wrong.",
                "image_prompt": "modern water treatment plant with geometric tanks at blue hour, aerial view, crisp, cinematic",
                "motion": "zoom_out",
                "caption": "The cost of clean",
                "duration_s": 6.5,
            },
        ),
    ),
    Seed(
        title="The Forgotten Language That Vanished in a Generation",
        shots=(
            {
                "narration": "One morning, in a quiet village, the last person who spoke a language fluently passed away. And with a single breath, an entire way of seeing the world went silent forever.",
                "image_prompt": "elderly person's silhouette at a window in soft morning light, empty quiet room, muted tones, melancholic, cinematic",
                "motion": "zoom_in",
                "caption": "The last speaker",
                "duration_s": 7.0,
            },
            {
                "narration": "Languages rarely die by accident. Often a policy forbids them in schools, children are shamed for speaking them, and within a single generation the chain from parent to child quietly snaps.",
                "image_prompt": "old empty schoolroom with wooden desks and a faded chalkboard, dust drifting in shafts of light, nostalgic, cinematic",
                "motion": "pan_right",
                "caption": "How a language dies",
                "duration_s": 6.5,
            },
            {
                "narration": "What vanishes is far more than words. Untranslatable ideas, songs, oral maps of rivers and stars, and generations of knowledge about plants and seasons, all encoded in sounds no one can now pronounce.",
                "image_prompt": "weathered hand-drawn map and old notebooks filled with unfamiliar script on a wooden table, warm light, cinematic still life",
                "motion": "zoom_in",
                "caption": "More than words",
                "duration_s": 7.0,
            },
            {
                "narration": "But some stories don't end there. With old recordings, new apps, and stubborn young speakers, dying languages are being coaxed back to life, one remembered word at a time.",
                "image_prompt": "young person wearing headphones smiling at a laptop showing audio waveforms, warm hopeful light, cinematic",
                "motion": "zoom_out",
                "caption": "Brought back to life",
                "duration_s": 6.5,
            },
        ),
    ),
    Seed(
        title="Why Some Ancient Bridges Still Stand Today",
        shots=(
            {
                "narration": "In Spain, a stone bridge built by Roman engineers still carries traffic today, nearly two thousand years later. Meanwhile, modern bridges are condemned after just forty. What did they know?",
                "image_prompt": "ancient roman stone arch bridge spanning a river in golden light, massive weathered stone, cinematic wide shot",
                "motion": "pan_left",
                "caption": "2,000 years and counting",
                "duration_s": 7.0,
            },
            {
                "narration": "The secret is the shape. The arch turns the crushing weight of the bridge into pure compression, pushing outward along the stone. And stone is extraordinarily strong when squeezed, rather than stretched.",
                "image_prompt": "close up of a stone arch keystone seen from below, geometric, dramatic shadows, architectural, cinematic",
                "motion": "zoom_in",
                "caption": "The power of the arch",
                "duration_s": 6.5,
            },
            {
                "narration": "They also built with a heavy margin for error. Massive stones, deep foundations, and no reliance on mortar meant that even as pieces weathered, the structure simply settled and held.",
                "image_prompt": "thick weathered stone bridge piers rising from a calm river, moss and age, overcast light, cinematic detail",
                "motion": "pan_right",
                "caption": "Built to overbuild",
                "duration_s": 6.5,
            },
            {
                "narration": "Modern engineering optimizes for cost and speed, shaving away every gram of material. The Romans optimized for time. Two thousand years later, it's clear which of them was really thinking ahead.",
                "image_prompt": "split composition of an ancient roman bridge beside a modern concrete highway overpass, contrast, dramatic sky, cinematic",
                "motion": "zoom_out",
                "caption": "Who thought ahead?",
                "duration_s": 7.0,
            },
        ),
    ),
)

# Titles in seed order — the topic stage's evergreen seed list.
SEED_TITLES: tuple[str, ...] = tuple(seed.title for seed in SEEDS)

_SEEDS_BY_TITLE: dict[str, Seed] = {seed.title: seed for seed in SEEDS}


def generic_shots(title: str) -> list[ShotDict]:
    """Topic-neutral last-resort shot list for a title with no bespoke seed
    (e.g. a human-queued custom topic on a keyless run). The first beat names the
    topic so the video still references it. Returns a fresh list each call, so
    callers may use it directly. ``generic_script`` joins the SAME narrations, so
    the script<->shots coherence invariant holds for the generic path too."""
    subject = title.strip() or "This story"
    return [
        {
            "narration": f"{subject}. Some stories hide in plain sight, waiting for someone to finally look a little closer.",
            "image_prompt": "atmospheric wide establishing shot at soft golden light, film grain, cinematic, moody",
            "motion": "zoom_in",
            "caption": "A closer look",
            "duration_s": 5.5,
        },
        {
            "narration": "Trace it back to the very beginning, and a familiar thing starts to look strange and new.",
            "image_prompt": "extreme close up of an aged, textured surface, moody, high detail, cinematic",
            "motion": "pan_right",
            "caption": "Back to the start",
            "duration_s": 5.5,
        },
        {
            "narration": "By the end, you will never quite see it the same way again.",
            "image_prompt": "slow reveal of a wide landscape at golden hour, hopeful, cinematic, expansive",
            "motion": "zoom_out",
            "caption": "See it anew",
            "duration_s": 5.5,
        },
    ]


def generic_script(title: str) -> str:
    """Generic narration for a non-seed title = its generic shot narrations
    joined, so it stays coherent with the shots the direction stage builds."""
    return " ".join(shot["narration"] for shot in generic_shots(title))


def seed_for_title(title: str) -> Seed | None:
    """Return the bespoke seed for an exact title, or None if unknown."""
    return _SEEDS_BY_TITLE.get(title)


def pick_seed_index(run_id: str, n: int) -> int:
    """Deterministic daily rotation index in [0, n). Keyed off the run date so a
    keyless channel ships a different seed each day; falls back to 0 for a
    non-date run_id."""
    if n <= 0:
        return 0
    try:
        return date.fromisoformat(run_id).toordinal() % n
    except ValueError:
        return 0


def rotated_seed_titles(run_id: str) -> list[str]:
    """Seed titles rotated so today's pick is first — every downstream selector
    that takes ``candidates[0]`` then lands on the day's rotated seed."""
    titles = list(SEED_TITLES)
    idx = pick_seed_index(run_id, len(titles))
    return titles[idx:] + titles[:idx]
