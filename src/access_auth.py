"""Checks the Cloudflare Access token on a web sender's request and returns the sender's email."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import jwt

HEADER = "Cf-Access-Jwt-Assertion"
LEEWAY_SECONDS = 60
FETCH_TIMEOUT_SECONDS = 3
RETRY_AFTER_SECONDS = 10

# fetch_data runs json.load on the response, so a non-JSON certs page raises a plain ValueError.
_FETCH_ERRORS = (jwt.PyJWTError, OSError, ValueError)


class AccessDenied(Exception):
    """The reason is for server logs, never for the HTTP response."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class AccessCerts(jwt.PyJWKClient):
    """Serves the last good key set while the certs endpoint fails."""

    def __init__(self, url: str, timeout: float = FETCH_TIMEOUT_SECONDS, **options: Any) -> None:
        super().__init__(url, timeout=timeout, **options)
        self.last_good: dict[str, Any] | None = None
        self.failed_at: float | None = None

    def fetch_data(self) -> Any:
        # PyJWKClient holds a lock across this call, so every waiting request would repeat a hung fetch.
        if self.failed_at is None or time.monotonic() - self.failed_at >= RETRY_AFTER_SECONDS:
            try:
                self.last_good = super().fetch_data()
                self.failed_at = None
                return self.last_good
            except _FETCH_ERRORS:
                self.failed_at = time.monotonic()
        if self.last_good is None:
            raise jwt.PyJWKClientConnectionError("certs endpoint unavailable")
        return self.last_good


class AccessVerifier:
    def __init__(self, team_domain: str, audience: str, keys: jwt.PyJWKClient | None = None) -> None:
        self.issuer = f"https://{team_domain}"
        self.audience = audience
        self.keys = keys or AccessCerts(f"{self.issuer}/cdn-cgi/access/certs")

    async def verify(self, token: str | None) -> str:
        """Return the sender's email. Runs in a thread: a key fetch is a blocking HTTP call."""
        return await asyncio.to_thread(self._verify, token)

    def _verify(self, token: str | None) -> str:
        if not token:
            raise AccessDenied(f"missing {HEADER} header")
        try:
            key = self.keys.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                key.key,
                algorithms=["RS256"],
                audience=self.audience,
                issuer=self.issuer,
                leeway=LEEWAY_SECONDS,
                options={"require": ["exp", "iss", "aud"]},
            )
        # The error message can quote token fields such as the kid, so only the class name is kept.
        except _FETCH_ERRORS as error:
            raise AccessDenied(f"invalid Access token ({type(error).__name__})") from None
        email = claims.get("email")
        if not isinstance(email, str) or not email:
            raise AccessDenied("Access token has no email")
        return email
