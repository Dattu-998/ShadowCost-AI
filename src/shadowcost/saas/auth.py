"""Who is calling, and what may they do in this workspace?

Supabase signs each user's session token with an asymmetric key (ES256) and publishes the public
half at `/auth/v1/.well-known/jwks.json`, so the API verifies tokens without holding any secret.

Roles, from least to most: viewer (sees everything), approver (+ approves agents and queued
actions, runs a day), admin (+ data, connectors, drafting, inviting), owner (+ billing).
A user who isn't a member gets 404, not 403, so workspace ids can't be probed.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache

import jwt
from fastapi import Header, HTTPException

from shadowcost.saas.config import settings
from shadowcost.saas.db import Database, one

ROLES = ("viewer", "approver", "admin", "owner")
RANK = {role: i for i, role in enumerate(ROLES)}


@dataclass(frozen=True)
class User:
    id: str
    email: str


Verifier = Callable[[str], dict]
_verifier: Verifier | None = None


def set_verifier(verifier: Verifier | None) -> None:
    """Replace token verification (tests sign tokens with their own key)."""
    global _verifier
    _verifier = verifier


@lru_cache(maxsize=1)
def _jwks_client() -> jwt.PyJWKClient:
    return jwt.PyJWKClient(settings().jwks_url, cache_keys=True, lifespan=3600)


def verify_supabase_token(token: str) -> dict:
    key = _jwks_client().get_signing_key_from_jwt(token)
    return jwt.decode(token, key.key, algorithms=["ES256", "RS256"], audience="authenticated")


def current_user(authorization: str | None = Header(default=None)) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "sign in first")
    if _verifier is None and not settings().auth_enabled:
        raise HTTPException(503, "accounts are not configured on this server")
    try:
        claims = (_verifier or verify_supabase_token)(authorization.split(" ", 1)[1].strip())
    except jwt.PyJWTError as err:
        raise HTTPException(401, "your session is invalid or has expired; sign in again") from err
    if not claims.get("sub") or not claims.get("email"):
        raise HTTPException(401, "your session has no user")
    return User(id=claims["sub"], email=str(claims["email"]).lower())


def membership(db: Database, org_id: str, user: User, minimum: str = "viewer") -> dict:
    """The caller's membership, if their role is at least `minimum`."""
    found = one(db.select("memberships", where={"org_id": org_id, "user_id": user.id}))
    if not found:
        raise HTTPException(404, "no such workspace")
    if RANK[found["role"]] < RANK[minimum]:
        raise HTTPException(
            403, f"this needs the {minimum} role or higher; you are {found['role']}"
        )
    return found
