"""Sign-in, sign-out and reviewer mode ."""
from __future__ import annotations

from django.conf import settings
from django.contrib.auth import logout
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from social_django.utils import load_backend, load_strategy

from .decorators import safe_next
from .middleware import FAILED

BACKEND = "azuread-tenant-oauth2"


@never_cache
def login(request):
    """Start the University sign-in (a GET, as the landing page's link). Remembers where to go back to."""
    nxt = safe_next(request.GET.get("next"))
    if settings.AUTH_MODE == "none":
        return redirect(nxt)
    logout(request)    # a fresh session: the state and PKCE verifier below belong to this attempt only
    strategy = load_strategy(request)
    backend = load_backend(strategy, BACKEND, redirect_uri=reverse("social:complete", args=(BACKEND,)))
    strategy.session_set("next", nxt)
    backend.prepare_auth(user=None)
    return backend.start()


@require_POST
def logout_view(request):
    logout(request)
    return redirect("pages.course_map")      # the home page, which shows the welcome page to a signed-out visitor


def signin_error(request):
    return render(request, "signin_error.html", {"reason": FAILED}, status=400)


@require_POST
def toggle_reviewer_mode(request):
    user = getattr(request, "user_info", None)
    if not (user and user.get("reviewer")):
        raise Http404
    request.session["review_mode"] = request.POST.get("on") == "1"
    return redirect(safe_next(request.POST.get("next")))


def admin_landing(request):
    """/django-admin/: the admin index for signed-in staff, otherwise a landing page that leads to the
    admin's own username-and-password login (the Cambridge sign-in does not open the admin)."""
    from django.contrib import admin
    from django.shortcuts import render
    from django.urls import reverse

    user = request.user
    if user.is_active and user.is_staff:
        return admin.site.admin_view(admin.site.index)(request)
    return render(request, "admin_landing.html", {
        "landing": True,
        "admin_login_url": reverse("admin:login") + "?next=" + reverse("admin:index"),
    })
