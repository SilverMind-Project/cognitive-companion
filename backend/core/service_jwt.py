"""Short-lived service JWT minter for CC -> microservice calls.

Microservices verify ``iss``, ``aud``, ``exp``, and the signing key.

Dev-mode fallback: when ``cts.jwt.private_key_pem`` is absent from
settings, ``mint_service_jwt()`` returns an empty string and a
``service_jwt_disabled`` warning is logged once.  Every upstream client
still sends an ``Authorization`` header; the microservice may skip
verification when its own JWT config is absent.
"""

from __future__ import annotations

import time
from functools import cache

from backend.core.config import settings
from backend.core.logging import get_logger

logger = get_logger(__name__)

_warned_once = False


@cache
def _private_key() -> tuple[str | None, str | None]:
    """Return (pem, kid) from settings, or (None, None) in dev mode."""
    pem: str | None = settings.get("cts.jwt.private_key_pem")
    kid: str | None = settings.get("cts.jwt.kid", "cts-svc-key-1")
    return pem, kid


def mint_service_jwt(*, aud: str, ttl_s: int = 60) -> str:
    """Return a signed EdDSA JWT for the given audience.

    Returns an empty string when ``cts.jwt.private_key_pem`` is not
    configured (dev mode).  The caller still sends the ``Authorization``
    header; an empty Bearer token is ignored by microservices running in
    dev mode.
    """
    global _warned_once
    pem, kid = _private_key()
    if not pem:
        if not _warned_once:
            logger.warning(
                "service_jwt_disabled",
                reason="cts.jwt.private_key_pem not configured; using dev mode (no JWT)",
            )
            _warned_once = True
        return ""

    try:
        import jwt  # pyjwt[cryptography]

        now = int(time.time())
        return jwt.encode(
            {
                "iss": "cognitive-companion",
                "aud": aud,
                "iat": now,
                "nbf": now,
                "exp": now + ttl_s,
                "sub": "svc/cognitive-companion",
            },
            pem,
            algorithm="EdDSA",
            headers={"kid": kid},
        )
    except ImportError:
        if not _warned_once:
            logger.warning(
                "service_jwt_disabled",
                reason="pyjwt[cryptography] not installed",
            )
            _warned_once = True
        return ""
