"""Flask app for the course "Reading Modern Literary Chinese".

Run in development with:

    flask --app app run --debug
"""
from __future__ import annotations

import json
import logging
import secrets
import threading
from datetime import datetime, timedelta
from pathlib import Path

from flask import Flask, g, request

from .content import ContentError, content_signature, load
from .content.render import render, render_inline

REPO = Path(__file__).resolve().parent.parent


class CourseStore:
    """Holds the loaded course; reloads it when content files change (development)."""

    def __init__(self, root: Path, reload: bool):
        self.root = root
        self.reload = reload
        self._lock = threading.Lock()
        self.course = load(root)          # raises ContentError if the content is invalid
        self.signature = content_signature(root) if reload else None
        self.error: ContentError | None = None

    def current(self):
        if self.reload:
            sig = content_signature(self.root)
            if sig != self.signature:
                with self._lock:
                    if sig != self.signature:
                        self.signature = sig
                        try:
                            self.course = load(self.root)
                            self.error = None
                        except ContentError as e:
                            self.error = e    # keep serving the last good version, but show the errors
        return self.course


ENV_FILE = Path(__file__).resolve().parent / ".env"
ENV_ALIASES = {"Ollama_API": "OLLAMA_API_KEY", "OLLAMA_API_KEY": "OLLAMA_API_KEY"}


def read_env_file(path: Path) -> dict:
    """Settings from a local .env file (development): MLC_NAME=value lines, as in the environment.

    `Ollama_API` and `OLLAMA_API_KEY` are also accepted for the API key. Values are parsed as
    JSON where possible (true, 40, ["a"]), like Flask's from_prefixed_env. A missing file is
    no error. The file is ignored by git and must never be committed.
    """
    out = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = (x.strip() for x in line.split("=", 1))
        if key.startswith("export "):
            key = key[7:].strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key in ENV_ALIASES:
            out[ENV_ALIASES[key]] = value
        elif key.startswith("MLC_"):
            try:
                out[key[4:]] = json.loads(value)
            except ValueError:
                out[key[4:]] = value
    return out


def setup_logging(app: Flask) -> None:
    """Warnings and errors from the app's modules (model service failures, sign-in problems)
    go to standard error, which Gunicorn and systemd collect. Learners' texts are never logged."""
    logger = logging.getLogger("app")
    if app.testing:
        logger.setLevel(logging.CRITICAL)
        return
    if not logger.handlers:
        h = logging.StreamHandler()
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        logger.addHandler(h)
        logger.setLevel(logging.INFO)
        logger.propagate = False


def create_app(config: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config.update(
        CONTENT_DIR=REPO / "content",
        RELOAD_CONTENT=None,       # None: reload when debug is on
        SHOW_UNREVIEWED=True,      # False at release: hide pages below `reviewed` (reviewers still see them)
        AUTH_MODE=None,            # "oidc" or "none"; None: "none" in debug and testing, otherwise "oidc"
        OIDC_METADATA_URL="",
        OIDC_CLIENT_ID="",
        OIDC_CLIENT_SECRET="",
        ALLOWED_DOMAINS=["cam.ac.uk"],
        REVIEWERS=[],
        DEV_USER="dev",
        TRUST_PROXY=0,
        ACCESSIBILITY_CONTACT="",
        ASSISTANT_ENABLED=True,
        ASSISTANT_MAX_CHARS=600,
        ASSISTANT_MODEL="qwen3.5:9b",
        ASSISTANT_TIMEOUT=60,          # seconds for one model call
        ASSISTANT_STEP_DEADLINE=90,    # seconds for a whole step (the words step may make several calls)
        ASSISTANT_MAX_CONCURRENT=6,    # model calls at once, for everyone together
        ASSISTANT_QUEUE_WAIT=20,       # seconds a request waits for a free slot before "busy"
        ASSISTANT_DAILY_LIMIT=40,     # AI calls per user per day (one full analysis is 5, each question 1)
        ASSISTANT_HOURLY_LIMIT=150,   # AI calls per hour for everyone together
        OLLAMA_HOST="http://localhost:11434",   # the cloud service: https://ollama.com
        OLLAMA_API_KEY="",                      # cloud only; kept on the server
        MAX_CONTENT_LENGTH=256 * 1024,   # request bodies (pasted texts are at most a few KB)
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_HTTPONLY=True,
        PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
    )
    env_file = (config or {}).get("ENV_FILE", None if (config or {}).get("TESTING") else ENV_FILE)
    if env_file:
        app.config.update(read_env_file(Path(env_file)))
    app.config.from_prefixed_env("MLC")       # the real environment wins over the file
    if config:
        app.config.update(config)
    setup_logging(app)
    if app.config["AUTH_MODE"] is None:
        app.config["AUTH_MODE"] = "none" if (app.debug or app.testing) else "oidc"
    if app.config["AUTH_MODE"] == "none" and not app.config.get("SECRET_KEY"):
        app.config["SECRET_KEY"] = secrets.token_hex(32)   # development only: sessions end when the app restarts
    if app.config["AUTH_MODE"] == "oidc":
        app.config["SESSION_COOKIE_SECURE"] = True
    if app.config["TRUST_PROXY"]:
        from werkzeug.middleware.proxy_fix import ProxyFix
        n = int(app.config["TRUST_PROXY"])
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=n, x_proto=n, x_host=n)

    reload = app.config["RELOAD_CONTENT"]
    if reload is None:
        reload = app.debug
    store = CourseStore(Path(app.config["CONTENT_DIR"]), bool(reload))
    app.extensions["course_store"] = store

    @app.before_request
    def attach_course():
        g.course = store.current()
        g.content_error = store.error

    @app.context_processor
    def helpers():
        course = g.get("course") or store.course

        def md(text, page=None):
            return render(text, page.path if page is not None else None, course.urls)

        def md_inline(text, page=None):
            return render_inline(text, page.path if page is not None else None, course.urls)

        return dict(current_year=datetime.now().year, course=course, md=md, md_inline=md_inline, content_error=g.get("content_error"))

    app.jinja_env.filters["first_index"] = lambda occ_id: int(occ_id.split("-")[0])

    def passage_progress_item(pid):
        course = g.get("course") or store.course
        p = course.passages.get(pid)
        return [pid, len(p.exercises) if p else 0]

    app.jinja_env.filters["passage_progress_item"] = passage_progress_item

    from . import assistant, auth, flask_views as views   # Task 9 removes the Flask app
    auth.init_app(app)
    app.register_blueprint(views.bp)
    app.register_blueprint(assistant.bp)

    @app.after_request
    def security_headers(resp):
        # The pages load no third-party scripts, styles or fonts, and contain no inline scripts.
        resp.headers.setdefault("Content-Security-Policy",
                                "default-src 'self'; img-src 'self' data:; object-src 'none'; "
                                "base-uri 'self'; form-action 'self'; frame-ancestors 'none'")
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        resp.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if app.config["AUTH_MODE"] == "oidc":
            resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
        if request.path.startswith("/static/"):
            resp.cache_control.public = True
        else:
            resp.cache_control.private = True   # pages may show reviewer notes or the user's name
            resp.cache_control.no_cache = True
        return resp

    @app.route("/healthz", endpoint="health")
    def health():
        return {"status": "ok"}

    return app


__all__ = ["create_app", "ContentError"]
