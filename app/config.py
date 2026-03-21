"""Environment configuration for Co-Parenting Board shared portal."""

import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

log = logging.getLogger(__name__)

# Database — SQLite 
_DATA_DIR = Path(__file__).parent / "data"
_DATA_DIR.mkdir(exist_ok=True)
DATABASE_PATH: str = os.getenv("DATABASE_PATH", str(_DATA_DIR / "shared.db"))
DATABASE_URL: str = f"sqlite+aiosqlite:///{DATABASE_PATH}"

SECRET_KEY: str = os.getenv("SECRET_KEY", "")
HOST: str = os.getenv("HOST", "0.0.0.0")
PORT: int = int(os.getenv("PORT", "8443"))

# Custody schedule anchor: a known Friday when Ace's ON week starts
ACE_ON_WEEK_ANCHOR: str = os.getenv("ACE_ON_WEEK_ANCHOR", "2026-03-13")
TIMEZONE: str = os.getenv("TIMEZONE", "America/New_York")

# API key used by Tier 2 (vault) to pull data via sync API
SYNC_API_KEY: str = os.getenv("SYNC_API_KEY", "")

# Cloudflare Access
CF_TEAM_DOMAIN: str = os.getenv("CF_TEAM_DOMAIN", "")  # e.g. "myteam"
CF_AUD: str = os.getenv("CF_AUD", "")  # Application Audience (AUD) tag
CF_POLICY_AUD: str = os.getenv("CF_POLICY_AUD", CF_AUD)  # alias

# Local dev: set to an email to bypass CF Access auth entirely
DEV_USER_EMAIL: str = os.getenv("DEV_USER_EMAIL", "")

# App URL (for links)
APP_URL: str = os.getenv("APP_URL", "")

# Anthropic (AI rewrite)
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
AI_MODEL: str = os.getenv("AI_MODEL", "claude-haiku-4-5-20251001")

# SMTP —  relay for notification emails (not auth)
SMTP_HOST: str = os.getenv("SMTP_HOST", "")
SMTP_PORT: int = int(os.getenv("SMTP_PORT", "25"))
SMTP_FROM: str = os.getenv("SMTP_FROM", "Ace's Board <noreply@example.com>")

# ── Startup validation ──────────────────────────────────────────────────────
_INSECURE_DEFAULTS = {"change-me-in-production", "change-me-sync-key", ""}

if SECRET_KEY in _INSECURE_DEFAULTS:
    if DEV_USER_EMAIL:
        log.warning("SECRET_KEY is not set — running in dev mode (DEV_USER_EMAIL=%s)", DEV_USER_EMAIL)
        SECRET_KEY = "dev-only-insecure-key-do-not-use-in-prod"
    else:
        print("FATAL: SECRET_KEY must be set in .env for production", file=sys.stderr)
        sys.exit(1)

if SYNC_API_KEY in _INSECURE_DEFAULTS and not DEV_USER_EMAIL:
    print("FATAL: SYNC_API_KEY must be set in .env for production", file=sys.stderr)
    sys.exit(1)

if DEV_USER_EMAIL:
    log.warning("DEV_USER_EMAIL is set — CF Access auth is bypassed for %s", DEV_USER_EMAIL)
elif not CF_TEAM_DOMAIN or not CF_AUD:
    print("FATAL: CF_TEAM_DOMAIN and CF_AUD must be set for Cloudflare Access auth", file=sys.stderr)
    sys.exit(1)
