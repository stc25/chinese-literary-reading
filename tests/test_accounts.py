import os
import unittest

os.environ.setdefault("MLC_TESTING", "1")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()   # a no-op under `manage.py test`; needed under `unittest discover`

from tests.django_helpers import (  # noqa: E402  (sets up Django first)
    CONTENT, COMPLETE, FIXTURE, TENANT, claims_for, no_network, oidc_settings, page_settings, sso_sign_in,
    start_test_database, stop_test_database)

import re  # noqa: E402
from urllib.parse import parse_qs, urlparse  # noqa: E402

from django.contrib.auth import get_user_model  # noqa: E402
from django.core.exceptions import ValidationError  # noqa: E402
from django.test import Client, TestCase  # noqa: E402
from social_django.models import UserSocialAuth  # noqa: E402

from accounts.models import AllowedLogin  # noqa: E402

_db = None


def setUpModule():
    global _db
    _db = start_test_database()


def tearDownModule():
    stop_test_database(_db)


def allow(*entries):
    for e in entries:
        AllowedLogin(entry=e).save()


class AllowsTests(TestCase):
    def test_crsid_entry_matches_case_insensitively(self):
        allow("abc123")
        self.assertTrue(AllowedLogin.objects.allows("abc123@cam.ac.uk", "ABC123"))
        self.assertTrue(AllowedLogin.objects.allows("ABC123@CAM.AC.UK", "abc123"))

    def test_crsid_entry_matches_email_local_part_when_crsid_blank(self):
        allow("abc123")
        self.assertTrue(AllowedLogin.objects.allows("abc123@cam.ac.uk", ""))

    def test_given_crsid_overrides_local_part(self):
        allow("abc123")
        self.assertFalse(AllowedLogin.objects.allows("abc123@cam.ac.uk", "zzz"))
        self.assertTrue(AllowedLogin.objects.allows("abc123@cam.ac.uk", ""))
        self.assertTrue(AllowedLogin.objects.allows("other@cam.ac.uk", "abc123"))

    def test_crsid_entry_needs_cam_email(self):
        allow("abc123")
        self.assertFalse(AllowedLogin.objects.allows("abc123@gmail.com", "abc123"))
        self.assertFalse(AllowedLogin.objects.allows("abc123@cam.ac.uk.evil.com", "abc123"))
        self.assertFalse(AllowedLogin.objects.allows("abc123@evilcam.ac.uk", "abc123"))

    def test_crsid_entry_does_not_match_other_crsid(self):
        allow("abc123")
        self.assertFalse(AllowedLogin.objects.allows("xyz9@cam.ac.uk", "xyz9"))

    def test_email_entry_exact_and_case_insensitive(self):
        allow("abc123@cam.ac.uk")
        self.assertTrue(AllowedLogin.objects.allows("abc123@CAM.AC.UK", ""))
        self.assertFalse(AllowedLogin.objects.allows("abc123@gmail.com", "abc123"))
        self.assertFalse(AllowedLogin.objects.allows("xabc123@cam.ac.uk", ""))

    def test_domain_entry_case_insensitive(self):
        allow("@ling.cam.ac.uk")
        self.assertTrue(AllowedLogin.objects.allows("x@Ling.Cam.Ac.Uk", ""))
        self.assertFalse(AllowedLogin.objects.allows("x@cam.ac.uk", ""))

    def test_domain_entry_is_not_suffix_matched(self):
        allow("@cam.ac.uk")
        self.assertTrue(AllowedLogin.objects.allows("x@cam.ac.uk", ""))
        self.assertFalse(AllowedLogin.objects.allows("x@evilcam.ac.uk", ""))
        self.assertFalse(AllowedLogin.objects.allows("x@cam.ac.uk.evil.com", ""))
        self.assertFalse(AllowedLogin.objects.allows("x@sub.cam.ac.uk", ""))

    def test_domain_uses_part_after_last_at(self):
        allow("@cam.ac.uk")
        self.assertFalse(AllowedLogin.objects.allows("x@cam.ac.uk@evil.com", ""))

    def test_empty_inputs_and_empty_list(self):
        self.assertFalse(AllowedLogin.objects.allows("x@cam.ac.uk", "x"))
        allow("abc123")
        self.assertFalse(AllowedLogin.objects.allows("", ""))


