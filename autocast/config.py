"""Typed configuration + secrets, loaded from environment variables.

Secrets come from GitHub Actions Secrets -> env -> here. NOTHING is committed.
See `.env.example` for the full list. Local dev may use a `.env` file (gitignored).

Per the CTO doc: `pydantic-settings` reading env vars. No config service.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo-relative default output roots. `runs/` is committed back by the Action.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Config(BaseSettings):
    """All runtime settings + secrets. Missing secrets are allowed at import
    time (they're only required by the stages that use them) so `--dry-run`
    works with zero keys."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---- output dirs (state lives in the repo) ----
    runs_dir: Path = _PROJECT_ROOT / "runs"
    queue_path: Path = _PROJECT_ROOT / "queue" / "topics.json"

    # ---- render settings (mirrored into the spine's config_snapshot) ----
    voice: str = "af_heart"
    width: int = 1920
    height: int = 1080
    fps: int = 30
    target_len_s: int = 90

    # ---- LLM providers (cascade order: gemini -> groq -> cloudflare -> cerebras)
    gemini_api_key: str | None = Field(default=None)
    groq_api_key: str | None = Field(default=None)
    cerebras_api_key: str | None = Field(default=None)

    # ---- Cloudflare Workers AI (LLM + image fallback). Bills on overage:
    #      cascade.py must guard it behind the budget kill-switch.
    cloudflare_api_token: str | None = Field(default=None)
    cloudflare_account_id: str | None = Field(default=None)

    # ---- image providers (gemini-image -> pollinations[keyless] -> cloudflare-flux)
    #      Pollinations needs no key.

    # ---- assets ----
    pixabay_api_key: str | None = Field(default=None)
    pexels_api_key: str | None = Field(default=None)
    freesound_api_key: str | None = Field(default=None)

    # ---- YouTube OAuth (Desktop client + one refresh token; see README gate) ----
    yt_client_id: str | None = Field(default=None)
    yt_client_secret: str | None = Field(default=None)
    yt_refresh_token: str | None = Field(default=None)

    # ---- safety: Cloudflare overage budget kill-switch (USD cents). 0 = never
    #      allow paid Cloudflare fallback. Raise deliberately once a budget is set.
    cloudflare_budget_cents: int = 0

    # ---- helpers ----

    def run_dir(self, run_id: str) -> Path:
        return self.runs_dir / run_id

    def run_json_path(self, run_id: str) -> Path:
        return self.run_dir(run_id) / "run.json"

    def assets_dir(self, run_id: str) -> Path:
        return self.run_dir(run_id) / "assets"

    def manifest_path(self) -> Path:
        return self.runs_dir / "manifest.json"


def load_config() -> Config:
    """Single entry point so the rest of the code never touches env directly."""
    return Config()
