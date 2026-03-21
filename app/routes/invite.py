"""Invite route: parent_a adds the co-parent by email. Email alias management."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import create_audit_entry
from app.auth import get_current_user, require_parent_a
from app.database import get_db
from app.models import User, UserEmail

router = APIRouter(prefix="/auth", tags=["auth"])


class InviteRequest(BaseModel):
    email: str
    display_name: str = ""


class AddEmailRequest(BaseModel):
    email: str


async def _email_in_use(db: AsyncSession, email: str) -> bool:
    """Check if an email is already used as a primary or alias."""
    r1 = await db.execute(select(User).where(User.email == email))
    if r1.scalar_one_or_none():
        return True
    r2 = await db.execute(select(UserEmail).where(UserEmail.email == email))
    return r2.scalar_one_or_none() is not None


@router.post("/invite")
async def send_invite(
    body: InviteRequest,
    user=Depends(require_parent_a),
    db: AsyncSession = Depends(get_db),
):
    """parent_a adds the co-parent as parent_b. She signs in via Cloudflare Access."""
    email = body.email.strip().lower()
    if await _email_in_use(db, email):
        raise HTTPException(status_code=400, detail="An account with this email already exists")

    new_user = User(
        email=email,
        display_name=body.display_name or email.split("@")[0].title(),
        role="parent_b",
    )
    db.add(new_user)
    await db.flush()
    await db.refresh(new_user)

    await create_audit_entry(
        db, "users", new_user.id, "create", user.id,
        new_values={"email": new_user.email, "display_name": new_user.display_name, "role": new_user.role},
    )

    return {
        "detail": "Co-parent added. They can sign in via Cloudflare Access with this email.",
        "user": {"id": str(new_user.id), "email": new_user.email, "display_name": new_user.display_name},
    }


@router.post("/me/emails")
async def add_email_alias(
    body: AddEmailRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add an additional email address to the current user's account.
    Allows signing in from multiple email addresses."""
    email = body.email.strip().lower()
    if await _email_in_use(db, email):
        raise HTTPException(status_code=400, detail="This email is already associated with an account")

    alias = UserEmail(user_id=user.id, email=email)
    db.add(alias)
    await db.flush()

    await create_audit_entry(
        db, "user_emails", alias.id, "create", user.id,
        new_values={"email": email},
    )

    return {"detail": f"Email {email} linked to your account"}


@router.get("/me/emails")
async def list_email_aliases(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all emails linked to the current user."""
    result = await db.execute(select(UserEmail).where(UserEmail.user_id == user.id))
    aliases = result.scalars().all()

    return {
        "primary": user.email,
        "aliases": [a.email for a in aliases],
    }


@router.delete("/me/emails/{email}")
async def remove_email_alias(
    email: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove an email alias (cannot remove primary email)."""
    if email == user.email:
        raise HTTPException(status_code=400, detail="Cannot remove your primary email")

    result = await db.execute(
        select(UserEmail).where(UserEmail.user_id == user.id, UserEmail.email == email)
    )
    alias = result.scalar_one_or_none()
    if not alias:
        raise HTTPException(status_code=404, detail="Email alias not found")

    await create_audit_entry(
        db, "user_emails", alias.id, "delete", user.id,
        old_values={"email": email},
    )

    await db.delete(alias)
    return {"detail": f"Email {email} removed from your account"}
