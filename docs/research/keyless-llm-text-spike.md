# Research: Is there a keyless, free, ToS-clean LLM *text* endpoint?

**Date:** 2026-07-21 (AutoCompany Cycle 11)
**Author:** research-thompson + devops-hightower (autonomous)
**Verdict:** **NO-GO.** No keyless, free, ToS-clean text-generation endpoint can
produce real scripts/shot-lists today. Keyless dynamic content is not achievable
without a (human-added) free API key. This closes the long-standing open question.

---

## Why this spike existed

AutoCast's content ceiling in keyless mode is the hand-authored **seed rotation**:
without an LLM key, the topic/script/direction stages fall back to templates. The
biggest quality lever is *dynamic, any-topic* content, which needs a text LLM.

Every prior cycle assumed "dynamic content needs a human ~2-min key." Before
accepting that permanently, Cycle 11 ran an empirical spike: is there a genuinely
**keyless** text endpoint — the way keyless **Pollinations images** already power
the image stage with zero human step?

## Candidates probed (2026-07-21)

| Endpoint | Keyless? | ToS-clean? | Result |
|---|---|---|---|
| **Pollinations text** (`text.pollinations.ai`, `openai-fast` = GPT-OSS 20B) | Yes (anonymous tier) | Yes | **Cost-gated to ~0.** Only trivial (~0-cost) completions return 200; any real generation → **HTTP 402**. |
| **Cloudflare Workers AI** (`/ai/v1/chat/completions`) | No — per-account | Yes | 404 without an account id + token. Free tier exists but **requires a key**. |
| **HuggingFace serverless inference** | No | Yes | Connection refused / 401 without a token. |
| **DuckDuckGo AI Chat** (`duckduckgo.com/duckchat`) | Technically | **No** | Requires defeating an obfuscated JS anti-bot challenge (`x-vqd-hash-1`); DDG ToS forbids automated/programmatic access. **Excluded on ToS grounds.** |
| **g4f / free-proxy aggregators** | Sometimes | **No** | Scrape provider frontends; explicit ToS violations, unstable. **Excluded.** |

## The decisive evidence — Pollinations anonymous tier is cost-gated to zero

A trivial completion succeeds:

```
POST https://text.pollinations.ai/openai   {"model":"openai","messages":[{"role":"user","content":"Say PONG"}]}
→ HTTP 200   content: "PONG"   user_tier: "anonymous"
```

A **real** script/shot-list prompt (any non-trivial output) is refused:

```
POST https://text.pollinations.ai/openai   (a ~60-word narration or a 4-8 shot JSON list)
→ HTTP 402 Payment Required
   "API key budget too low. This request costs ~0.0002 pollen, but this key has 0.0000."
   deprecation_notice: "... Anonymous requests to text.pollinations.ai are NOT affected."
```

The `deprecation_notice` claims anonymous requests are "NOT affected," but in
practice the **anonymous identity carries a 0.0000-pollen budget**. Any request
that costs more than ~0 pollen (i.e. anything that generates real text) is
rejected. Adding a `referrer` does **not** help — it just creates a named identity
with the same empty budget, which drains after one or two tiny calls.

`GET https://text.pollinations.ai/models` confirms only **one** anonymous model
exists (`openai-fast`, GPT-OSS 20B); there is no alternate free text model.

## Conclusion

Keyless free text generation is **not viable** as of 2026-07-21. The only
ToS-clean keyless option (Pollinations) is cost-gated to zero for real output;
every other free tier requires a key or violates a provider's ToS. The image
stage stays keyless (Pollinations images are still free); **text does not.**

**Implication for the pipeline (already true, now proven):** the keyed cascade in
`autocast/providers/llm.py` (Gemini → Groq → Cloudflare → Cerebras) is the path to
dynamic content, unlocked by one free key. The keyless Pollinations text provider
stays wired as a harmless fast-failing last attempt (it self-heals if a free tier
ever returns), but it must **not** be relied on for real generation.

## Fallback lever shipped this cycle (the autonomous win)

Since dynamic content stays human-gated, Cycle 11 doubled the **keyless content
ceiling** instead: the evergreen **seed rotation expanded from 5 → 10** bespoke,
hand-authored, coherent videos (`autocast/seeds.py`). A keyless channel now ships
**10 distinct days** of content before any repeat (was 5), with the same
script↔shot-list coherence invariant enforced by `tests/test_seeds.py`.
Cycle 13 grew the rotation again, **10 → 15** bespoke seeds (ancient revived
seeds, the world's largest fungus, Tambora's "year without a summer", shape-
memory metal, and birds that sleep in flight), so a keyless channel now runs
**15 distinct days** before any repeat.

## What would flip this to GO (human levers, unchanged)

- Add a free **`GEMINI_API_KEY`** (Google AI Studio, no credit card) — or
  `GROQ_API_KEY` / `CEREBRAS_API_KEY`. One key turns on dynamic any-topic text
  across all three LLM stages with **no code change**.
