"""Tiny HTTP helpers over httpx — the ONE place network I/O + retries live.

Every real provider (Pollinations image/text, Google Trends RSS, YouTube) goes
through here so timeout + retry + a sane User-Agent are consistent and testable.
Keeps provider modules free of httpx boilerplate.
"""

from __future__ import annotations

import logging
import time

import httpx

log = logging.getLogger("autocast.net")

# Free public endpoints occasionally 5xx / rate-limit under load; a couple of
# spaced retries turns a flaky call into a reliable one without masking a real
# outage (the cascade still falls through to the next provider if we exhaust).
_DEFAULT_RETRIES = 3
_DEFAULT_BACKOFF_S = 2.0
_UA = "AutoCast/0.1 (+https://github.com/; faceless-youtube-pipeline)"


def _sleep(seconds: float) -> None:
    # Wrapped so tests can monkeypatch without importing time everywhere.
    time.sleep(seconds)


def _request(
    method: str,
    url: str,
    *,
    timeout: float,
    retries: int,
    backoff_s: float,
    **kwargs,
) -> httpx.Response:
    """Issue a request with linear backoff; raise the last error if all fail."""
    headers = {"User-Agent": _UA, **kwargs.pop("headers", {})}
    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            resp = httpx.request(
                method, url, timeout=timeout, headers=headers, follow_redirects=True, **kwargs
            )
            resp.raise_for_status()
            return resp
        except Exception as exc:  # noqa: BLE001 - retry then re-raise the last
            last_exc = exc
            log.warning("net: %s %s failed (attempt %d/%d): %s", method, url[:80], attempt, retries, exc)
            if attempt < retries:
                _sleep(backoff_s * attempt)
    assert last_exc is not None
    raise last_exc


def get_bytes(
    url: str,
    *,
    timeout: float = 90.0,
    retries: int = _DEFAULT_RETRIES,
    backoff_s: float = _DEFAULT_BACKOFF_S,
    params: dict | None = None,
) -> bytes:
    """GET raw bytes (images, RSS). Validates HTTP status; retries transient errors."""
    return _request("GET", url, timeout=timeout, retries=retries, backoff_s=backoff_s, params=params).content


def get_text(
    url: str,
    *,
    timeout: float = 30.0,
    retries: int = _DEFAULT_RETRIES,
    backoff_s: float = _DEFAULT_BACKOFF_S,
    params: dict | None = None,
) -> str:
    return _request("GET", url, timeout=timeout, retries=retries, backoff_s=backoff_s, params=params).text


def post_json(
    url: str,
    payload: dict,
    *,
    timeout: float = 90.0,
    retries: int = _DEFAULT_RETRIES,
    backoff_s: float = _DEFAULT_BACKOFF_S,
    headers: dict | None = None,
) -> dict:
    """POST JSON, return the decoded JSON response body."""
    resp = _request(
        "POST",
        url,
        timeout=timeout,
        retries=retries,
        backoff_s=backoff_s,
        json=payload,
        headers=headers or {},
    )
    return resp.json()
