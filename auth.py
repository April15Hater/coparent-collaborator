"""Authentication via Cloudflare Access JWT.

Cloudflare Access sits in front of coparent.joeysolomon.com and handles
login (Google, email OTP, etc.). It sets a Cf-Access-Jwt-Assertion header
containing the authenticated user's email. We validate that JWT and look
up the user in our database.

For local development, set DEV_USER_EMAIL to bypass CF Access entirely.
"""

import logging
from typing import Optional

import httpx
from fastapi import Depends, HTTPException, Request, status
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import CF_AUD, CF_TEAM_DOMAIN, DEV_USER_EMAIL
from database import get_db
from models import User, UserEmail

log = logging.getLogger(__name__)

# Cache the CF Access public keys (JWKs) with 1-hour TTL
_cf_jwks: dict | None = None
_cf_jwks_fetched_at: float = 0
_CF_JWKS_TTL = 3600  # seconds


async def _get_cf_public_keys(force_refresh: bool = False) -> dict:
    """Fetch Cloudflare Access public keys (cached with 1-hour TTL)."""
    global _cf_jwks, _cf_jwks_fetched_at
    import time

    if not force_refresh and _cf_jwks is not None:
        if (time.time() - _cf_jwks_fetched_at) < _CF_JWKS_TTL:
            return _cf_jwks

    certs_url = f"https://{CF_TEAM_DOMAIN}.cloudflareaccess.com/cdn-cgi/access/certs"
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(certs_url)
        resp.raise_for_status()
        _cf_jwks = resp.json()
        _cf_jwks_fetched_at = time.time()
        log.info("Fetched CF Access public keys from %s", certs_url)
        return _cf_jwks


def _validate_cf_jwt(token: str, keys: dict) -> str:
    """Validate a Cloudflare Access JWT and return the user's email.

    Raises JWTError if validation fails.
    """
    # CF Access JWTs use RS256
    # The 'aud' claim must match our application's AUD tag
    payload = jwt.decode(
        token,
        keys,
        algorithms=["RS256"],
        audience=CF_AUD,
    )
    email = payload.get("email")
    if not email:
        raise JWTError("No email claim in CF Access JWT")
    return email.lower()


async def _lookup_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
    """Find a user by primary email or alias."""
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user:
        return user

    alias_result = await db.execute(
        select(UserEmail).where(UserEmail.email == email)
    )
    alias = alias_result.scalar_one_or_none()
    if alias:
        result = await db.execute(select(User).where(User.id == alias.user_id))
        return result.scalar_one_or_none()

    return None


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    """Get the current user from CF Access JWT or DEV_USER_EMAIL."""
    # Local dev bypass
    if DEV_USER_EMAIL:
        user = await _lookup_user_by_email(db, DEV_USER_EMAIL)
        if user:
            return user
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="no_account",
        )

    # Extract CF Access JWT from header or cookie
    token = (
        request.headers.get("Cf-Access-Jwt-Assertion")
        or request.cookies.get("CF_Authorization")
    )
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        keys = await _get_cf_public_keys()
        email = _validate_cf_jwt(token, keys)
    except JWTError:
        # Retry with fresh keys in case of key rotation
        try:
            keys = await _get_cf_public_keys(force_refresh=True)
            email = _validate_cf_jwt(token, keys)
        except JWTError as e:
            log.warning("CF Access JWT validation failed after key refresh: %s", e)
            raise HTTPException(status_code=401, detail="Invalid CF Access token")
    except Exception as e:
        log.error("Failed to validate CF Access JWT: %s", e)
        raise HTTPException(status_code=401, detail="Authentication error")

    user = await _lookup_user_by_email(db, email)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="no_account",
        )
    return user


async def get_optional_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    """Like get_current_user but returns None instead of raising."""
    try:
        return await get_current_user(request, db)
    except HTTPException:
        return None


def require_parent_a(user: User = Depends(get_current_user)) -> User:
    """Dependency that requires the user to be parent_a."""
    if user.role != "parent_a":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only parent_a can perform this action",
        )
    return user


async def invalidate_cf_keys():
    """Clear the cached CF Access keys (call on key rotation)."""
    global _cf_jwks
    _cf_jwks = None
