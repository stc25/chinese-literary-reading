"""python-social-auth pipeline steps for University SSO (Microsoft Entra ID).

``enforce_allowlist`` runs right after social-core's ``auth_allowed`` and refuses the sign-in
before any user or social-auth row exists. ``finish_login`` runs last, once a stock
``auth.User`` has been found or created. Only the user name (the CRSid, or the local part of a
non-Cambridge address) and the display name are kept: never the address, never the tokens.
"""
from __future__ import annotations

import re

try:  # social-auth-core 7 renamed AuthForbidden to AuthPolicyError
    from social_core.exceptions import AuthForbidden
except ImportError:  # pragma: no cover - depends on the installed version
    from social_core.exceptions import AuthPolicyError as AuthForbidden

from .decorators import safe_next
from .models import AllowedLogin

CRSID_RE = re.compile(r"^[a-z0-9]+$")
CAM_DOMAIN = "@cam.ac.uk"
IDENTIFIER_CLAIMS = ("preferred_username", "upn", "email")   # never "sub": it is not a person's name
SESSION_IDENTIFIER = "mlc_login"   # the IdP identifier, kept in the signed session cookie for the per-request re-check


def identifier_from_claims(claims: dict) -> str:
    """The account name from the ID token: preferred_username, else upn, else email. "" if none."""
    for key in IDENTIFIER_CLAIMS:
        value = claims.get(key)
        if value:
            return str(value).strip().lower()
    return ""


def well_formed(identifier: str) -> bool:
    """One @, with something on both sides (so every part of the code splits it the same way)."""
    local, _, domain = (identifier or "").partition("@")
    return identifier.count("@") == 1 and bool(local) and bool(domain)


def crsid_of(identifier: str) -> str:
    """The CRSid of a Cambridge address (abc123@cam.ac.uk), or "" for any other identifier."""
    if not (well_formed(identifier) and identifier.endswith(CAM_DOMAIN)):
        return ""
    local = identifier.split("@", 1)[0]
    return local if CRSID_RE.match(local) else ""


def identity_of(identifier: str) -> str:
    """The user's id on this site (reviewer list, assistant limits): the CRSid for a Cambridge
    address, the whole address otherwise, so another domain's `cz201` is never the CRSid cz201."""
    return crsid_of(identifier) or identifier


def is_allowed(identifier: str) -> bool:
    """The allowlist decision, at sign-in and again on every request. A Cambridge address must have
    a CRSid as its local part; any other address can only match an email or a domain entry."""
    if not well_formed(identifier):
        return False
    crsid = crsid_of(identifier)
    if identifier.endswith(CAM_DOMAIN) and not crsid:
        return False
    return AllowedLogin.objects.allows(identifier, crsid)


def enforce_allowlist(backend, details, response, *args, **kwargs):
    if kwargs.get("user") is not None:
        raise AuthForbidden(backend)    # someone already signed in: never link a second identity to them
    identifier = identifier_from_claims(response or {})
    if not is_allowed(identifier):
        raise AuthForbidden(backend)
    username = crsid_of(identifier) or identifier.split("@", 1)[0]    # never the address itself
    name = str((response or {}).get("name") or "").strip() or identity_of(identifier)
    return {
        "details": {"username": username, "email": "", "fullname": name, "first_name": name[:150], "last_name": ""},
        "login_identifier": identifier,
    }


def finish_login(backend, user=None, *args, strategy=None, login_identifier=None, social=None, details=None,
                 **kwargs):
    if user is None:
        return
    if not user.is_active:
        raise AuthForbidden(backend)
    name = str((details or {}).get("first_name") or user.first_name or user.username)[:150]
    user.first_name, user.last_name, user.email = name, "", ""
    fields = ["first_name", "last_name", "email"]
    if user.has_usable_password():
        # Only when it changes: a new unusable password is random, which would change the session
        # hash and end the user's sessions on their other devices.
        user.set_unusable_password()
        fields.append("password")
    user.save(update_fields=fields)
    if social is not None and social.extra_data:
        social.extra_data = {}     # load_extra_data copied the tokens; this site never calls Microsoft again
        social.save(update_fields=["extra_data"])
    if strategy is not None:
        strategy.session_set(SESSION_IDENTIFIER, login_identifier)
        # social:begin also takes ?next= directly; keep only same-site paths.
        strategy.session_set("next", safe_next(strategy.session_get("next")))
