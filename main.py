"""Co-Parenting Board."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from config import CF_TEAM_DOMAIN, HOST, PORT
from database import get_db, init_db
from auth import get_optional_user
from scheduler import start_scheduler, stop_scheduler
from sqlalchemy.ext.asyncio import AsyncSession

_BASE_DIR = Path(__file__).parent

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title="Ace's Co-Parenting Board", lifespan=lifespan)

templates = Jinja2Templates(directory=str(_BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(_BASE_DIR / "static")), name="static")

# API routers
from routes_auth import router as auth_router
from routes_issues import router as issues_router
from routes_comments import router as comments_router
from routes_sync import router as sync_router
from routes_invite import router as invite_router
from routes_notifications import router as notifications_router
from routes_ai_rewrite import router as ai_rewrite_router

app.include_router(auth_router)
app.include_router(issues_router)
app.include_router(comments_router)
app.include_router(sync_router)
app.include_router(invite_router)
app.include_router(notifications_router)
app.include_router(ai_rewrite_router)


# ── Health check ──────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "service": "coparent-board"}


# ── HTML pages ────────────────────────────────────────────────────────────────

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_optional_user(request, db)
    if user:
        return RedirectResponse(url="/topics")
    return templates.TemplateResponse("login.html", {
        "request": request,
        "cf_team_domain": CF_TEAM_DOMAIN,
    })


@app.get("/", response_class=HTMLResponse)
async def index(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_optional_user(request, db)
    if not user:
        return RedirectResponse(url="/login")
    return RedirectResponse(url="/topics")


@app.get("/topics", response_class=HTMLResponse)
async def topics_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_optional_user(request, db)
    if not user:
        return RedirectResponse(url="/login")
    return templates.TemplateResponse("issues.html", {
        "request": request,
        "user": user,
    })


@app.get("/topics/{issue_id}", response_class=HTMLResponse)
async def topic_detail_page(request: Request, issue_id: str, db: AsyncSession = Depends(get_db)):
    user = await get_optional_user(request, db)
    if not user:
        return RedirectResponse(url="/login")
    return templates.TemplateResponse("issue_detail.html", {
        "request": request,
        "user": user,
        "issue_id": issue_id,
    })


if __name__ == "__main__":
    uvicorn.run("main:app", host=HOST, port=PORT, reload=True)
