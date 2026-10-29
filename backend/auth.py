import os
from functools import lru_cache
from urllib.parse import urlsplit

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

bearer = HTTPBearer(auto_error=False)


@lru_cache(maxsize=4)
def key_client(issuer):
    return jwt.PyJWKClient(
        issuer + "/.well-known/jwks.json", cache_jwk_set=True, lifespan=300, timeout=5
    )


def require_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(401, "Please sign in to access your scans.", headers={"WWW-Authenticate": "Bearer"})
    issuer = os.getenv("CLERK_ISSUER_URL", "").rstrip("/")
    parsed = urlsplit(issuer)
    if parsed.scheme != "https" or not parsed.hostname or parsed.query or parsed.fragment or parsed.username:
        raise HTTPException(503, "Sign-in is not configured. Please contact the site owner.")
    origins = {origin.strip() for origin in os.getenv(
        "CLERK_AUTHORIZED_PARTIES", os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")
    ).split(",") if origin.strip()}
    try:
        token = credentials.credentials
        if len(token) > 16384:
            raise jwt.InvalidTokenError()
        key = key_client(issuer).get_signing_key_from_jwt(token).key
        claims = jwt.decode(
            token, key, algorithms=["RS256"], issuer=issuer,
            options={"require": ["exp", "iat", "nbf", "iss", "sub", "sid", "azp"]},
        )
        if claims["azp"] not in origins or claims.get("sts") == "pending":
            raise jwt.InvalidTokenError()
        user_id = claims["sub"]
        if not isinstance(user_id, str) or not user_id.startswith("user_") or len(user_id) > 255 or not claims["sid"]:
            raise jwt.InvalidTokenError()
        return user_id
    except jwt.PyJWKClientConnectionError:
        raise HTTPException(503, "Sign-in verification is temporarily unavailable. Please retry.") from None
    except (jwt.PyJWTError, ValueError, TypeError, KeyError):
        raise HTTPException(401, "Your session is invalid or expired. Please sign in again.", headers={"WWW-Authenticate": "Bearer"}) from None
