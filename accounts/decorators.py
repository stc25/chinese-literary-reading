"""Small helpers shared by the sign-in views and the course pages."""
from __future__ import annotations

from functools import wraps
from urllib.parse import urlparse

from django.conf import settings
from django.http import Http404
from django.urls import reverse


def is_reviewer(uid: str | None) -> bool:
    if not uid:
        return False
    return uid.lower() in {str(r).lower() for r in getattr(settings, "REVIEWERS", [])}


def safe_next(url: str | None) -> str:
    """Only allow redirects back to a path on this site."""
    if not url:
        return reverse("pages.course_map")
    parts = urlparse(url)
    if parts.scheme or parts.netloc or not url.startswith("/") or url.startswith("//"):
        return reverse("pages.course_map")
    # Not in the Flask original: browsers read a backslash as a slash ("/\evil.com" is "//evil.com"),
    # and control characters have no place in a path.
    if "\\" in url or any(ord(c) < 32 or ord(c) == 127 for c in url):
        return reverse("pages.course_map")
    return url


def reviewer_required(view):
    """404 unless the signed-in user is a reviewer."""
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        user = getattr(request, "user_info", None)
        if not (user and user.get("reviewer")):
            raise Http404
        return view(request, *args, **kwargs)
    return wrapped
