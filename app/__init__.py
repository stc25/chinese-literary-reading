"""Flask app for the course "Reading Modern Literary Chinese".

Run in development with:

    flask --app app run --debug
"""
from __future__ import annotations

import threading
from pathlib import Path

from flask import Flask, g

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
        SHOW_UNREVIEWED=True,      # False at release: hide pages below `reviewed`
    )
    app.config.from_prefixed_env("MLC")
    if config:
        app.config.update(config)

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

    from . import views
    app.register_blueprint(views.bp)
    return app


__all__ = ["create_app", "ContentError"]