class EntryValidationTests(TestCase):
    def test_save_normalises(self):
        AllowedLogin(entry=" ABC123 ").save()
        self.assertEqual(AllowedLogin.objects.get().entry, "abc123")

    def test_clean_normalises(self):
        a = AllowedLogin(entry=" @Ling.CAM.ac.uk ")
        a.full_clean()
        self.assertEqual(a.entry, "@ling.cam.ac.uk")

    def test_invalid_entries_rejected_on_save(self):
        for bad in ("a b", "", "   ", "@", "a@", "a@b@c", "@a@b", "ab-1"):
            with self.subTest(bad=bad), self.assertRaises(ValidationError):
                AllowedLogin(entry=bad).save()
        self.assertEqual(AllowedLogin.objects.count(), 0)

    def test_invalid_entries_rejected_by_full_clean(self):
        for bad in ("a b", ""):
            with self.subTest(bad=bad), self.assertRaises(ValidationError):
                AllowedLogin(entry=bad).full_clean()

    def test_duplicate_after_normalisation_rejected(self):
        AllowedLogin(entry="abc123").save()
        with self.assertRaises(ValidationError):
            AllowedLogin(entry=" ABC123").save()


User = get_user_model()
REFUSED = "This course is open to members of the University of Cambridge only."
FAILED = "The sign-in could not be completed."


def csrf_from(html):
    return re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', html).group(1)


class SafeNextTests(TestCase):
    def test_same_site_paths_only(self):
        from accounts.decorators import safe_next
        self.assertEqual(safe_next("/glossary?q=qun"), "/glossary?q=qun")
        self.assertEqual(safe_next("/units/u01"), "/units/u01")
        for bad in (None, "", "//evil.com", "https://evil.com", "http://evil.com/x", "evil.com", "glossary",
                    "/\\evil.com", "\\\\evil.com", "/\\/evil.com", "javascript:alert(1)", "/\tevil", "/x\nLocation: y"):
            with self.subTest(bad=bad):
                self.assertEqual(safe_next(bad), "/")


class PipelineTests(TestCase):
    """The pipeline steps on their own, with the ID-token claims as a plain dict (no network)."""

    def enforce(self, response):
        from accounts.pipeline import enforce_allowlist
        return enforce_allowlist(backend=None, details={"username": response.get("name"), "email": "x@y"},
                                 response=response)

    def refused(self, response):
        from accounts.pipeline import AuthForbidden
        with self.assertRaises(AuthForbidden):
            self.enforce(response)

    def test_identifier_order_and_details(self):
        allow("abc123")
        for key in ("preferred_username", "upn", "email"):
            with self.subTest(key=key):
                out = self.enforce({key: "ABC123@cam.ac.uk", "name": "A. B. C.", "sub": "zz"})
                self.assertEqual(out["details"]["username"], "abc123")
                self.assertEqual(out["details"]["email"], "")
                self.assertEqual(out["details"]["first_name"], "A. B. C.")
        out = self.enforce({"preferred_username": "abc123@cam.ac.uk", "upn": "other@cam.ac.uk"})
        self.assertEqual(out["details"]["username"], "abc123")
        self.assertEqual(out["details"]["first_name"], "abc123")     # no name claim: the CRSid

    def test_sub_is_never_the_identifier(self):
        allow("abc123", "@cam.ac.uk")
        self.refused({"sub": "abc123"})
        self.refused({"sub": "abc123@cam.ac.uk", "name": "X"})
        self.refused({})

    def test_local_part_must_look_like_a_crsid(self):
        allow("@cam.ac.uk")
        self.refused({"preferred_username": "a.b@cam.ac.uk"})
        self.refused({"preferred_username": "x_gmail.com#ext#@cam.ac.uk"})
        self.refused({"preferred_username": "abc123"})    # no domain at all

    def test_allowlist_matching(self):
        allow("abc123", "xyz9@cam.ac.uk")
        for ident in ("ABC123@cam.ac.uk", "abc123@CAM.AC.UK", "XYZ9@cam.ac.uk"):
            with self.subTest(ident=ident):
                self.enforce({"preferred_username": ident})
        for ident in ("abc123@gmail.com", "abc123@cam.ac.uk.evil.com", "abc123@evilcam.ac.uk", "nobody@cam.ac.uk", "abc123@ling.cam.ac.uk"):
            with self.subTest(ident=ident):
                self.refused({"preferred_username": ident})

    def test_identifier_needs_exactly_one_at(self):
        allow("abc123", "@cam.ac.uk", "abc123@x.com", "@x.com")
        for ident in ("abc123@x.com@cam.ac.uk", "abc123@cam.ac.uk@x.com", "abc123@@cam.ac.uk", "@cam.ac.uk",
                      "abc123@"):
            with self.subTest(ident=ident):
                self.refused({"preferred_username": ident})
        from accounts.pipeline import is_allowed
        self.assertFalse(is_allowed("abc123@x.com@cam.ac.uk"))      # the per-request re-check too
        self.assertTrue(is_allowed("abc123@cam.ac.uk"))

    def test_only_cambridge_addresses_can_be_allowed(self):
        allow("cz201", "visitor@example.ac.uk", "@partner.ac.uk", "@example.ac.uk", "cz201@ling.cam.ac.uk")
        for ident in ("visitor@example.ac.uk", "anyone.here@partner.ac.uk", "cz201@example.ac.uk",
                      "cz201@ling.cam.ac.uk"):
            with self.subTest(ident=ident):
                self.refused({"preferred_username": ident})

    def test_well_formed_tolerates_none(self):
        from accounts.pipeline import well_formed
        self.assertFalse(well_formed(None))
        self.assertFalse(well_formed(""))

    def test_identity_of(self):
        from accounts.pipeline import identity_of
        self.assertEqual(identity_of("cz201@cam.ac.uk"), "cz201")
        self.assertEqual(identity_of("cz201@example.ac.uk"), "cz201@example.ac.uk")
        self.assertEqual(identity_of("cz201@ling.cam.ac.uk"), "cz201@ling.cam.ac.uk")

    def test_domain_entry_is_exact(self):
        allow("@cam.ac.uk")
        self.enforce({"preferred_username": "x@cam.ac.uk"})
        self.refused({"preferred_username": "x@evilcam.ac.uk"})
        self.refused({"preferred_username": "x@cam.ac.uk.evil.com"})

    def test_finish_login_keeps_no_email(self):
        from accounts.pipeline import finish_login

        class Strategy:
            def __init__(self):
                self.session = {"next": "//evil.com"}

            def session_get(self, key, default=None):
                return self.session.get(key, default)

            def session_set(self, key, value):
                self.session[key] = value

        user = User.objects.create_user("abc123", email="abc123@cam.ac.uk", password="pw")
        strategy = Strategy()
        finish_login(backend=None, user=user, strategy=strategy, login_identifier="abc123@cam.ac.uk",
                     details={"first_name": "A. B. C."})
        user.refresh_from_db()
        self.assertEqual(user.email, "")
        self.assertFalse(user.has_usable_password())
        self.assertEqual(user.first_name, "A. B. C.")
        self.assertEqual(strategy.session["next"], "/")

    def test_finish_login_refuses_inactive_user(self):
        from accounts.pipeline import AuthForbidden, finish_login
        user = User.objects.create_user("abc123", is_active=False)
        with self.assertRaises(AuthForbidden):
            finish_login(backend=None, user=user, strategy=None, login_identifier="abc123@cam.ac.uk", details={})


