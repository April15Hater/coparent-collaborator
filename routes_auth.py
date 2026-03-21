"""Authentication routes — session info and logout.

Auth is handled by Cloudflare Access. These routes just provide
user info and logout functionality.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Response

from auth import get_current_user, invalidate_cf_keys
from config import CF_TEAM_DOMAIN
from models import User
from schemas import UserResponse

log = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me", response_model=UserResponse)
async def me(user: User = Depends(get_current_user)):
    """Get the current authenticated user."""
    return user


@router.post("/logout")
async def logout():
    """Return the CF Access logout URL."""
    logout_url = "/login"
    if CF_TEAM_DOMAIN:
        logout_url = f"https://{CF_TEAM_DOMAIN}.cloudflareaccess.com/cdn-cgi/access/logout"
    return {"detail": "Logged out", "logout_url": logout_url}


@router.post("/refresh-keys")
async def refresh_keys(user: User = Depends(get_current_user)):
    """Clear cached CF Access public keys (admin only)."""
    if user.role != "parent_a":
        raise HTTPException(status_code=403, detail="Not authorized")
    await invalidate_cf_keys()
    return {"detail": "CF Access key cache cleared"}
