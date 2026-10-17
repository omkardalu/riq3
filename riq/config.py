"""Application configuration, driven by environment variables.

Nothing secret lives in the repository: copy `.env.example` to `.env` for local work.
"""
from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

_DEV_SECRET = "dev-only-insecure-secret-change-me"


def _normalize_db_url(url: str) -> str:
    """Accept postgres:// and postgresql:// (Heroku/Render style) and use the psycopg 3 driver."""
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    return default if raw is None else raw.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    return default if raw in (None, "") else int(raw)


class Config:
    ENV_NAME = "base"
    DEBUG = False
    TESTING = False

    SECRET_KEY = os.environ.get("SECRET_KEY", _DEV_SECRET)
    SQLALCHEMY_DATABASE_URI = _normalize_db_url(
        os.environ.get("DATABASE_URL", "postgresql://riq:riq@localhost:5432/riq")
    )
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    # --- sessions / cookies
    SESSION_COOKIE_NAME = "riq_session"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _bool("SESSION_COOKIE_SECURE", False)
    PERMANENT_SESSION_LIFETIME = timedelta(hours=_int("SESSION_LIFETIME_HOURS", 24 * 7))

    # --- CSRF
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = None  # token lives as long as the session
    WTF_CSRF_HEADERS = ["X-CSRFToken"]

    # --- uploads (all limits are enforced server-side)
    UPLOAD_FOLDER = os.environ.get("UPLOAD_FOLDER", str(BASE_DIR / "instance" / "uploads"))
    MAX_RESUME_BYTES = _int("MAX_RESUME_BYTES", 5 * 1024 * 1024)  # per file
    USER_STORAGE_QUOTA_BYTES = _int("USER_STORAGE_QUOTA_BYTES", 500 * 1024 * 1024)  # per account
    MAX_CONTENT_LENGTH = MAX_RESUME_BYTES + 512 * 1024  # request cap = file + form overhead
    ALLOWED_RESUME_EXTENSIONS = ("pdf", "docx")

    # --- job input limits
    MAX_REQUIRED_SKILLS = 100
    MAX_SKILL_LENGTH = 60
    MAX_JOB_DESCRIPTION_CHARS = 20000

    # --- rate limiting (set RATELIMIT_STORAGE_URI=redis://... when running several workers)
    RATELIMIT_ENABLED = _bool("RATELIMIT_ENABLED", True)
    RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")
    RATELIMIT_HEADERS_ENABLED = True
    LOGIN_RATE_LIMIT = os.environ.get("LOGIN_RATE_LIMIT", "10 per minute")
    REGISTER_RATE_LIMIT = os.environ.get("REGISTER_RATE_LIMIT", "10 per hour")

    TRUST_PROXY = _bool("TRUST_PROXY", False)
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")

    @classmethod
    def validate(cls) -> None:  # overridden in production
        pass


class DevelopmentConfig(Config):
    ENV_NAME = "development"
    DEBUG = True


class TestingConfig(Config):
    ENV_NAME = "testing"
    TESTING = True
    SECRET_KEY = "test-secret"
    SQLALCHEMY_DATABASE_URI = _normalize_db_url(
        os.environ.get("TEST_DATABASE_URL", "postgresql://riq:riq@localhost:5432/riq_test")
    )
    WTF_CSRF_ENABLED = False
    RATELIMIT_ENABLED = False
    UPLOAD_FOLDER = str(BASE_DIR / "instance" / "test-uploads")
    LOG_LEVEL = "WARNING"


class ProductionConfig(Config):
    ENV_NAME = "production"
    SESSION_COOKIE_SECURE = _bool("SESSION_COOKIE_SECURE", True)

    @classmethod
    def validate(cls) -> None:
        problems = []
        if cls.SECRET_KEY == _DEV_SECRET or len(cls.SECRET_KEY) < 32:
            problems.append("SECRET_KEY must be set to a random value of at least 32 characters")
        if "DATABASE_URL" not in os.environ:
            problems.append("DATABASE_URL must be set")
        if not cls.SESSION_COOKIE_SECURE:
            problems.append("SESSION_COOKIE_SECURE must be true in production (serve over HTTPS)")
        if problems:
            raise RuntimeError("Invalid production configuration: " + "; ".join(problems))


CONFIGS = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def get_config(name: str | None = None) -> type[Config]:
    return CONFIGS[name or os.environ.get("APP_ENV", "development")]