@oidc_settings(CONTENT_DIR=str(FIXTURE), REVIEWERS=["cz201"])
class SignInFlowTests(TestCase):
    """The whole sign-in, through the views, with Microsoft's code exchange and ID-token check stubbed."""

    def setUp(self):
        allow("cz201", "ab123")

    def test_login_redirects_to_microsoft(self):
        with no_network():
            r = self.client.get("/login?next=/glossary")
        self.assertEqual(r.status_code, 302)
        url = urlparse(r["Location"])
        q = parse_qs(url.query)
        self.assertEqual(f"{url.scheme}://{url.netloc}", "https://login.microsoftonline.com")
        self.assertTrue(url.path.startswith(f"/{TENANT}/"))
        self.assertEqual(q["client_id"], ["test-client-id"])
        self.assertTrue(q["redirect_uri"][0].endswith(COMPLETE))
        self.assertTrue(q["state"][0])
        self.assertIn("code_challenge", q)
        self.assertNotIn("form_post", q.get("response_mode", [""])[0])    # a GET back, so the Lax cookie is sent
        # The state lives in the signed session cookie, which is SameSite=Lax
        cookie = r.cookies["sessionid"]
        self.assertEqual(cookie["samesite"], "Lax")
        self.assertTrue(cookie["secure"])
        state = q["state"][0]
        saved = self.client.session[f"azuread-tenant-oauth2_oauth2_state_{state}"]
        self.assertEqual(saved["state"], state)
        self.assertTrue(saved["code_verifier"])
        self.assertEqual(self.client.session["next"], "/glossary")

    def test_login_sanitises_next(self):
        for bad in ("//evil.com", "https://evil.com", "/\\evil.com"):
            with self.subTest(bad=bad), no_network():
                self.client.get("/login", {"next": bad})
                self.assertEqual(self.client.session["next"], "/")

    def test_callback_url_name(self):
        from django.urls import reverse
        self.assertEqual(reverse("auth.callback"), COMPLETE)
        self.assertEqual(reverse("social:complete", args=("azuread-tenant-oauth2",)), COMPLETE)

    def test_sign_in_and_return(self):
        r = sso_sign_in(self.client, next="/glossary")
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r["Location"], "/glossary")
        self.assertEqual(self.client.get("/glossary").status_code, 200)
        html = self.client.get("/").content.decode()
        self.assertIn("C. Z.", html)
        self.assertIn("Reviewer notes: off", html)
        self.assertIn('id="units"', html)

    def test_only_user_name_and_display_name_are_stored(self):
        sso_sign_in(self.client)
        user = User.objects.get()
        self.assertEqual(user.username, "cz201")
        self.assertEqual(user.first_name, "C. Z.")
        self.assertEqual((user.email, user.last_name), ("", ""))
        self.assertFalse(user.has_usable_password())
        social = UserSocialAuth.objects.get()
        self.assertNotIn("@", social.uid)
        self.assertNotIn("test-access-token", str(social.extra_data))
        self.assertNotIn("test-id-token", str(social.extra_data))
        self.assertNotIn("@", str(social.extra_data))

    def test_identity_is_the_crsid_even_if_the_user_name_was_taken(self):
        User.objects.create_user("cz201")      # e.g. an admin account made by hand with that name
        sso_sign_in(self.client)
        self.assertEqual(User.objects.count(), 2)
        html = self.client.get("/").content.decode()
        self.assertIn("Reviewer notes: off", html)    # cz201 is a reviewer whatever the account is called

    def test_sign_in_on_another_device_keeps_this_one(self):
        a, b = Client(), Client()
        sso_sign_in(a)
        self.assertEqual(a.get("/glossary").status_code, 200)
        sso_sign_in(b)
        self.assertEqual(b.get("/glossary").status_code, 200)
        self.assertEqual(a.get("/glossary").status_code, 200)    # still signed in on the first device

    def test_logout_on_one_device_keeps_the_other(self):
        a, b = Client(), Client()
        sso_sign_in(a)
        sso_sign_in(b)
        self.assertEqual(b.post("/logout")["Location"], "/signed-out")
        self.assertEqual(b.get("/glossary").status_code, 302)
        self.assertEqual(a.get("/glossary").status_code, 200)

    def test_v1_token_claims(self):
        """A v1.0-shaped token (upn, unique_name, tid; no preferred_username) signs in by its upn."""
        r = sso_sign_in(self.client, claims_for("cz201@cam.ac.uk", "C. Z.", v1=True), next="/glossary")
        self.assertEqual(r["Location"], "/glossary")
        r = self.client.get("/")
        self.assertEqual(r.wsgi_request.user_info, {"id": "cz201", "name": "C. Z.", "reviewer": True})
        self.assertEqual(User.objects.get().username, "cz201")

    def test_two_at_signs_refused_and_no_user(self):
        allow("@cam.ac.uk", "@x.com")
        with self.assertLogs("accounts", "WARNING"):
            r = sso_sign_in(self.client, claims_for("abc123@x.com@cam.ac.uk"))
        self.assertEqual(r.status_code, 403)
        self.assertEqual(User.objects.count(), 0)

    def test_real_id_token_validation(self):
        """The ID token itself is checked (RS256 signature against the JWKS, audience, issuer, tenant):
        only the code exchange and the key/metadata downloads are stubbed, with a locally made key."""
        import time
        from unittest import mock

        import jwt
        from cryptography.hazmat.primitives.asymmetric import rsa
        from jwt.algorithms import RSAAlgorithm
        from social_core.backends.azuread_tenant import AzureADTenantOAuth2

        def key():
            return rsa.generate_private_key(public_exponent=65537, key_size=2048)

        good, other = key(), key()
        jwk = {**RSAAlgorithm.to_jwk(good.public_key(), as_dict=True), "kid": "k1", "use": "sig"}
        issuer = f"https://login.microsoftonline.com/{TENANT}/v2.0"
        now = int(time.time())

        def token(signing_key, **claims):
            body = {**claims_for(), "aud": "test-client-id", "iss": issuer, "iat": now, "nbf": now,
                    "exp": now + 600, **claims}
            return jwt.encode(body, signing_key, algorithm="RS256", headers={"kid": "k1"})

        def sign_in(id_token):
            client = Client()
            with no_network():
                r = client.get("/login")
                state = parse_qs(urlparse(r["Location"]).query)["state"][0]
                with mock.patch.object(AzureADTenantOAuth2, "request_access_token",
                                       return_value={"access_token": "a", "id_token": id_token}), \
                        mock.patch.object(AzureADTenantOAuth2, "get_jwks_keys", return_value=[jwk]), \
                        mock.patch.object(AzureADTenantOAuth2, "openid_configuration",
                                          return_value={"issuer": issuer}):
                    return client.get(COMPLETE, {"code": "c", "state": state})

        self.assertEqual(sign_in(token(good))["Location"], "/")
        self.assertEqual(User.objects.count(), 1)
        for bad in (token(other), token(good, aud="another-app"), token(good, exp=now - 3600),
                    token(good, tid="11111111-1111-1111-1111-111111111111")):
            with self.subTest(), self.assertLogs("accounts", "WARNING"):
                self.assertEqual(sign_in(bad).status_code, 400)
        self.assertEqual(User.objects.count(), 1)

    def test_second_sign_in_reuses_the_account(self):
        sso_sign_in(self.client)
        self.client.post("/logout")
        sso_sign_in(self.client, claims_for(name="C. Zhang"))
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(User.objects.get().first_name, "C. Zhang")

    def test_not_allowlisted_refused_with_403_and_no_user(self):
        with self.assertLogs("accounts", "WARNING"):
            r = sso_sign_in(self.client, claims_for("someone@example.com"))
        self.assertEqual(r.status_code, 403)
        self.assertIn(REFUSED, r.content.decode())
        self.assertIn("Sign-in problem", r.content.decode())
        self.assertEqual(User.objects.count(), 0)
        self.assertEqual(UserSocialAuth.objects.count(), 0)
        self.assertEqual(self.client.get("/glossary").status_code, 302)     # still not signed in

    def test_token_without_identifier_refused_and_no_user(self):
        allow("@cam.ac.uk")
        with self.assertLogs("accounts", "WARNING"):
            r = sso_sign_in(self.client, {"sub": "cz201", "name": "C. Z.", "tid": TENANT})
        self.assertEqual(r.status_code, 403)
        self.assertIn(REFUSED, r.content.decode())
        self.assertEqual(User.objects.count(), 0)

    def test_failed_exchange_shows_error_page_and_logs_no_secrets(self):
        import requests
        with self.assertLogs("accounts", "WARNING") as logs:
            r = sso_sign_in(self.client, exchange_error=requests.ConnectionError("bad code test-access-token"))
        self.assertEqual(r.status_code, 400)
        self.assertIn(FAILED, r.content.decode())
        self.assertNotIn("test-access-token", "\n".join(logs.output))
        self.assertNotIn("test-client-secret", "\n".join(logs.output))
        self.assertEqual(User.objects.count(), 0)

    def test_social_auth_error_shows_error_page(self):
        from social_core.exceptions import AuthResponseError
        with self.assertLogs("accounts", "WARNING"):
            r = sso_sign_in(self.client, exchange_error=AuthResponseError(None, code="missing_claim"))
        self.assertEqual(r.status_code, 400)
        self.assertIn(FAILED, r.content.decode())

    def test_programming_error_in_sign_in_is_a_logged_500(self):
        """Only social-auth and network failures become the sign-in error page; a bug is a 500 with
        a traceback in the log."""
        client = Client(raise_request_exception=False)
        with self.assertLogs("django.request", "ERROR") as logs:
            r = sso_sign_in(client, exchange_error=RuntimeError("a bug"))
        self.assertEqual(r.status_code, 500)
        self.assertIn("Traceback", "\n".join(logs.output))
        self.assertEqual(User.objects.count(), 0)

    def test_wrong_state_refused(self):
        with self.assertLogs("accounts", "WARNING"):
            r = sso_sign_in(self.client, state="forged")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(User.objects.count(), 0)

    def test_cancelled_at_microsoft(self):
        with no_network():
            self.client.get("/login")
            with self.assertLogs("accounts", "WARNING"):
                r = self.client.get(COMPLETE, {"error": "access_denied", "error_description": "cancelled"})
        self.assertEqual(r.status_code, 400)
        self.assertIn(FAILED, r.content.decode())

    def test_signin_error_page(self):
        r = self.client.get("/signin-error")
        self.assertIn(FAILED, r.content.decode())
        self.assertIn('href="/login"', r.content.decode())

    def test_no_open_redirect(self):
        self.assertEqual(sso_sign_in(self.client, next="//evil.example.com/")["Location"], "/")

    def test_no_open_redirect_through_the_social_begin_url(self):
        from unittest import mock

        from social_core.backends.azuread_tenant import AzureADTenantOAuth2
        with no_network():
            r = self.client.post("/auth/sso/login/azuread-tenant-oauth2/?next=/\\evil.example.com")
            state = parse_qs(urlparse(r["Location"]).query)["state"][0]
            token = {"access_token": "a", "id_token": "i"}
            with mock.patch.object(AzureADTenantOAuth2, "request_access_token", return_value=token), \
                    mock.patch.object(AzureADTenantOAuth2, "user_data", return_value=claims_for()):
                r = self.client.get(COMPLETE, {"code": "c", "state": state})
        self.assertEqual(r["Location"], "/")

    def test_session_cookie_is_secure(self):
        r = sso_sign_in(self.client)
        cookie = r.cookies["sessionid"]
        self.assertTrue(cookie["secure"])
        self.assertTrue(cookie["httponly"])
        self.assertEqual(cookie["samesite"], "Lax")

    def test_learner_is_not_reviewer(self):
        sso_sign_in(self.client, claims_for("ab123@cam.ac.uk", "A. B."))
        html = self.client.get("/").content.decode()
        self.assertIn("A. B.", html)
        self.assertNotIn("Reviewer notes", html)
        self.assertEqual(self.client.get("/review").status_code, 404)
        self.assertEqual(self.client.post("/reviewer-mode", {"on": "1"}).status_code, 404)

    def test_login_while_signed_in_signs_out_first(self):
        sso_sign_in(self.client)
        with no_network():
            self.client.get("/login")
        self.assertEqual(self.client.get("/glossary").status_code, 302)


