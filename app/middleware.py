from __future__ import annotations

from django.apps import apps
from django.conf import settings
from django.urls import Resolver404, resolve
from django.utils.cache import patch_cache_control

from .context import current_course_var

CSP = ("default-src 'self'; img-src 'self' data:; object-src 'none'; "
       "base-uri 'self'; form-action 'self'; frame-ancestors 'none'")


class SecurityHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        resp = self.get_response(request)
        # The pages load no third-party scripts, styles or fonts, and contain no inline scripts.
        resp.headers.setdefault("Content-Security-Policy", CSP)
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        resp.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if settings.AUTH_MODE == "oidc":
            resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
        if request.path.startswith("/static/"):
            patch_cache_control(resp, public=True)
        else:
            patch_cache_control(resp, private=True, no_cache=True)   # pages may show reviewer notes or the user's name
        return resp


class CourseMiddleware:
    """Attaches the current course (reloaded in development) and what Flask's request offered."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        store = apps.get_app_config("app").course_store
        request.course = store.current()
        request.content_error = store.error
        try:
            request.endpoint = resolve(request.path_info).view_name
        except Resolver404:
            request.endpoint = None
        request.full_path = request.get_full_path()
        token = current_course_var.set(request.course)
        try:
            return self.get_response(request)
        finally:
            current_course_var.reset(token)
