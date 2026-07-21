"""The ONE generic fallback helper used by every LLM/image/TTS stage.

`run_with_fallback` tries providers in order, records which one succeeded, and
raises only if all fail. "Everything fails, all the time" — so this is the single
place that encodes the try-in-order-with-backoff discipline.

Each provider is a `Provider`: a name + a zero-or-more-arg callable. The callable
either returns a result (success) or raises (try the next one). The name of the
provider that succeeded is returned alongside the result so the caller can stamp
it into `spine.stages[].provider_used`.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Callable, Generic, TypeVar

log = logging.getLogger("autocast.cascade")

T = TypeVar("T")


@dataclass(frozen=True)
class Provider(Generic[T]):
    """A named attempt. `call` takes no args — bind inputs with a closure/lambda
    at the call site so the cascade stays generic across stages."""

    name: str
    call: Callable[[], T]


class AllProvidersFailed(RuntimeError):
    """Raised when every provider in the chain failed. Carries the trail."""

    def __init__(self, errors: dict[str, str]) -> None:
        self.errors = errors
        trail = "; ".join(f"{k}: {v}" for k, v in errors.items())
        super().__init__(f"all providers failed -> {trail}")


@dataclass(frozen=True)
class CascadeResult(Generic[T]):
    value: T
    provider_used: str
    attempts: int


def run_with_fallback(
    providers: list[Provider[T]],
    *,
    retries_per_provider: int = 1,
    backoff_s: float = 0.0,
) -> CascadeResult[T]:
    """Try each provider in order (with optional retries + backoff per provider).

    Returns the first success wrapped with the winning provider's name.
    Raises `AllProvidersFailed` only if the whole chain is exhausted.
    """
    if not providers:
        raise ValueError("run_with_fallback: providers list is empty")

    errors: dict[str, str] = {}
    total_attempts = 0

    for provider in providers:
        for attempt in range(1, retries_per_provider + 1):
            total_attempts += 1
            try:
                log.info("cascade: trying %s (attempt %d)", provider.name, attempt)
                value = provider.call()
                log.info("cascade: %s succeeded", provider.name)
                return CascadeResult(
                    value=value,
                    provider_used=provider.name,
                    attempts=total_attempts,
                )
            except Exception as exc:  # noqa: BLE001 - deliberate: fall through
                errors[provider.name] = f"{type(exc).__name__}: {exc}"
                log.warning("cascade: %s failed: %s", provider.name, exc)
                if attempt < retries_per_provider and backoff_s > 0:
                    time.sleep(backoff_s)

    raise AllProvidersFailed(errors)