@oidc_settings(CONTENT_DIR=str(FIXTURE), REVIEWERS=["cz201"])
class GateTests(TestCase):
    """What a visitor who is not signed in can reach in oidc mode, and the per-request re-check."""

    def setUp(self):
        allow("cz201")

    def test_pages_need_sign_in(self):
        r = self.client.get("/units/u01")
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r["Location"], "/login?next=/units/u01")
        r = self.client.get("/glossary?q=qun")
        self.assertEqual(r["Location"], "/login?next=/glossary%3Fq%3Dqun")

    def test_every_other_url_is_closed(self):
        for path in ("/units/u01", "/units/u01/p01", "/grammar", "/grammar/g01", "/toolkit", "/toolkit/t02",
                     "/glossary", "/review", "/assistant/", "/assistant/help", "/no-such-page", "/units/u99"):
            with self.subTest(path=path):
                r = self.client.get(path)
                self.assertEqual(r.status_code, 302)
                self.assertTrue(r["Location"].startswith("/login?next="))
        r = self.client.post("/reviewer-mode", {"on": "1"})
        self.assertEqual(r.status_code, 302)
        self.assertNotIn("review_mode", self.client.session)

    def test_open_pages(self):
        for path in ("/healthz", "/static/css/site.css", "/accessibility", "/", "/welcome", "/signed-out"):
            with self.subTest(path=path):
                r = self.client.get(path)
                self.assertEqual(r.status_code, 200)
                r.close()
        self.assertIn("Sign in with", self.client.get("/").content.decode())
        self.assertEqual(self.client.get("/signin-error").status_code, 400)

    def test_anonymous_api_calls_get_401_json(self):
        for method, path in (("get", "/summaries.json"), ("post", "/assistant/api/words"),
                             ("get", "/assistant/api/words")):
            with self.subTest(path=path, method=method):
                r = getattr(self.client, method)(path)
                self.assertEqual(r.status_code, 401)
                self.assertEqual(r["Content-Type"], "application/json")
                self.assertEqual(r.json(), {"error": "sign-in required"})

    def test_allowlist_entry_deleted_mid_session(self):
        sso_sign_in(self.client)
        self.assertEqual(self.client.get("/glossary").status_code, 200)
        AllowedLogin.objects.filter(entry="cz201").delete()
        r = self.client.get("/glossary")
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r["Location"], "/login?next=/glossary")
        allow("cz201")      # put back: the old session stays ended
        self.assertEqual(self.client.get("/glossary").status_code, 302)

    def test_allowlist_entry_deleted_mid_session_api(self):
        sso_sign_in(self.client)
        AllowedLogin.objects.all().delete()
        self.assertEqual(self.client.get("/summaries.json").status_code, 401)

    def test_deactivated_user_refused_on_next_request(self):
        sso_sign_in(self.client)
        self.assertEqual(self.client.get("/glossary").status_code, 200)
        User.objects.filter(username="cz201").update(is_active=False)
        r = self.client.get("/glossary")
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r["Location"], "/login?next=/glossary")

    def test_deactivated_user_cannot_sign_in_again(self):
        sso_sign_in(self.client)
        self.client.post("/logout")
        User.objects.update(is_active=False)
        with self.assertLogs("accounts", "WARNING"):
            r = sso_sign_in(self.client)
        self.assertEqual(r.status_code, 403)
        self.assertEqual(self.client.get("/glossary").status_code, 302)

    def test_removed_user_on_open_page_is_signed_out(self):
        sso_sign_in(self.client)
        AllowedLogin.objects.all().delete()
        html = self.client.get("/").content.decode()
        self.assertIn("Sign in with", html)
        self.assertNotIn("C. Z.", html)

    def test_database_error_in_the_recheck_fails_closed(self):
        from unittest import mock

        from django.db import DatabaseError
        sso_sign_in(self.client)
        client = Client(raise_request_exception=False)
        client.cookies = self.client.cookies
        with mock.patch.object(type(AllowedLogin.objects), "allows", side_effect=DatabaseError("locked")), \
                self.assertLogs("django.request", "ERROR") as logs:
            r = client.get("/glossary")
            api = client.get("/summaries.json")
        self.assertEqual(r.status_code, 500)
        self.assertEqual(api.status_code, 500)
        self.assertNotIn("Glossary", r.content.decode())
        self.assertIn("DatabaseError", "\n".join(logs.output))

    def test_admin_add_view_stores_the_normalised_entry(self):
        User.objects.create_superuser("admin", password="a-long-admin-password-123")
        client = Client(enforce_csrf_checks=True)
        client.login(username="admin", password="a-long-admin-password-123")
        url = "/django-admin/accounts/allowedlogin/add/"
        html = client.get(url).content.decode()
        token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', html).group(1)
        r = client.post(url, {"csrfmiddlewaretoken": token, "entry": "  @Ling.CAM.ac.uk ", "note": "Linguistics"})
        self.assertEqual(r.status_code, 302, r.content.decode()[:500])
        self.assertTrue(AllowedLogin.objects.filter(entry="@ling.cam.ac.uk", note="Linguistics").exists())
        r = client.post(url, {"csrfmiddlewaretoken": token, "entry": "not valid!"})
        self.assertEqual(r.status_code, 200)      # the form again, with the error
        self.assertFalse(AllowedLogin.objects.filter(entry="not valid!").exists())

    def test_admin_password_login_only_counts_inside_the_admin(self):
        User.objects.create_superuser("admin", password="a-long-admin-password-123")
        self.assertTrue(self.client.login(username="admin", password="a-long-admin-password-123"))
        self.assertEqual(self.client.get("/django-admin/").status_code, 200)
        r = self.client.get("/glossary")
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r["Location"].startswith("/login"))

    def test_sso_user_removed_from_allowlist_is_refused_in_the_admin_too(self):
        sso_sign_in(self.client)
        User.objects.filter(username="cz201").update(is_staff=True, is_superuser=True)
        self.assertEqual(self.client.get("/django-admin/").status_code, 200)
        AllowedLogin.objects.all().delete()
        r = self.client.get("/django-admin/")
        self.assertEqual(r.status_code, 302)
        self.assertNotEqual(self.client.get("/glossary").status_code, 200)


