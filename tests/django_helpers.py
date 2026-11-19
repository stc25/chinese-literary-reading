"""Shared set-up for the Django page tests."""
import os
from pathlib import Path

os.environ.setdefault("MLC_TESTING", "1")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()   # a no-op under `manage.py test`; needed under `unittest discover`

from django.apps import apps
from django.test import override_settings

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "valid"
CONTENT = ROOT / "content"


def page_settings(content=FIXTURE, **extra):
    """override_settings for a page test: the given content, no sign-in, unless overridden."""
    return override_settings(**{"CONTENT_DIR": str(content), "AUTH_MODE": "none", **extra})


def current_course():
    return apps.get_app_config("app").course_store.course


# --- Test database for modules that also run under plain `unittest discover` ---

def start_test_database():
    """`manage.py test` has already built the test database; plain `unittest discover` has not.
    Returns a handle for stop_test_database (None when there was nothing to do)."""
    from django.db import connection
    from django.test.runner import DiscoverRunner
    name = str(connection.settings_dict["NAME"])
    if "memorydb" in name or name == ":memory:":
        return None
    runner = DiscoverRunner(verbosity=0, interactive=False)
    runner.setup_test_environment()
    return runner, runner.setup_databases()


def stop_test_database(handle):
    if handle is not None:
        runner, old_config = handle
        runner.teardown_databases(old_config)
        runner.teardown_test_environment()


# --- Sign-in through the SSO flow, with Microsoft replaced by a stub (no network) ---

BACKEND = "azuread-tenant-oauth2"
COMPLETE = f"/auth/sso/complete/{BACKEND}/"
TENANT = "00000000-0000-0000-0000-000000000001"
OIDC = {
    "AUTH_MODE": "oidc",
    "SOCIAL_AUTH_AZUREAD_TENANT_OAUTH2_KEY": "test-client-id",
    "SOCIAL_AUTH_AZUREAD_TENANT_OAUTH2_SECRET": "test-client-secret",
    "SOCIAL_AUTH_AZUREAD_TENANT_OAUTH2_TENANT_ID": TENANT,
    "SESSION_COOKIE_SECURE": True,     # what build_settings sets in oidc mode
    "CSRF_COOKIE_SECURE": True,
}


def oidc_settings(**extra):
    return override_settings(**{**OIDC, **extra})


def claims_for(username="cz201@cam.ac.uk", name="C. Z.", v1=False, **extra):
    """ID-token claims. v1=True: the shape of a v1.0 token (`upn` and `unique_name`, no `preferred_username`)."""
    sub = "opaque-" + username.replace("@", "-at-")
    if v1:
        return {"upn": username, "unique_name": username, "name": name, "sub": sub, "tid": TENANT, **extra}
    return {"preferred_username": username, "name": name, "sub": sub, "tid": TENANT, **extra}


def no_network():
    """Fail loudly if anything tries to reach the identity provider."""
    from contextlib import ExitStack
    from unittest import mock

    def refuse(*args, **kwargs):
        raise AssertionError("a test tried to make a network call")

    stack = ExitStack()
    stack.enter_context(mock.patch("social_core.backends.base.BaseAuth.request", refuse))
    stack.enter_context(mock.patch("requests.sessions.Session.request", refuse))
    return stack


def sso_sign_in(client, claims=None, next=None, exchange_error=None, state=None):
    """The real flow: GET /login (state and PKCE verifier go into the session cookie), then the
    completion URL. Only Microsoft's part is stubbed: the code exchange and the ID-token check."""
    from unittest import mock
    from urllib.parse import parse_qs, urlparse

    from social_core.backends.azuread_tenant import AzureADTenantOAuth2

    claims = claims_for() if claims is None else claims
    with no_network():
        r = client.get("/login", {"next": next} if next is not None else {})
        sent_state = parse_qs(urlparse(r["Location"]).query)["state"][0]
        token = {"access_token": "test-access-token", "id_token": "test-id-token", "token_type": "Bearer"}
        exchange = (mock.patch.object(AzureADTenantOAuth2, "request_access_token", side_effect=exchange_error)
                    if exchange_error else
                    mock.patch.object(AzureADTenantOAuth2, "request_access_token", return_value=token))
        with exchange, mock.patch.object(AzureADTenantOAuth2, "user_data", return_value=dict(claims)):
            return client.get(COMPLETE, {"code": "test-code", "state": state or sent_state})
