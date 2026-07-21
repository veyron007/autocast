"""YouTube OAuth: exchange the stored refresh token for a short-lived access token.

Auth shape (per research doc §8): OAuth 2.0 **Desktop-app** client + the
`youtube.upload` scope. Authorize ONCE interactively (access_type=offline,
prompt=consent), store exactly one refresh token as a secret, auto-refresh every
run here.

THE #1 killer: an OAuth app left in "Testing" mode issues refresh tokens that die
after 7 days. Set the consent screen to "In production." See README gate.
"""

from __future__ import annotations

# TODO(real): import httpx and hit https://oauth2.googleapis.com/token with
#   grant_type=refresh_token. Kept import-light so the dry-run skeleton installs
#   without network deps resolving eagerly.

_TOKEN_URL = "https://oauth2.googleapis.com/token"


class YouTubeAuthError(RuntimeError):
    pass


def get_access_token(
    client_id: str | None,
    client_secret: str | None,
    refresh_token: str | None,
    *,
    dry_run: bool = False,
) -> str:
    """Return a valid access token, refreshing from the refresh token.

    In dry-run we never touch the network — return a clearly-fake token so the
    upload stage can exercise its metadata-derivation path.
    """
    if dry_run:
        return "DRYRUN_ACCESS_TOKEN"

    if not (client_id and client_secret and refresh_token):
        raise YouTubeAuthError(
            "missing YT_CLIENT_ID / YT_CLIENT_SECRET / YT_REFRESH_TOKEN. "
            "See README human-dependency gate."
        )

    # TODO(real): implement the token refresh:
    #   import httpx
    #   resp = httpx.post(_TOKEN_URL, data={
    #       "client_id": client_id,
    #       "client_secret": client_secret,
    #       "refresh_token": refresh_token,
    #       "grant_type": "refresh_token",
    #   }, timeout=30)
    #   resp.raise_for_status()  # on invalid_grant -> refresh token died (7-day / revoked)
    #   return resp.json()["access_token"]
    raise YouTubeAuthError(
        "real YouTube auth not implemented yet (Cycle 4). Run with --dry-run."
    )
