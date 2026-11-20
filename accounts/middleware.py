"""The sign-in gate and the sign-in error page."""
from __future__ import annotations

import logging
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.contrib.auth import BACKEND_SESSION_KEY, logout
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from social_core.exceptions import SocialAuthBaseException

from .decorators import is_reviewer
from .pipeline import SESSION_IDENTIFIER, AuthForbidden, identity_of, is_allowed

log = logging.getLogger("accounts")

# Paths that do not need sign-in. The course map at "/" shows the landing page to a visitor who is
# not signed in. The admin has its own password login (superusers created with createsuperuser).
OPEN_PATHS = {"/", "/welcome", "/login", "/logout", "/signed-out", "/signin-error", "/healthz", "/accessibility"}
OPEN_PREFIXES = ("/auth/", "/static/", "/django-admin/")
API_PATHS = {"/summaries.json"}
API_PREFIXES = ("/assistant/api/",)
PASSWORD_BACKEND = "accounts.backends.EmailBackend"

REFUSED = "This course is open to members of the University of Cambridge only."
FAILED = "The sign-in could not be completed."


def is_open(path: str) -> bool:
    return path in OPEN_PATHS or path.startswith(OPEN_PREFIXES)


def is_api(path: str) -> bool:
    return path in API_PATHS or path.startswith(API_PREFIXES)


def signed_in_user(request) -> dict | None:
    """user_info for a valid SSO sign-in, re-checked against the allowlist on every request."""
    user = request.user
    if not user.is_authenticated:
        return None
    identifier = request.session.get(SESSION_IDENTIFIER)
    if user.is_active and identifier and is_allowed(identifier):
        uid = identity_of(identifier)    # the CRSid for a Cambridge address, else the whole address
        return {"id": uid, "name": user.first_name or uid, "reviewer": is_reviewer(uid)}
    return None


class RequireSignInMiddleware:
    """Sets request.user_info ({"id", "name", "reviewer"} or None) and keeps visitors who are not
    signed in to the open pages: pages redirect to /login?next=<path>, API calls get a 401 JSON."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if settings.AUTH_MODE == "none":
            uid = getattr(settings, "DEV_USER", "dev") or "dev"
            request.user_info = {"id": uid, "name": f"{uid} (development)", "reviewer": is_reviewer(uid)}
            return self.get_response(request)

        path = request.path_info
        request.user_info = signed_in_user(request)
        if request.user_info is None and request.user.is_authenticated:
            in_admin = path.startswith("/django-admin/")
            if not (in_admin and request.session.get(BACKEND_SESSION_KEY) == PASSWORD_BACKEND):
                # Removed from the allowlist, deactivated, or a password sign-in outside the admin.
                logout(request)
        if request.user_info is None and not is_open(path):
            if is_api(path):
                return JsonResponse({"error": "sign-in required"}, status=401)
            return redirect(reverse("auth.login") + "?" + urlencode({"next": request.get_full_path()}, safe="/"))
        return self.get_response(request)


class SignInErrorMiddleware:
    """A failed or refused sign-in (a social-auth error, or the network failing on the way to
    Microsoft) shows the sign-in error page. Logs only the kind of failure: those messages can carry
    codes or tokens. Anything else is a bug: it propagates as a 500 and Django logs the traceback."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_exception(self, request, exception):
        network = isinstance(exception, requests.RequestException) and request.path_info.startswith("/auth/sso/")
        if not (isinstance(exception, SocialAuthBaseException) or network):
            return None
        log.warning("sign-in failed: %s", type(exception).__name__)
        if isinstance(exception, AuthForbidden):
            return render(request, "signin_error.html", {"reason": REFUSED}, status=403)
        return render(request, "signin_error.html", {"reason": FAILED}, status=400)
