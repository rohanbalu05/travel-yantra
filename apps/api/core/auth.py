"""Firebase ID-token verification (HQ V3-AG: Google sign-in). No firebase-admin and no service-account key:
the token's signature is checked against Google's published certificates with google-auth.

TY_FIREBASE_PROJECT_ID names the Firebase project; without it, sign-in is off and only X-Client-Id works.
"""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.request
from dataclasses import dataclass

CERTS_URL = "https://www.googleapis.com/robot/v1/metadata/x509/securetoken@system.gserviceaccount.com"
CERTS_TTL_S = 3600
# Account ids carry a prefix with a ":", which an anonymous X-Client-Id can never contain.
ACCOUNT_PREFIX = "fb:"
MAX_UID = 128  # Firebase's limit for a uid


class AuthError(Exception):
    """The bearer token is missing its project, malformed, expired or not ours. Maps to HTTP 401."""


class AuthUnavailable(Exception):
    """Google's certificates could not be fetched and none are cached. Maps to HTTP 503."""


@dataclass(frozen=True)
class Claims:
    uid: str
    email: str | None
    name: str | None


def project_id() -> str | None:
    return os.getenv("TY_FIREBASE_PROJECT_ID") or None


_certs: dict[str, str] = {}
_certs_at = 0.0
_lock = threading.Lock()


def _fetch_certs() -> dict[str, str]:
    with urllib.request.urlopen(CERTS_URL, timeout=5) as r:  # noqa: S310 (fixed https URL)
        return json.loads(r.read().decode())


def certs() -> dict[str, str]:
    """Google's signing certificates, fetched at most once an hour per instance."""
    global _certs, _certs_at
    with _lock:
        if not _certs or time.monotonic() - _certs_at > CERTS_TTL_S:
            try:
                _certs, _certs_at = _fetch_certs(), time.monotonic()
            except (OSError, ValueError) as exc:  # network, timeout or bad JSON
                if not _certs:
                    raise AuthUnavailable("sign-in is unavailable right now") from exc
                # Keep using the certificates we have (Google rotates them slowly); try again next call.
        return _certs


def verify(token: str) -> Claims:
    """Check the signature, audience, issuer and subject of a Firebase ID token. Blocking (may fetch certs);
    FastAPI runs the sync dependency that calls it in its threadpool."""
    from google.auth import exceptions, jwt

    project = project_id()
    if not project:
        raise AuthError("sign-in is not configured")
    try:
        claims = jwt.decode(token, certs=certs(), audience=project)
    except (ValueError, exceptions.GoogleAuthError) as exc:
        raise AuthError("invalid or expired sign-in token") from exc
    sub = claims.get("sub")
    if claims.get("iss") != f"https://securetoken.google.com/{project}" or not isinstance(sub, str)             or not 0 < len(sub) <= MAX_UID:
        raise AuthError("sign-in token is not for this app")
    return Claims(uid=ACCOUNT_PREFIX + sub, email=claims.get("email"), name=claims.get("name"))