@oidc_settings(CONTENT_DIR=str(FIXTURE), REVIEWERS=["cz201"])
class CsrfTests(TestCase):
    """POSTs without the CSRF token are refused with 403 and leave the session as it was."""

    def setUp(self):
        allow("cz201")
        self.client = Client(enforce_csrf_checks=True)
        sso_sign_in(self.client)

    def session_cookie(self):
        return self.client.cookies["sessionid"].value

    def test_logout_needs_token(self):
        before = self.session_cookie()
        r = self.client.post("/logout")
        self.assertEqual(r.status_code, 403)
        self.assertNotIn("sessionid", r.cookies)
        self.assertEqual(self.session_cookie(), before)
        self.assertEqual(self.client.get("/glossary").status_code, 200)     # still signed in
        token = csrf_from(self.client.get("/").content.decode())
        r = self.client.post("/logout", {"csrfmiddlewaretoken": token})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r["Location"], "/signed-out")
        self.assertEqual(self.client.get("/glossary").status_code, 302)
        self.assertIn("Sign in with", self.client.get("/").content.decode())     # back to the landing page
        self.assertIn("You have signed out", self.client.get("/signed-out").content.decode())

    def proxied_post(self, origin):
        token = csrf_from(self.client.get("/").content.decode())
        return self.client.post("/logout", {"csrfmiddlewaretoken": token}, HTTP_HOST="mlc.example.ac.uk",
                                HTTP_ORIGIN=origin, HTTP_X_FORWARDED_PROTO="https")

    def test_origin_check_behind_the_proxy(self):
        """Production: TLS ends at the proxy; with MLC_TRUST_PROXY Django sees https and the Origin matches."""
        with self.settings(SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO", "https"), USE_X_FORWARDED_HOST=True):
            r = self.proxied_post("https://mlc.example.ac.uk")
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r["Location"], "/signed-out")

    def test_origin_check_fails_without_trust_proxy(self):
        r = self.proxied_post("https://mlc.example.ac.uk")
        self.assertEqual(r.status_code, 403)
        self.assertEqual(self.client.get("/glossary").status_code, 200)     # still signed in

    def test_origin_from_another_site_refused_behind_the_proxy(self):
        with self.settings(SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO", "https"), USE_X_FORWARDED_HOST=True):
            r = self.proxied_post("https://evil.example.com")
        self.assertEqual(r.status_code, 403)

    def test_forms_use_djangos_field_name_only(self):
        html = self.client.get("/").content.decode()
        self.assertNotIn('name="csrf"', html)
        token = csrf_from(html)
        self.assertEqual(self.client.post("/logout", {"csrf": token}).status_code, 403)    # Flask's old name
        self.assertEqual(self.client.post("/logout", {"csrfmiddlewaretoken": token})["Location"], "/signed-out")

    def test_logout_is_post_only(self):
        self.assertEqual(self.client.get("/logout").status_code, 405)
        self.assertEqual(self.client.get("/glossary").status_code, 200)

    def test_reviewer_mode_needs_token(self):
        before = self.session_cookie()
        r = self.client.post("/reviewer-mode", {"on": "1", "next": "/glossary"})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(self.session_cookie(), before)
        self.assertNotIn("review_mode", self.client.session)
        token = csrf_from(self.client.get("/").content.decode())
        r = self.client.post("/reviewer-mode", {"csrfmiddlewaretoken": token, "on": "1", "next": "/glossary"})
        self.assertEqual(r["Location"], "/glossary")
        self.assertIn("Reviewer notes: on", self.client.get("/").content.decode())

    def test_reviewer_mode_next_is_same_site(self):
        token = csrf_from(self.client.get("/").content.decode())
        r = self.client.post("/reviewer-mode", {"csrfmiddlewaretoken": token, "on": "1", "next": "//evil.com"})
        self.assertEqual(r["Location"], "/")


class ContentErrorTests(TestCase):
    """Broken content after an edit in debug, in oidc mode: /healthz still answers to anyone, and a
    signed-in user sees the error list on the pages (the last valid course is kept)."""

    def test_content_error_with_sign_in(self):
        import os
        import shutil
        import tempfile
        from pathlib import Path

        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        root = tmp / "content"
        shutil.copytree(FIXTURE, root)
        allow("cz201")
        with oidc_settings(CONTENT_DIR=str(root), DEBUG=True):
            sso_sign_in(self.client)
            f = root / "units/u01-topic-and-comment/u01-p01-old-empire.md"
            f.write_text(f.read_text(encoding="utf-8").replace("status: draft", "status: finished"), encoding="utf-8")
            os.utime(f, (f.stat().st_atime + 10, f.stat().st_mtime + 10))
            self.assertEqual(Client().get("/healthz").status_code, 200)
            html = self.client.get("/").content.decode()
        self.assertIn("The content has validation errors", html)
        self.assertIn('id="units"', html)


@page_settings(CONTENT, REVIEWERS=["cz201"])
class ReviewerTests(TestCase):
    """Reviewer mode in development (`none` mode): DEV_USER is a reviewer iff listed in REVIEWERS."""

    def client_for(self, user):
        self.enterContext(page_settings(CONTENT, REVIEWERS=["cz201"], DEV_USER=user))
        return Client(enforce_csrf_checks=True)

    def turn_on(self, client):
        token = csrf_from(client.get("/").content.decode())
        client.post("/reviewer-mode", {"csrfmiddlewaretoken": token, "on": "1", "next": "/"})

    def test_dev_user_identity(self):
        c = self.client_for("cz201")
        html = c.get("/").content.decode()
        self.assertIn("Reviewer notes: off", html)
        self.assertNotIn("Sign out", html)

    def test_notes_hidden_until_switched_on(self):
        c = self.client_for("cz201")
        self.assertNotIn('class="review-note"', c.get("/units/u17/p01").content.decode())
        self.turn_on(c)
        self.assertIn('class="review-note"', c.get("/units/u17/p01").content.decode())

    def test_learners_never_see_notes(self):
        c = self.client_for("ab123")
        self.assertEqual(c.post("/reviewer-mode", {"on": "1"}).status_code, 403)    # no token
        self.assertNotIn('class="review-note"', c.get("/units/u17/p01").content.decode())
        self.assertEqual(Client().post("/reviewer-mode", {"on": "1"}).status_code, 404)    # past CSRF: not a reviewer

    def test_every_note_is_placed(self):
        from app.content import load
        course = load(CONTENT)
        pages = [*course.units.values(), *course.passages.values(), *course.grammar.values(), *course.toolkit.values()]
        notes = [r for pg in pages for r in pg.reviews]
        self.assertTrue(notes)
        for r in notes:
            self.assertTrue(r.body and not r.body.startswith("REVIEW"))
        c = self.client_for("cz201")
        self.turn_on(c)
        shown = 0
        for pg in pages:
            if pg.reviews:
                shown += c.get(course.urls[pg.path.resolve()]).content.decode().count('class="review-note"')
        self.assertEqual(shown, len(notes), "every REVIEW comment appears on its page")

    def test_review_list(self):
        self.assertEqual(self.client_for("cz201").get("/review").status_code, 200)
        self.assertEqual(self.client_for("ab123").get("/review").status_code, 404)

    def test_reviewers_see_unreviewed_pages_at_release(self):
        with page_settings(CONTENT, REVIEWERS=["cz201"], DEV_USER="ab123", SHOW_UNREVIEWED=False):
            self.assertEqual(Client().get("/units/u17/p01").status_code, 404)
        with page_settings(CONTENT, REVIEWERS=["cz201"], DEV_USER="cz201", SHOW_UNREVIEWED=False):
            self.assertEqual(Client().get("/units/u17/p01").status_code, 200)

    def test_login_in_development_goes_straight_back(self):
        r = Client().get("/login?next=/glossary")
        self.assertEqual(r["Location"], "/glossary")
        self.assertEqual(Client().get("/login?next=//evil.com")["Location"], "/")


if __name__ == "__main__":
    unittest.main()
