# AutoCast — The Cutting Room (operator desk)

A single, non-template dashboard for the AutoCast pipeline. It is a **static site**
(three files, no build, no server, no cost) that reads the repo's committed spine and
gives one real UI — not the CLI — for watching runs and steering the channel.

- `index.html` · `styles.css` · `app.js` — vanilla, zero dependencies.

## What it shows (reads)

- **The Reel** — every run from `runs/manifest.json`, newest first, with its thumbnail.
- **The Spine** — the nine synchronized stages of the selected run from
  `runs/<id>/run.json`, drawn as a **signal chain**: the wire lights green wherever the
  signal passed (topic → script → direction → images → tts → assets → video → thumbnail
  → upload), amber where a stage is rendering, red where it failed. This is the standing
  directive made visible — *script drives direction drives generation drives upload*.
- **Shot list, shooting script, publish state, render config** — straight from the spine,
  including which provider and which seed produced each stage.

Data is fetched from `raw.githubusercontent.com` (CORS-enabled), so the desk shows the
**live committed state** wherever it is hosted — GitHub Pages, Cloudflare Pages, or a
local `python -m http.server` from the repo root (it falls back to relative paths).

## What it changes (writes) — zero server, zero committed secret

Two write actions, each with a graceful fallback:

| Action | With a token | Without a token |
|--------|--------------|-----------------|
| **Save cue sheet** (edit `queue/topics.json`) | Commits via the GitHub Contents API | Copies the exact JSON to your clipboard and opens the GitHub web editor |
| **Render / retry a run** | Triggers the `daily.yml` workflow via `workflow_dispatch` (targets the selected `run_id`) | Opens the Actions tab so you click **Run workflow** |

The token is a GitHub **fine-grained PAT** (scoped to this repo: *Contents* read/write +
*Actions* read/write). Click **⚿ ACCESS** and paste it. It is stored **only in your
browser's `localStorage`** — never committed, never sent anywhere but `api.github.com`.
Clear it anytime.

> **Retry semantics:** the orchestrator is resumable. Dispatching a *failed or partial*
> run re-attempts its unfinished stages; a *finished* run is a no-op (every stage skips).

## Deploy (free)

**GitHub Pages** — repo → **Settings → Pages → Deploy from a branch → `main` / `/docs`**.
The desk goes live at `https://veyron007.github.io/autocast/`. No build step, no secrets.

(Cloudflare Pages works too: point it at this repo, build command *none*, output dir
`docs`.)
