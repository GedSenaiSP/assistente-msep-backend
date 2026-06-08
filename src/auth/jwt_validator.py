"""
JWT Validator for WSO2 Identity Server.

Validates JWT tokens using the public keys from the WSO2 JWKS endpoint.
Roles are NOT extracted from the JWT — the existing database-based
permission system handles authorization.
"""

import logging
from dataclasses import dataclass

import jwt
from jwt import PyJWKClient

logger = logging.getLogger(__name__)


@dataclass
class AuthenticatedUser:
    """Represents an authenticated user extracted from a valid JWT."""
    user_id: str
    email: str | None = None


class JWTValidator:
    """Validates WSO2 JWT tokens via JWKS endpoint with built-in key caching."""

    def __init__(self, jwks_url: str, issuer: str):
        self._jwks_client = PyJWKClient(
            jwks_url,
            cache_jwk_set=True,
            lifespan=3600,  # Cache keys for 1 hour
        )
        self._issuer = issuer

    def validate(self, token: str) -> AuthenticatedUser:
        """Validate JWT signature and expiration, return authenticated user.

        Only validates:
        - Signature (RS256 via JWKS)
        - Issuer (iss claim)
        - Expiration (exp claim)

        Does NOT validate audience (aud) — WSO2 may use different aud values.
        Roles are managed by the existing database system.
        """
        signing_key = self._jwks_client.get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=self._issuer,
            options={"verify_exp": True, "verify_aud": False},
        )
        return AuthenticatedUser(
            user_id=payload.get("sub"),
            email=payload.get("email"),
        )
