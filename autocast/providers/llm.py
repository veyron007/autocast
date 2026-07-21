"""LLM provider cascade: gemini -> groq -> cloudflare -> cerebras -> keyless.

All keyed providers are OpenAI-compatible (same /chat/completions shape, just a
different base_url + model + bearer key), so the whole cascade is bindings of one
`_call_openai_compat` call. `build_llm_providers(...)` returns the ordered
`Provider` list the cascade runs; keyed providers are included only when their key
is present, so a zero-key run still degrades cleanly to the keyless fallback and
then to each stage's built-in template.

Add real content with ONE free key (no credit card) — set any of GEMINI_API_KEY /
GROQ_API_KEY / CEREBRAS_API_KEY in the environment and every stage starts
producing dynamic text with no code change.

NOTES:
- Cerebras has an 8k-context cap -> use it for topic/script only, NOT the
  shot-list (direction) stage (research §1); gated by `allow_cerebras`.
- Cloudflare Workers AI bills on overage -> gated behind `cloudflare_budget_cents`
  (0 = never use it; the documented kill-switch in config).
- The keyless Pollinations text tier now returns HTTP 402 for anonymous requests
  too (it started charging "pollen"), so it is no longer a reliable free provider
  — kept only as a fast-failing final attempt in case a free tier returns.
"""

from __future__ import annotations

import logging

from autocast.config import Config
from autocast.providers.cascade import AllProvidersFailed, Provider, run_with_fallback
from autocast.util.net import post_json

log = logging.getLogger("autocast.providers.llm")

# ---- Keyed, OpenAI-compatible endpoints. Free tiers need no credit card. ----
# Change a model here if a provider retires one; every entry is the exact same
# HTTP shape, so no other code changes.
_GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
_GEMINI_MODEL = "gemini-2.0-flash"
_GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
_GROQ_MODEL = "llama-3.3-70b-versatile"
_CEREBRAS_URL = "https://api.cerebras.ai/v1/chat/completions"
_CEREBRAS_MODEL = "llama-3.3-70b"
# Cloudflare Workers AI exposes an OpenAI-compatible endpoint per account.
_CLOUDFLARE_URL = (
    "https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1/chat/completions"
)
_CLOUDFLARE_MODEL = "@cf/meta/llama-3.1-8b-instruct"

# ---- Keyless fallback (now paywalled; kept as a fast-failing last resort). ----
_POLLINATIONS_OPENAI = "https://text.pollinations.ai/openai"
_POLLINATIONS_MODEL = "openai"
_REFERRER = "autocast"  # Pollinations-specific; never sent to keyed providers.


def _dry_stub(prompt: str, kind: str) -> str:
    """Deterministic placeholder so dry-run downstream stages have real inputs."""
    return f"[DRYRUN {kind}] {prompt[:60]}"


def _call_openai_compat(
    base_url: str,
    model: str,
    prompt: str,
    *,
    api_key: str | None = None,
    temperature: float = 0.7,
    extra_body: dict | None = None,
) -> str:
    """One OpenAI-compatible chat call. Every keyed LLM provider is this shape with
    a different base_url/model/key — so the cascade is just bindings of this fn.

    `extra_body` carries provider-specific fields (e.g. Pollinations' `referrer`);
    keyed providers get none, since strict endpoints can reject unknown fields."""
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else None
    body: dict = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
    }
    if extra_body:
        body.update(extra_body)
    resp = post_json(
        base_url,
        body,
        headers=headers,
        timeout=20.0,
        retries=1,  # the cascade's NEXT provider is the retry; fail fast on a hang
        backoff_s=0.0,
    )
    content = resp["choices"][0]["message"]["content"]
    if not isinstance(content, str) or not content.strip():
        raise ValueError("LLM returned empty content")
    return content.strip()


def _keyed_provider(
    name: str, base_url: str, model: str, api_key: str, prompt: str
) -> Provider[str]:
    """Bind one keyed OpenAI-compatible provider for the cascade (cascade.py logs
    the provider name on each attempt, so no extra logging is needed here)."""
    return Provider(name, lambda: _call_openai_compat(base_url, model, prompt, api_key=api_key))


def _pollinations_openai(prompt: str, kind: str) -> str:
    log.info("llm[%s]: calling pollinations-openai (keyless, POST)", kind)
    return _call_openai_compat(
        _POLLINATIONS_OPENAI, _POLLINATIONS_MODEL, prompt, extra_body={"referrer": _REFERRER}
    )


def build_llm_providers(
    cfg: Config,
    *,
    prompt: str,
    kind: str,
    allow_cerebras: bool = True,
    dry_run: bool = False,
) -> list[Provider[str]]:
    """Return the ordered LLM providers for the cascade.

    `kind` is a label ("topic-rank" | "script" | "direction") used for logging
    and the dry stub. `allow_cerebras=False` for the direction (shot-list) stage
    because of the 8k context cap.

    Keyed providers (Gemini/Groq/Cloudflare/Cerebras) go FIRST when their key is
    present, in the documented order; keyless Pollinations is always the final
    attempt so a zero-key run still tries for real text before a stage's template.
    """
    if dry_run:
        return [Provider("dry-stub", lambda: _dry_stub(prompt, kind))]

    providers: list[Provider[str]] = []

    if cfg.gemini_api_key:
        providers.append(
            _keyed_provider("gemini", _GEMINI_URL, _GEMINI_MODEL, cfg.gemini_api_key, prompt)
        )
    if cfg.groq_api_key:
        providers.append(
            _keyed_provider("groq", _GROQ_URL, _GROQ_MODEL, cfg.groq_api_key, prompt)
        )
    # Cloudflare bills on overage -> only when a budget is explicitly set (>0).
    if (
        cfg.cloudflare_api_token
        and cfg.cloudflare_account_id
        and cfg.cloudflare_budget_cents > 0
    ):
        providers.append(
            _keyed_provider(
                "cloudflare",
                _CLOUDFLARE_URL.format(account_id=cfg.cloudflare_account_id),
                _CLOUDFLARE_MODEL,
                cfg.cloudflare_api_token,
                prompt,
            )
        )
    # Cerebras' 8k context can't hold the shot-list prompt -> topic/script only.
    if allow_cerebras and cfg.cerebras_api_key:
        providers.append(
            _keyed_provider(
                "cerebras", _CEREBRAS_URL, _CEREBRAS_MODEL, cfg.cerebras_api_key, prompt
            )
        )

    # Keyless final attempt (currently paywalled; harmless fast-fail, self-heals
    # if a free tier returns).
    providers.append(Provider("pollinations-openai", lambda: _pollinations_openai(prompt, kind)))
    return providers


# Sentinel provider name recorded when every LLM failed and the stage used its
# built-in deterministic template instead of dying.
TEMPLATE_FALLBACK = "template-fallback"


def try_llm(providers: list[Provider[str]]) -> tuple[str | None, str]:
    """Run the LLM cascade, degrading gracefully.

    Returns (text, provider_used) on success, or (None, TEMPLATE_FALLBACK) if the
    whole cascade failed — so an LLM-using stage NEVER kills the run over a flaky
    free endpoint; it falls back to its template and keeps the pipeline moving.
    """
    try:
        result = run_with_fallback(providers)
        return result.value, result.provider_used
    except AllProvidersFailed as exc:
        log.warning("llm: all providers failed (%s); caller falls back to template", exc)
        return None, TEMPLATE_FALLBACK
