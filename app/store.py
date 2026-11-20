"""The loaded course, shared by all requests."""
from __future__ import annotations

import threading
from pathlib import Path

from django.conf import settings

from .content import ContentError, content_signature, load


class CourseStore:
    """Holds the loaded course; reloads it when content files change (development)."""

    def __init__(self, root: Path, reload: bool):
        self.root = root
        self.reload = reload
        self._lock = threading.Lock()
        self.course = load(root, url_prefix=settings.URL_PREFIX)          # raises ContentError if the content is invalid
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
                            self.course = load(self.root, url_prefix=settings.URL_PREFIX)
                            self.error = None
                        except ContentError as e:
                            self.error = e    # keep serving the last good version, but show the errors
        return self.course
