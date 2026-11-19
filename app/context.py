"""Template context for the Jinja2 backend (Flask's context processors, ported)."""
from __future__ import annotations

from datetime import datetime

from django.apps import apps
from django.conf import settings
from django.middleware.csrf import get_token

from .content.render import render, render_inline


def current_course(request):
    """The course for this request: set by CourseMiddleware, else the app's store, else None."""
    course = getattr(request, "course", None)
    if course is None:
        store = getattr(apps.get_app_config("app"), "course_store", None)
        course = store.course if store is not None else None
    return course


def template_context(request) -> dict:
    course = current_course(request)
    user = getattr(request, "user_info", None)
    session = getattr(request, "session", None)
    reviewer_mode = bool(user and user.get("reviewer") and session is not None and session.get("review_mode"))

    def md(text, page=None):
        return render(text, page.path if page is not None else None, course.urls)

    def md_inline(text, page=None):
        return render_inline(text, page.path if page is not None else None, course.urls)

    return dict(
        course=course,
        md=md,
        md_inline=md_inline,
        current_year=datetime.now().year,
        current_user=user,
        reviewer_mode=reviewer_mode,
        auth_mode=settings.AUTH_MODE,
        config=settings,
        request=request,
        content_error=getattr(request, "content_error", None),
        csrf_token=lambda: get_token(request),
    )
