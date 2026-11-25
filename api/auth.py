"""OIDC access-token validation and platform-admin authorization."""
import logging
from functools import lru_cache
from urllib.parse import urlsplit

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
from jwt.exceptions import PyJWKClientConnectionError, PyJWTError

from config import (
    AUTH_ADMIN_SUBJECTS,
    OIDC_AUDIENCE,
    OIDC_ISSUER,
    OIDC_JWKS_URL,
)


logger = logging.getLogger(__name__)
_bearer = HTTPBearer(auto_error=False)


@lru_cache(maxsize=4)
def _jwks_client(url):
    return PyJWKClient(url, cache_keys=True, timeout=5)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
):
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Authentication required.")
    if not (OIDC_ISSUER and OIDC_AUDIENCE and OIDC_JWKS_URL):
        raise HTTPException(
            status_code=503,
            detail="Authentication is not configured on this server.",
        )
    issuer_url = urlsplit(OIDC_ISSUER)
    jwks_url = urlsplit(OIDC_JWKS_URL)
    if (
        issuer_url.scheme != "https"
        or not issuer_url.hostname
        or jwks_url.scheme != "https"
        or not jwks_url.hostname
    ):
        raise HTTPException(
            status_code=503,
            detail="Authentication requires HTTPS issuer and signing-key URLs.",
        )

    try:
        signing_key = _jwks_client(OIDC_JWKS_URL).get_signing_key_from_jwt(
            credentials.credentials
        )
        claims = jwt.decode(
            credentials.credentials,
            signing_key.key,
            algorithms=["RS256", "ES256"],
            audience=OIDC_AUDIENCE,
            issuer=OIDC_ISSUER,
            options={"require": ["exp", "sub"]},
        )
    except PyJWKClientConnectionError as error:
        logger.warning("OIDC signing keys are unavailable (%s)", type(error).__name__)
        raise HTTPException(
            status_code=503,
            detail="Authentication service is temporarily unavailable.",
        ) from error
    except PyJWTError as error:
        logger.info("Rejected invalid OIDC access token (%s)", type(error).__name__)
        raise HTTPException(status_code=401, detail="Invalid or expired access token.") from error

    subject = claims.get("sub")
    issuer = claims.get("iss")
    if not isinstance(subject, str) or not subject or issuer != OIDC_ISSUER:
        raise HTTPException(status_code=401, detail="Invalid access token.")
    return {"issuer": issuer, "subject": subject}


def require_platform_admin(user=Depends(get_current_user)):
    if user["subject"] not in AUTH_ADMIN_SUBJECTS:
        raise HTTPException(status_code=403, detail="Administrator access required.")
    return user
