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
    Seed(
        title="The Library of Alexandria Didn't Burn in a Day",
        shots=(
            {
                "narration": "You have heard that the great Library of Alexandria burned in a single catastrophic night, taking all the world's knowledge with it. The truth is stranger, and far quieter.",
                "image_prompt": "grand ancient library of alexandria interior, towering shelves of papyrus scrolls, warm torchlight, marble columns, cinematic wide shot",
                "motion": "zoom_in",
                "caption": "The great fire myth",
                "duration_s": 7.0,
            },
            {
                "narration": "There was no single fire. Caesar's troops scorched part of it once, but the real decline was slow: decades of lost funding, expelled scholars, and fragile scrolls crumbling to dust in the damp sea air.",
                "image_prompt": "decaying papyrus scrolls crumbling on dusty neglected shelves in dim shafts of light, melancholic, high detail, cinematic",
                "motion": "pan_right",
                "caption": "A slow decline",
                "duration_s": 7.0,
            },
            {
                "narration": "Every scroll had to be copied by hand just to survive. When the scholars stopped coming and the copyists laid down their pens, the words did not burn. They were simply never recopied, and faded away.",
                "image_prompt": "close up of an ancient scribe's hands copying greek text onto papyrus with a reed pen by candlelight, warm, intimate, cinematic",
                "motion": "zoom_in",
                "caption": "Copied by hand, or lost",
                "duration_s": 6.5,
            },
            {
                "narration": "We mourn a single dramatic blaze, but knowledge more often dies of neglect. The lesson of Alexandria is not to fear the fire. It is to fear forgetting to care.",
                "image_prompt": "a single candle burning low beside a fading scroll in surrounding darkness, symbolic, moody, cinematic still life",
                "motion": "zoom_out",
                "caption": "Neglect, not flame",
                "duration_s": 6.5,
            },
        ),
    ),
    Seed(
        title="Why Honey Is the Only Food That Never Spoils",
        shots=(
            {
                "narration": "Archaeologists digging in an Egyptian tomb once found a sealed jar of honey over three thousand years old. They tasted it, and it was still perfectly good to eat. How?",
                "image_prompt": "ancient sealed ceramic jar of golden honey inside an egyptian tomb lit by a single torch, dramatic, high detail, cinematic",
                "motion": "zoom_in",
                "caption": "3,000 years old, still edible",
                "duration_s": 6.5,
            },
            {
                "narration": "Honey is a near-perfect trap for the microbes that make food rot. It holds almost no free water, so bacteria that need moisture simply dry out and die before they can ever take hold.",
                "image_prompt": "extreme macro of thick golden honey slowly dripping in a glistening ribbon, amber light, appetizing, cinematic detail",
                "motion": "pan_right",
                "caption": "No water, no rot",
                "duration_s": 6.5,
            },
            {
                "narration": "The bees add the final touch. An enzyme from their bodies releases tiny amounts of hydrogen peroxide, and the honey itself is acidic. Together they form a natural preservative almost nothing survives.",
                "image_prompt": "honeybees clustered on a golden dripping honeycomb in warm sunlight, richly detailed, cinematic wildlife macro",
                "motion": "zoom_in",
                "caption": "The bees' secret",
                "duration_s": 7.0,
            },
            {
                "narration": "So long as it stays sealed and dry, a jar of honey can outlast whole empires. The next spoonful you eat may well still be sweet a thousand years from now.",
                "image_prompt": "a spoon lifting glistening honey from an open jar in golden morning light, warm, inviting, cinematic",
                "motion": "zoom_out",
                "caption": "Sweeter than empires",
                "duration_s": 6.5,
            },
        ),
    ),
    Seed(
        title="The 2,000-Year-Old Computer Found in a Shipwreck",
        shots=(
            {
                "narration": "In 1901, sponge divers off a Greek island hauled a lump of corroded bronze up from an ancient wreck. It would take a full century to realize they had found a two-thousand-year-old computer.",
                "image_prompt": "corroded bronze gear fragment encrusted with sea deposits on a dark surface, mysterious, museum lighting, cinematic close up",
                "motion": "zoom_in",
                "caption": "A lump of bronze",
                "duration_s": 7.0,
            },
            {
                "narration": "Hidden inside were dozens of interlocking bronze gears, cut with astonishing precision. It was a hand-cranked machine, built by ancient Greeks to model the motion of the heavens themselves.",
                "image_prompt": "intricate interlocking ancient bronze gears in extreme detail, glowing golden light, mechanical, cinematic macro",
                "motion": "pan_left",
                "caption": "Dozens of gears",
                "duration_s": 6.5,
            },
            {
                "narration": "Turn its crank and it tracked the sun and moon, predicted their phases, even forecast eclipses years in advance. Nothing this intricate would appear again anywhere for over a thousand years.",
                "image_prompt": "reconstruction of the antikythera mechanism with rotating dials and pointers, glowing bronze, dramatic, cinematic",
                "motion": "zoom_in",
                "caption": "It predicted eclipses",
                "duration_s": 6.5,
            },
            {
                "narration": "We assume our ancestors were simpler than us. But someone, twenty centuries ago, held the whole sky inside a box of gears. And then that knowledge vanished into the sea.",
                "image_prompt": "an ancient bronze mechanism sinking slowly through deep blue seawater pierced by shafts of light, haunting, cinematic",
                "motion": "zoom_out",
                "caption": "The sky in a box",
                "duration_s": 7.0,
            },
        ),
    ),
    Seed(
        title="The Explosion That Flattened a Siberian Forest",
        shots=(
            {
                "narration": "One morning in 1908, over a remote stretch of Siberia, the sky split open with a blast a thousand times stronger than an atomic bomb. And almost no one was there to see it.",
                "image_prompt": "vast siberian taiga forest at dawn with a blinding fireball streaking across the sky, dramatic, atmospheric, cinematic wide shot",
                "motion": "zoom_in",
                "caption": "1908, Siberia",
                "duration_s": 7.0,
            },
            {
                "narration": "It leveled eighty million trees across an area larger than a city, snapping them flat like matchsticks, all pointing away from one empty center. And yet there was no crater at all.",
                "image_prompt": "endless field of fallen trees lying flat in the same direction across a barren siberian landscape, grey light, eerie, cinematic aerial",
                "motion": "pan_right",
                "caption": "80 million trees, no crater",
                "duration_s": 7.0,
            },
            {
                "narration": "The cause was almost certainly a comet or asteroid that exploded miles above the ground, unleashing all of its energy as a searing blast of air before it ever touched the earth.",
                "image_prompt": "a brilliant meteor exploding in a blinding airburst high above a dark forest, dramatic sky, luminous, cinematic",
                "motion": "zoom_in",
                "caption": "An airburst",
                "duration_s": 6.5,
            },
            {
                "narration": "Had it arrived just a few hours later, it might have erased a major city instead of empty forest. Tunguska is a quiet reminder that the sky is not always as still as it seems.",
                "image_prompt": "peaceful starry night sky over a silhouetted forest, calm but faintly ominous, deep blue, cinematic",
                "motion": "zoom_out",
                "caption": "The sky isn't still",
                "duration_s": 6.5,
            },
        ),
    ),
    Seed(
        title="The Whale Whose Song No Other Whale Can Hear",
        shots=(
            {
                "narration": "Somewhere in the Pacific swims a whale that has been calling out for decades, in a voice no other whale seems able to answer. Scientists came to call it the loneliest whale in the world.",
                "image_prompt": "a lone whale silhouette in vast deep blue ocean with sunbeams streaming from above, solitary, atmospheric, cinematic wide shot",
                "motion": "zoom_in",
                "caption": "The loneliest whale",
                "duration_s": 7.0,
            },
            {
                "narration": "Most whales sing at a low, resonant pitch. But this one calls at fifty-two hertz, far higher than its own kind ever uses, like a voice speaking a language nobody else seems to know.",
                "image_prompt": "abstract underwater sound waves rippling through dark blue water around a distant whale, glowing, ethereal, cinematic",
                "motion": "pan_left",
                "caption": "A voice at 52 hertz",
                "duration_s": 7.0,
            },
            {
                "narration": "For years, sonar arrays tracked its song across the ocean, always alone, never joined. No one knows if it is deaf, a rare hybrid, or simply one of a kind. It has never once been seen.",
                "image_prompt": "a glowing green sonar screen showing a single moving blip in a dark control room, technical, moody, cinematic",
                "motion": "zoom_in",
                "caption": "Tracked but never seen",
                "duration_s": 6.5,
            },
            {
                "narration": "Maybe it truly is alone, or maybe others hear it and we simply cannot. Either way, somewhere out there tonight, a single voice is still singing into the dark.",
                "image_prompt": "moonlit ocean surface stretching to the horizon at night with a faint ripple below, haunting, serene, cinematic",
                "motion": "zoom_out",
                "caption": "Still singing",
                "duration_s": 6.5,
            },
        ),
    ),
    Seed(
        title="The Ancient Seeds That Grew After 2,000 Years",
        shots=(
            {
                "narration": "High on a desert cliff in Israel, archaeologists sifting through an ancient fortress found a handful of date palm seeds, buried and forgotten for two thousand years. By every rule of biology, they should have been long dead.",
                "image_prompt": "sun-scorched desert fortress ruins on a high cliff above a pale valley, golden light, archaeological dig, cinematic wide shot",
                "motion": "zoom_in",
                "caption": "Seeds from a lost fortress",
                "duration_s": 7.0,
            },
            {
                "narration": "Decades later, a researcher decided to try the impossible and simply planted them. She soaked the shriveled seeds, gave them water and warmth, and waited for something everyone expected would never come.",
                "image_prompt": "extreme close up of three ancient shriveled date seeds resting in dark soil under warm light, high detail, hopeful, cinematic macro",
                "motion": "pan_right",
                "caption": "Planting the impossible",
                "duration_s": 6.5,
            },
            {
                "narration": "Then, against two thousand years of odds, a single green shoot pushed up through the soil. The ancient seed had awakened, and they named the little palm Methuselah, after the oldest man in legend.",
                "image_prompt": "a tiny green palm sprout emerging from dark earth in a shaft of warm sunlight, tender new leaves, luminous, cinematic close up",
                "motion": "zoom_in",
                "caption": "It woke up",
                "duration_s": 7.0,
            },
            {
                "narration": "Today that palm stands tall, grown from a seed older than most of recorded history. It is living proof that life can wait, patient and dormant, for millennia, ready to begin again.",
                "image_prompt": "a tall healthy date palm standing alone against a vast desert sky at golden hour, majestic, warm, cinematic wide shot",
                "motion": "zoom_out",
                "caption": "Life can wait",
                "duration_s": 6.5,
            },
        ),
    ),
    Seed(
        title="The Largest Living Thing Is a Single Fungus",
        shots=(
            {
                "narration": "In a quiet forest in Oregon, trees were dying in slow, spreading rings, and no one knew why. When scientists dug beneath the soil to investigate, they uncovered the largest living organism on Earth.",
                "image_prompt": "dense oregon pine forest with patches of dying trees seen from above, misty, muted green, eerie, cinematic aerial",
                "motion": "zoom_in",
                "caption": "Trees dying in rings",
                "duration_s": 7.0,
            },
            {
                "narration": "It was a single honey fungus, hidden almost entirely underground. A vast web of pale threads laced through the soil, all part of one connected organism spreading silently between the roots of the trees.",
                "image_prompt": "macro of pale white fungal threads threading through dark forest soil and tree roots, intricate, glistening, cinematic detail",
                "motion": "pan_left",
                "caption": "One hidden organism",
                "duration_s": 6.5,
            },
            {
                "narration": "This one fungus sprawls across nearly ten square kilometers, weighs as much as thousands of cars, and may be over two thousand years old. Almost all of it stays invisible, deep beneath the forest floor.",
                "image_prompt": "clusters of golden honey mushrooms growing at the base of a mossy tree trunk in dim forest light, richly detailed, cinematic",
                "motion": "zoom_in",
                "caption": "Bigger than a city",
                "duration_s": 7.0,
            },
            {
                "narration": "We picture giants as whales or towering trees. But the true colossus of the living world is a quiet, patient fungus, hiding under a forest that has no idea it is standing on a single vast creature.",
                "image_prompt": "sunlight breaking through a tall silent forest canopy onto the shadowed floor below, atmospheric, expansive, cinematic",
                "motion": "zoom_out",
                "caption": "The true giant",
                "duration_s": 6.5,
            },
        ),
    ),
    Seed(
        title="The Volcano That Stole a Summer",
        shots=(
            {
                "narration": "In 1815, a mountain in Indonesia named Tambora erupted with the most violent blast in recorded history. It hurled so much ash into the sky that the effects would soon be felt on the far side of the world.",
                "image_prompt": "colossal volcanic eruption at dusk hurling ash and fire into a darkening sky over a tropical island, apocalyptic, cinematic wide shot",
                "motion": "zoom_in",
                "caption": "1815, Mount Tambora",
                "duration_s": 7.0,
            },
            {
                "narration": "A veil of fine ash and gas spread high through the atmosphere, circling the globe and dimming the sun itself. Slowly, quietly, it began to cool the entire planet by a fraction of a degree.",
                "image_prompt": "hazy pale sun struggling through a thick veil of high atmospheric ash, muted grey sky, ominous, cinematic",
                "motion": "pan_right",
                "caption": "A veil over the sun",
                "duration_s": 6.5,
            },
            {
                "narration": "The next year, 1816, became the year without a summer. Snow fell in June across New England, frost killed crops in Europe, harvests failed, and hunger spread through countries that never felt the eruption at all.",
                "image_prompt": "a failing summer crop field dusted with unseasonable frost under a cold grey sky, bleak, desolate, cinematic",
                "motion": "zoom_in",
                "caption": "A summer that never came",
                "duration_s": 7.0,
            },
            {
                "narration": "Trapped indoors by the endless gloom, a young writer named Mary Shelley began a ghost story that became Frankenstein. A single volcano had chilled the world, starved nations, and quietly reshaped its art.",
                "image_prompt": "candlelit writing desk with an open notebook and quill by a rain-streaked window at night, moody, intimate, cinematic",
                "motion": "zoom_out",
                "caption": "One volcano, a new world",
                "duration_s": 6.5,
            },
        ),
    ),
    Seed(
        title="The Metal That Remembers Its Shape",
        shots=(
            {
                "narration": "Bend this metal wire, twist it, crumple it into a knot. Then warm it gently, and it will untangle itself and spring back to its exact original shape, as if it remembered where it belonged.",
                "image_prompt": "a thin silver metal wire bent into a tangle resting on a clean dark surface under soft studio light, high detail, cinematic macro",
                "motion": "zoom_in",
                "caption": "Metal that remembers",
                "duration_s": 7.0,
            },
            {
                "narration": "The secret is an alloy of nickel and titanium called nitinol. Deep in its crystal structure the atoms hold two arrangements, and a little heat snaps them back from the bent shape to the one they were trained to keep.",
                "image_prompt": "abstract glowing crystalline lattice of atoms rearranging, blue and silver, scientific visualization, luminous, cinematic",
                "motion": "pan_left",
                "caption": "A trained crystal",
                "duration_s": 6.5,
            },
            {
                "narration": "This strange memory does real work. Nitinol springs open blocked arteries from inside the body, flexes eyeglass frames back into shape, and even folds up satellites that unfurl once they reach the cold of space.",
                "image_prompt": "close up of a delicate mesh medical stent expanding, precise metallic filaments, clinical blue light, cinematic detail",
                "motion": "zoom_in",
                "caption": "Memory that saves lives",
                "duration_s": 7.0,
            },
            {
                "narration": "We think of memory as something only minds possess. But locked inside the right metal is a kind of memory too, a shape it will always find its way back to, no matter how far you bend it.",
                "image_prompt": "a straightened silver wire glinting on a dark reflective surface with soft rim light, elegant, minimal, cinematic",
                "motion": "zoom_out",
                "caption": "Shape it never forgets",
                "duration_s": 6.5,
            },
        ),
    ),
    Seed(
        title="The Birds That Sleep While They Fly",
        shots=(
            {
                "narration": "Some seabirds stay in the air for weeks, even months, without ever touching down. Which raises an impossible question: if they never land, then when on earth do they ever sleep?",
                "image_prompt": "a lone seabird gliding high over an endless open ocean at golden hour, tiny against vast sky, serene, cinematic wide shot",
                "motion": "zoom_in",
                "caption": "Weeks without landing",
                "duration_s": 7.0,
            },
            {
                "narration": "Scientists strapped tiny brain monitors to great frigatebirds and sent them out over the sea. The recordings revealed something remarkable: the birds really do sleep, in the air, while still soaring on the wind.",
                "image_prompt": "great frigatebird with a wide black wingspan soaring against a dramatic cloud-streaked sky, majestic, cinematic",
                "motion": "pan_right",
                "caption": "Sleeping on the wing",
                "duration_s": 6.5,
            },
            {
                "narration": "They sleep in tiny bursts of just seconds, often resting only half the brain at a time while the other half stays alert. Sometimes, riding a rising current, they even shut down both halves at once.",
                "image_prompt": "close up of a frigatebird's eye and head in soft focus against a blurred bright sky, intimate, detailed, cinematic",
                "motion": "zoom_in",
                "caption": "Half a brain awake",
                "duration_s": 7.0,
            },
            {
                "narration": "In a whole month at sea, they sleep barely forty minutes a day, a fraction of what they take on land. High above the waves, these birds have quietly mastered a trick that still leaves scientists amazed.",
                "image_prompt": "silhouetted seabird drifting across a vast twilight sky above a calm ocean, peaceful, expansive, cinematic",
                "motion": "zoom_out",
                "caption": "Masters of the sky",
                "duration_s": 6.5,
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
