"""Django settings, built from defaults, app/.env and MLC_* environment variables.

Order: defaults, then app/.env (not when testing), then the real environment (MLC_NAME,
JSON-parsed where possible), so the real environment wins over the file.
"""
import json
import os
import secrets
import sys
from datetime import timedelta
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

from .envfile import read_env_file

REPO = Path(__file__).resolve().parent.parent
ENV_FILE = REPO / "app" / ".env"
AUTH_MODES = ("oidc", "none")
OIDC_REQUIRED = ("SECRET_KEY", "AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET", "AZURE_TENANT_ID")

DEFAULTS = {
    "CONTENT_DIR": str(REPO / "content"),
    "SHOW_UNREVIEWED": True,     # False at release: hide pages below `reviewed` (reviewers still see them)
    "REVIEWERS": [],
    "DEV_USER": "dev",
    "TRUST_PROXY": 0,
    "ACCESSIBILITY_CONTACT": "",
    "ASSISTANT_ENABLED": True,
    "ASSISTANT_MAX_CHARS": 600,
    "ASSISTANT_MODEL": "qwen3.5:9b",
    "ASSISTANT_TIMEOUT": 60,           # seconds for one model call
    "ASSISTANT_STEP_DEADLINE": 90,     # seconds for a whole step (the words step may make several calls)
    "ASSISTANT_MAX_CONCURRENT": 6,     # model calls at once, for everyone together
    "ASSISTANT_QUEUE_WAIT": 20,        # seconds a request waits for a free slot before "busy"
    "ASSISTANT_DAILY_LIMIT": 40,       # AI calls per user per day (one full analysis is 5, each question 1)
    "ASSISTANT_HOURLY_LIMIT": 150,     # AI calls per hour for everyone together
    "OLLAMA_HOST": "http://localhost:11434",   # the cloud service: https://ollama.com
    "OLLAMA_API_KEY": "",                      # cloud only; kept on the server
    "DB_PATH": str(REPO / "var" / "db.sqlite3"),
}


def build_settings(env: dict, debug: bool, testing: bool) -> dict:
    """Django settings from `env` (unprefixed MLC names). Raises ImproperlyConfigured."""
    values = {**DEFAULTS, **env}
    mode = values.get("AUTH_MODE") or ("none" if (debug or testing) else "oidc")
    if mode not in AUTH_MODES:
        raise ImproperlyConfigured(f"MLC_AUTH_MODE must be one of {AUTH_MODES}, not {mode!r}")
    secret = values.get("SECRET_KEY") or ""
    if mode == "oidc":
        for name in OIDC_REQUIRED:
            if not values.get(name):
                raise ImproperlyConfigured(f"MLC_{name} is required when MLC_AUTH_MODE is oidc")
    elif not secret:
        secret = secrets.token_hex(32)   # development only: sessions end when the app restarts

    s = {k: v for k, v in values.items() if k not in ("SECRET_KEY", "DB_PATH", "AUTH_MODE")}
    s.update(
        DEBUG=debug,
        SECRET_KEY=secret,
        AUTH_MODE=mode,
        AZURE_CLIENT_ID=values.get("AZURE_CLIENT_ID") or "",
        AZURE_CLIENT_SECRET=values.get("AZURE_CLIENT_SECRET") or "",
        AZURE_TENANT_ID=values.get("AZURE_TENANT_ID") or "",
        ALLOWED_HOSTS=["*"],   # the reverse proxy decides the host
        INSTALLED_APPS=[
            "django.contrib.contenttypes",
            "django.contrib.auth",
            "django.contrib.sessions",
            "app.apps.MlcConfig",
        ],
        MIDDLEWARE=[
            "django.contrib.sessions.middleware.SessionMiddleware",
            "django.middleware.csrf.CsrfViewMiddleware",
        ],
        ROOT_URLCONF="config.urls",
        WSGI_APPLICATION="config.wsgi.application",
        DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": values["DB_PATH"]}},
        DEFAULT_AUTO_FIELD="django.db.models.BigAutoField",
        USE_TZ=True,
        SESSION_ENGINE="django.contrib.sessions.backends.signed_cookies",
        SESSION_COOKIE_AGE=int(timedelta(hours=12).total_seconds()),
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SECURE=(mode == "oidc"),
        CSRF_HEADER_NAME="HTTP_X_CSRF_TOKEN",   # the header the existing assistant.js sends
        DATA_UPLOAD_MAX_MEMORY_SIZE=256 * 1024,  # pasted texts are at most a few KB
    )
    return s


def _environment() -> dict:
    out = {}
    for key, value in os.environ.items():
        if key.startswith("MLC_"):
            try:
                out[key[4:]] = json.loads(value)
            except ValueError:
                out[key[4:]] = value
    return out


# `manage.py test`, or plain `python -m unittest` (which imports this module for build_settings)
_TESTING = "test" in sys.argv or "unittest" in sys.modules
_env = {} if _TESTING else read_env_file(ENV_FILE)
_env.update(_environment())
_debug = bool(_env.pop("DEBUG", False))
globals().update(build_settings(_env, debug=_debug, testing=_TESTING))
