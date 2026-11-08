"""Flask app for the course "Reading Modern Literary Chinese".

Run in development with:

    flask --app app run --debug
"""
from __future__ import annotations

import secrets
import threading
from datetime import timedelta
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
        ACCESSIBILITY_CONTACT="",  # e-mail address for accessibility problems, shown on /accessibility             # number of reverse proxies in front of the app (sets the https scheme)
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_HTTPONLY=True,
        PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
    )
    app.config.from_prefixed_env("MLC")
    if config:
        app.config.update(config)
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

        return dict(course=course, md=md, md_inline=md_inline, content_error=g.get("content_error"))

    app.jinja_env.filters["first_index"] = lambda occ_id: int(occ_id.split("-")[0])

    def passage_progress_item(pid):
        course = g.get("course") or store.course
        p = course.passages.get(pid)
        return [pid, len(p.exercises) if p else 0]

    app.jinja_env.filters["passage_progress_item"] = passage_progress_item

    from . import auth, views
    auth.init_app(app)
    app.register_blueprint(views.bp)

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
