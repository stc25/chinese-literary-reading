"""Sign-in, sign-out and reviewer mode (ported from the Flask app/auth.py)."""
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
    return redirect("auth.signed_out")


def signed_out(request):
    return render(request, "signed_out.html")


def signin_error(request):
    return render(request, "signin_error.html", {"reason": FAILED}, status=400)


@require_POST
def toggle_reviewer_mode(request):
    user = getattr(request, "user_info", None)
    if not (user and user.get("reviewer")):
        raise Http404
    request.session["review_mode"] = request.POST.get("on") == "1"
    return redirect(safe_next(request.POST.get("next")))
