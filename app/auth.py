"""Sign-in through Cambridge University SSO (Microsoft Entra ID, OpenID Connect).

Nothing about the user is stored on the server: after sign-in the user's id,
name and reviewer flag are kept in Flask's signed session cookie.

Settings (environment variables are prefixed MLC_, e.g. MLC_AUTH_MODE):

    AUTH_MODE            "oidc" (sign-in required) or "none" (development: no sign-in)
    OIDC_METADATA_URL    the provider's discovery document, e.g.
                         https://login.microsoftonline.com/<tenant-id>/v2.0/.well-known/openid-configuration
    OIDC_CLIENT_ID       the app registration's client id
    OIDC_CLIENT_SECRET   its client secret
    ALLOWED_DOMAINS      e.g. ["cam.ac.uk"]; accounts outside these domains are refused
    REVIEWERS            user ids (CRSids) who may use reviewer mode, e.g. ["cz201"]
    DEV_USER             in "none" mode, the user id to act as (default "dev")
    SECRET_KEY           signs the session cookie; required in "oidc" mode
"""
from __future__ import annotations

import secrets
from functools import wraps
from urllib.parse import urlparse

from flask import Blueprint, abort, current_app, redirect, render_template, request, session, url_for

bp = Blueprint("auth", __name__)

# Pages that do not need sign-in
OPEN_ENDPOINTS = {"auth.login", "auth.callback", "auth.logout", "auth.signed_out", "static", "health"}


def user_id_from_claims(claims: dict) -> str:
    """The CRSid (or other account name) from the ID token: the part of the address before @."""
    name = claims.get("preferred_username") or claims.get("upn") or claims.get("email") or claims.get("sub", "")
    return str(name).split("@")[0].lower()


def domain_of(claims: dict) -> str:
    name = claims.get("preferred_username") or claims.get("upn") or claims.get("email") or ""
    return str(name).rpartition("@")[2].lower()


def is_reviewer(uid: str | None) -> bool:
    if not uid:
        return False
    return uid.lower() in {r.lower() for r in current_app.config.get("REVIEWERS", [])}


def current_user() -> dict | None:
    if current_app.config["AUTH_MODE"] == "none":
        uid = current_app.config.get("DEV_USER", "dev")
        return {"id": uid, "name": f"{uid} (development)", "reviewer": is_reviewer(uid)}
    return session.get("user")


def reviewer_mode() -> bool:
    """True when the current user is a reviewer and has reviewer mode switched on."""
    user = current_user()
    return bool(user and user.get("reviewer") and session.get("review_mode"))


def reviewer_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = current_user()
        if not (user and user.get("reviewer")):
            abort(404)
        return view(*args, **kwargs)
    return wrapped


def safe_next(url: str | None) -> str:
    """Only allow redirects back to a path on this site."""
    if not url:
        return url_for("pages.course_map")
    parts = urlparse(url)
    if parts.scheme or parts.netloc or not url.startswith("/") or url.startswith("//"):
        return url_for("pages.course_map")
    return url


def csrf_token() -> str:
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(16)
    return session["csrf"]


def check_csrf() -> None:
    expected = session.get("csrf")
    if not expected or not secrets.compare_digest(request.form.get("csrf", ""), expected):
        abort(400)


def init_app(app) -> None:
    mode = app.config["AUTH_MODE"]
    if mode not in ("oidc", "none"):
        raise RuntimeError(f"AUTH_MODE must be 'oidc' or 'none', not {mode!r}")
    if mode == "oidc":
        missing = [k for k in ("OIDC_METADATA_URL", "OIDC_CLIENT_ID", "OIDC_CLIENT_SECRET") if not app.config.get(k)]
        if missing:
            raise RuntimeError("AUTH_MODE is 'oidc' but these settings are missing: " + ", ".join(missing))
        if not app.config.get("SECRET_KEY") or app.config["SECRET_KEY"] == "dev":
            raise RuntimeError("Set a long random SECRET_KEY (MLC_SECRET_KEY) for sign-in")
        from authlib.integrations.flask_client import OAuth

        oauth = OAuth(app)
        oauth.register(
            "sso",
            server_metadata_url=app.config["OIDC_METADATA_URL"],
            client_id=app.config["OIDC_CLIENT_ID"],
            client_secret=app.config["OIDC_CLIENT_SECRET"],
            client_kwargs={"scope": "openid profile email", "code_challenge_method": "S256"},
        )
        app.extensions["oauth_sso"] = oauth.sso

    @app.before_request
    def require_sign_in():
        if app.config["AUTH_MODE"] == "none" or request.endpoint in OPEN_ENDPOINTS:
            return None
        if session.get("user") is None:
            return redirect(url_for("auth.login", next=request.full_path.rstrip("?")))
        return None

    @app.context_processor
    def auth_context():
        return dict(current_user=current_user(), reviewer_mode=reviewer_mode(), csrf_token=csrf_token,
                    auth_mode=app.config["AUTH_MODE"])

    app.register_blueprint(bp)


@bp.route("/login")
def login():
    if current_app.config["AUTH_MODE"] == "none":
        return redirect(safe_next(request.args.get("next")))
    session["next"] = safe_next(request.args.get("next"))
    client = current_app.extensions["oauth_sso"]
    return client.authorize_redirect(url_for("auth.callback", _external=True))


@bp.route("/auth/callback")
def callback():
    if current_app.config["AUTH_MODE"] == "none":
        return redirect(url_for("pages.course_map"))
    client = current_app.extensions["oauth_sso"]
    try:
        token = client.authorize_access_token()   # checks state, nonce and the ID token signature
    except Exception:  # noqa: BLE001 - any failure of the exchange means no sign-in
        current_app.logger.warning("sign-in failed", exc_info=True)
        return render_template("signin_error.html", reason="The sign-in could not be completed."), 400
    claims = token.get("userinfo") or {}
    allowed = [d.lower() for d in current_app.config.get("ALLOWED_DOMAINS", [])]
    if allowed and domain_of(claims) not in allowed:
        return render_template("signin_error.html",
                               reason="This course is open to members of the University of Cambridge only."), 403
    uid = user_id_from_claims(claims)
    nxt = session.pop("next", None)
    session.clear()
    session.permanent = True
    session["user"] = {"id": uid, "name": claims.get("name") or uid, "reviewer": is_reviewer(uid)}
    return redirect(safe_next(nxt))


@bp.route("/logout", methods=["POST"])
def logout():
    check_csrf()
    session.clear()
    return redirect(url_for("auth.signed_out"))


@bp.route("/signed-out")
def signed_out():
    return render_template("signed_out.html")


@bp.route("/reviewer-mode", methods=["POST"])
def toggle_reviewer_mode():
    check_csrf()
    user = current_user()
    if not (user and user.get("reviewer")):
        abort(404)
    session["review_mode"] = request.form.get("on") == "1"
    return redirect(safe_next(request.form.get("next")))
