"""AI rewrite endpoint — adjust tone of a comment before posting."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ai_rewrite import TONE_PROMPTS, check_appropriateness, rewrite_comment, summarize_thread
from auth import get_current_user
from config import ANTHROPIC_API_KEY
from database import get_db
from models import Comment, Issue, User

router = APIRouter(prefix="/api/ai", tags=["ai"])


class RewriteRequest(BaseModel):
    text: str
    tone: str


class RewriteResponse(BaseModel):
    original: str
    rewritten: str
    tone: str


@router.post("/rewrite", response_model=RewriteResponse)
async def rewrite(
    body: RewriteRequest,
    user: User = Depends(get_current_user),
):
    """Rewrite a comment draft with the specified tone."""
    if not ANTHROPIC_API_KEY:
        raise HTTPException(status_code=503, detail="AI rewrite not available")

    if body.tone not in TONE_PROMPTS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown tone. Options: {', '.join(TONE_PROMPTS.keys())}",
        )

    if not body.text.strip():
        raise HTTPException(status_code=400, detail="No text to rewrite")

    if len(body.text) > 5000:
        raise HTTPException(status_code=400, detail="Text too long (max 5000 characters)")

    result = await rewrite_comment(body.text, body.tone)
    if result is None:
        raise HTTPException(status_code=500, detail="Rewrite failed, please try again")

    return RewriteResponse(original=body.text, rewritten=result, tone=body.tone)


class ThreadEntry(BaseModel):
    author: str
    body: str


class CheckRequest(BaseModel):
    text: str
    thread_history: list[ThreadEntry] = []


class CheckResponse(BaseModel):
    appropriate: bool
    reason: str = ""


@router.post("/check", response_model=CheckResponse)
async def check_comment(
    body: CheckRequest,
    user: User = Depends(get_current_user),
):
    """Check if a comment is appropriate before posting."""
    if not ANTHROPIC_API_KEY:
        return CheckResponse(appropriate=True)

    if not body.text.strip():
        return CheckResponse(appropriate=True)

    history = [{"author": e.author, "body": e.body} for e in body.thread_history] if body.thread_history else None
    result = await check_appropriateness(body.text, thread_history=history)
    return CheckResponse(
        appropriate=result.get("appropriate", True),
        reason=result.get("reason", ""),
    )


class SummaryResponse(BaseModel):
    summary: str
    comment_count: int


@router.get("/summarize/{issue_id}", response_model=SummaryResponse)
async def summarize(
    issue_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate an AI summary of a topic's discussion thread."""
    if not ANTHROPIC_API_KEY:
        raise HTTPException(status_code=503, detail="AI not available")

    result = await db.execute(
        select(Issue).where(Issue.id == issue_id)
    )
    issue = result.scalar_one_or_none()
    if not issue:
        raise HTTPException(status_code=404, detail="Topic not found")

    comments_result = await db.execute(
        select(Comment)
        .options(selectinload(Comment.author))
        .where(Comment.issue_id == issue_id)
        .order_by(Comment.created_at.asc())
    )
    comments = comments_result.scalars().all()

    if not comments:
        return SummaryResponse(summary="No updates yet on this topic.", comment_count=0)

    comment_data = [
        {"author": c.author.display_name if c.author else "Unknown", "body": c.body}
        for c in comments
    ]

    summary = await summarize_thread(issue.title, issue.description, comment_data)
    if not summary:
        raise HTTPException(status_code=500, detail="Summary generation failed")

    return SummaryResponse(summary=summary, comment_count=len(comments))


@router.get("/tones")
async def list_tones(user: User = Depends(get_current_user)):
    """List available tone options."""
    return {
        "tones": [
            {"key": "softer", "label": "Softer", "icon": "🕊️"},
            {"key": "stronger", "label": "Stronger", "icon": "💪"},
            {"key": "neutral", "label": "Neutral", "icon": "⚖️"},
            {"key": "professional", "label": "Professional", "icon": "📋"},
            {"key": "longer", "label": "Longer", "icon": "📝"},
            {"key": "shorter", "label": "Shorter", "icon": "✂️"},
            {"key": "more_detailed", "label": "More Detail", "icon": "🔍"},
            {"key": "less_detailed", "label": "Less Detail", "icon": "📌"},
        ]
    }
