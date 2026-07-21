# AutoCast

A fully automated, **zero-cost**, daily faceless-YouTube video pipeline. One
scheduled job per day: pick a topic → write a script → break it into a shot list →
generate images → fake cinematic motion with FFmpeg Ken Burns → narrate → mux →
thumbnail → upload (private) → commit the run back to the repo.

Boring tech. Monolith. Single-process daily batch job — not a service. Every
external call is free / free-tier, and the whole thing runs on GitHub Actions.

## The spine (`run.json`) — the whole architecture

One canonical JSON artifact per run flows through every stage. Each stage is a pure
function `run.json → run.json`: it **reads** fields written by prior stages and
**writes only its own**, stamping its own `status`. The **shot list** (`shots[]`)
is the keystone — it drives image count, scene pacing, caption timing, and upload
metadata. Nothing is computed twice; nothing drifts.

```
runs/<YYYY-MM-DD>/
  run.json          # the spine (source of truth) — committed
  run.log.jsonl     # per-run JSONL log — committed
  assets/           # heavy blobs (mp4/wav/png) — gitignored; thumb.jpg kept
runs/manifest.json  # append-only history index (the UI reads this) — committed
```

`manifest.json` does double duty: it's the history store **and** the
GitHub-Actions keep-alive (a scheduled workflow auto-disables after 60 days of no
commits; committing the manifest each run keeps the cron alive).

## Stages (in order)

`topic → script → direction → images → tts → assets → video → thumbnail → upload`

Each lives in `autocast/stages/<name>.py` and exposes `run(spine, cfg, *, dry_run)`.
The **orchestrator** is the only thing that knows the order; stages never call each
other. Every external call goes through a fallback **cascade** in `autocast/providers/`.

## Run it (dry-run — no keys, no network, no FFmpeg)

The dry-run flows the spine end-to-end using stubs, proving the pipeline shape today.
It needs only Python 3.12+ and `pydantic` (+ Pillow if present for a real thumbnail).

```bash
# with uv (recommended — matches CI)
uv sync
uv run python -m autocast.orchestrator --dry-run

# or with a plain venv
pip install pydantic pydantic-settings httpx
python -m autocast.orchestrator --dry-run
```

Output: `runs/<today>/run.json` with every stage `completed`, plus a stub
`final.mp4`, `voice.wav`, per-shot PNGs, captions `.ass`, thumbnail, and a manifest.

Resumable: re-running the same `--run-id` skips already-`completed` stages. A failed
stage records `failed` + the error, saves the partial spine, and stops (blast radius
= that day only).

```bash
uv run python -m autocast.orchestrator --run-id 2026-07-21 --dry-run
```

## Tests

```bash
uv run --extra dev pytest   # spine round-trip + dry-run end-to-end + provider selection
```

## Configuration / secrets

Copy `.env.example` → `.env` for local dev (gitignored). In production these come
from **GitHub Actions Secrets**. The dry-run needs none of them.

| Concern | Env vars |
|---------|----------|
| LLM cascade | `GEMINI_API_KEY`, `GROQ_API_KEY`, `CEREBRAS_API_KEY` |
| Cloudflare (paid-on-overage; guarded) | `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_BUDGET_CENTS` |
| Assets | `PIXABAY_API_KEY`, `PEXELS_API_KEY`, `FREESOUND_API_KEY` |
| YouTube OAuth | `YT_CLIENT_ID`, `YT_CLIENT_SECRET`, `YT_REFRESH_TOKEN` |
| Render | `VOICE`, `WIDTH`, `HEIGHT`, `FPS`, `TARGET_LEN_S` |

## Human-dependency gate (blocks upload, NOT local render)

Phases 0–1 (topic → local `final.mp4`) build with **zero human input**. Upload is
gated on humans doing this now:

| Gate | Owner | Blocks | Clock |
|------|-------|--------|-------|
| Google Cloud project + OAuth **Desktop** client + one interactive auth to mint the **refresh token** | Human | any upload | hours |
| OAuth consent screen set to **"In production"** (else the refresh token dies every 7 days) | Human | a daily uploader that survives a week | hours |
| **Free YouTube compliance audit** (`youtube.upload` scope) | Human — **start NOW** | **public** publishing (uploads stay `private` until it clears) | **4–6 weeks** |

Until the audit clears, uploads are **always `private`** and the AI-content
disclosure flag is set. Music/stock licenses are recorded in each run's
`license_manifest` for auditability.

## Real render (no `--dry-run`)

```bash
uv sync --extra media --extra tts
uv run python -m autocast.orchestrator --run-id "$(date -u +%F)"
```

This runs the whole chain for real: images from keyless Pollinations Flux, voice
from `edge-tts` (with a local macOS `say` fallback), FFmpeg Ken Burns + mux, and a
Pillow thumbnail. Upload is skipped unless the YouTube secrets are set. Output:
`runs/<today>/assets/final.mp4` (1080p, voiced).

## Add real content with ONE free key

With **no keys**, `topic`/`script`/`direction` fall back to built-in templates, so
every video reads the same. Add **any one** free, no-credit-card key to make the
content dynamic — no code change needed:

| Provider | Free tier | Env var |
|----------|-----------|---------|
| Google Gemini | 1,500 req/day, no card | `GEMINI_API_KEY` |
| Groq | generous free tier | `GROQ_API_KEY` |
| Cerebras | free tier | `CEREBRAS_API_KEY` |

Locally: put it in `.env`. In CI: add it under the repo's **Actions Secrets**. The
cascade tries them in order and degrades to the template if all fail.

## Status

Renders a real 1080p MP4 end-to-end today; content is dynamic once a free LLM key
is added (above); publishing stays gated behind the YouTube compliance audit.
