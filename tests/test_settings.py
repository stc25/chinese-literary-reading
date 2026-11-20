import os
import tempfile
import unittest
from pathlib import Path

# `unittest discover -s tests` imports this file as a top-level module, so tests/__init__.py
# does not run; opt in to the test configuration explicitly before config.settings loads.
os.environ.setdefault("MLC_TESTING", "1")

from django.core.exceptions import ImproperlyConfigured

from config.envfile import read_env_file
from config.settings import build_settings, is_testing, merge_env, parse_bool, parse_url_prefix

OIDC = {
    "AUTH_MODE": "oidc",
    "SECRET_KEY": "k" * 20 + "0123456789abcdefghijklmnopqrstuv",
    "AZURE_CLIENT_ID": "id",
    "AZURE_CLIENT_SECRET": "secret",
    "AZURE_TENANT_ID": "6a3c1b6e-2f4d-4e8a-9b1c-0d2e3f4a5b6c",
}


class EnvFile(unittest.TestCase):
    def read(self, text=None):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / ".env"
            if text is not None:
                p.write_text(text, encoding="utf-8")
            return read_env_file(p)

    def test_read(self):
        text = ('# comment\nOllama_API="abc"\nMLC_OLLAMA_HOST=https://ollama.com\n'
                'export MLC_ASSISTANT_DAILY_LIMIT=10\nMLC_REVIEWERS=["a"]\nOTHER=x\n\n')
        self.assertEqual(self.read(text), {"OLLAMA_API_KEY": "abc", "OLLAMA_HOST": "https://ollama.com",
                                           "ASSISTANT_DAILY_LIMIT": 10, "REVIEWERS": ["a"]})
        self.assertEqual(self.read(), {})

    def test_ollama_alias(self):
        self.assertEqual(self.read("Ollama_API=k\n"), {"OLLAMA_API_KEY": "k"})

    def test_json_values(self):
        self.assertEqual(self.read('MLC_REVIEWERS=["cz201"]\n'), {"REVIEWERS": ["cz201"]})

    def test_comments_and_blank_lines_ignored(self):
        self.assertEqual(self.read("# note\n\nOTHER=1\n"), {})

    def test_missing_file(self):
        self.assertEqual(self.read(None), {})


    def test_env_files_are_ignored_by_git(self):
        root = Path(__file__).resolve().parent.parent
        self.assertIn(".env", (root / ".gitignore").read_text().split())


class WsgiEntryPoints(unittest.TestCase):
    """`gunicorn wsgi:application` and `gunicorn config.wsgi:application` are the same Django app."""

    def test_root_wsgi_is_the_django_application(self):
        import importlib
        import sys
        root = str(Path(__file__).resolve().parent.parent)
        if root not in sys.path:
            sys.path.insert(0, root)
        wsgi = importlib.import_module("wsgi")
        config_wsgi = importlib.import_module("config.wsgi")
        self.assertIs(wsgi.application, config_wsgi.application)
        self.assertTrue(callable(wsgi.application))


class MergeEnv(unittest.TestCase):
    FILE = {"OLLAMA_HOST": "from-file", "ASSISTANT_MODEL": "from-file", "OLLAMA_API_KEY": "file-key"}

    def test_environment_wins_over_the_file(self):
        out = merge_env(self.FILE, {"MLC_OLLAMA_HOST": "from-env"}, testing=False)
        self.assertEqual(out["OLLAMA_HOST"], "from-env")

    def test_file_fills_gaps(self):
        out = merge_env(self.FILE, {"MLC_OLLAMA_HOST": "from-env", "HOME": "/x"}, testing=False)
        self.assertEqual(out["ASSISTANT_MODEL"], "from-file")
        self.assertNotIn("HOME", out)

    def test_environment_values_are_json_parsed(self):
        out = merge_env({}, {"MLC_ASSISTANT_DAILY_LIMIT": "10", "MLC_REVIEWERS": '["a"]', "MLC_X": "plain"}, testing=False)
        self.assertEqual(out, {"ASSISTANT_DAILY_LIMIT": 10, "REVIEWERS": ["a"], "X": "plain"})

    def test_testing_ignores_the_file(self):
        out = merge_env(self.FILE, {"MLC_OLLAMA_HOST": "from-env"}, testing=True)
        self.assertEqual(out, {"OLLAMA_HOST": "from-env"})

    def test_file_alias_key_and_environment_override(self):
        file_env = read_env_file_text("Ollama_API=k\n")
        self.assertEqual(merge_env(file_env, {}, testing=False), {"OLLAMA_API_KEY": "k"})
        self.assertEqual(merge_env(file_env, {"MLC_OLLAMA_API_KEY": "env-key"}, testing=False),
                         {"OLLAMA_API_KEY": "env-key"})


def read_env_file_text(text):
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / ".env"
        p.write_text(text, encoding="utf-8")
        return read_env_file(p)


class UrlPrefix(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(parse_url_prefix(None), "")
        self.assertEqual(parse_url_prefix(""), "")
        self.assertEqual(parse_url_prefix("/"), "")
        self.assertEqual(parse_url_prefix("/chinese-literary-reading"), "/chinese-literary-reading")
        self.assertEqual(parse_url_prefix("/chinese-literary-reading/"), "/chinese-literary-reading")
        for bad in ("chinese", "/a b", "//evil.com", "/a//b", "http://x/y", "/a?b"):
            with self.subTest(bad=bad), self.assertRaises(ImproperlyConfigured):
                parse_url_prefix(bad)

    def test_settings_follow_the_prefix(self):
        s = build_settings({"URL_PREFIX": "/chinese-literary-reading"}, debug=True, testing=False)
        self.assertEqual(s["FORCE_SCRIPT_NAME"], "/chinese-literary-reading")
        self.assertEqual(s["STATIC_URL"], "/chinese-literary-reading/static/")
        self.assertEqual(s["SESSION_COOKIE_PATH"], "/chinese-literary-reading")
        self.assertEqual(s["CSRF_COOKIE_PATH"], "/chinese-literary-reading")
        self.assertEqual(s["SOCIAL_AUTH_LOGIN_ERROR_URL"], "/chinese-literary-reading/signin-error")

    def test_no_prefix_is_the_root(self):
        s = build_settings({}, debug=True, testing=False)
        self.assertIsNone(s["FORCE_SCRIPT_NAME"])
        self.assertEqual(s["STATIC_URL"], "/static/")
        self.assertEqual(s["SESSION_COOKIE_PATH"], "/")
        self.assertEqual((s["SESSION_COOKIE_NAME"], s["CSRF_COOKIE_NAME"]), ("mlc_session", "mlc_csrf"))


class Settings(unittest.TestCase):
    def test_bad_auth_mode(self):
        with self.assertRaises(ImproperlyConfigured):
            build_settings({"AUTH_MODE": "banana"}, debug=False, testing=False)

    def test_debug_defaults_to_none(self):
        s = build_settings({}, debug=True, testing=False)
        self.assertEqual(s["AUTH_MODE"], "none")
        self.assertTrue(s["SECRET_KEY"])

    def test_testing_defaults_to_none(self):
        self.assertEqual(build_settings({}, debug=False, testing=True)["AUTH_MODE"], "none")

    def test_production_defaults_to_oidc(self):
        with self.assertRaises(ImproperlyConfigured):
            build_settings({}, debug=False, testing=False)

    def test_oidc_complete(self):
        s = build_settings(dict(OIDC), debug=False, testing=False)
        self.assertEqual(s["AUTH_MODE"], "oidc")
        self.assertTrue(s["SESSION_COOKIE_SECURE"])
        self.assertEqual(s["SESSION_ENGINE"], "django.contrib.sessions.backends.signed_cookies")
        self.assertEqual(s["CSRF_HEADER_NAME"], "HTTP_X_CSRF_TOKEN")

    def test_logging_to_stderr(self):
        s = build_settings(dict(OIDC), debug=False, testing=False)
        log = s["LOGGING"]
        self.assertEqual(log["handlers"]["stderr"]["class"], "logging.StreamHandler")
        self.assertEqual(log["handlers"]["stderr"]["stream"], "ext://sys.stderr")
        self.assertEqual(log["formatters"]["plain"]["format"], "%(asctime)s %(levelname)s %(name)s: %(message)s")
        self.assertEqual(log["root"], {"handlers": ["stderr"], "level": "WARNING"})
        self.assertEqual(log["loggers"]["django"]["handlers"], [])
        self.assertTrue(log["loggers"]["django"]["propagate"])
        self.assertEqual(log["loggers"]["app"]["level"], "INFO")
        self.assertEqual(log["loggers"]["accounts"]["level"], "INFO")
        self.assertNotIn("level", log["handlers"]["stderr"])     # quiet only under test

    def test_sso_settings(self):
        s = build_settings(dict(OIDC), debug=False, testing=False)
        self.assertEqual(s["SOCIAL_AUTH_AZUREAD_TENANT_OAUTH2_KEY"], "id")
        self.assertEqual(s["SOCIAL_AUTH_AZUREAD_TENANT_OAUTH2_SECRET"], "secret")
        self.assertEqual(s["SOCIAL_AUTH_AZUREAD_TENANT_OAUTH2_TENANT_ID"], OIDC["AZURE_TENANT_ID"])
        self.assertEqual(s["AUTHENTICATION_BACKENDS"][0], "social_core.backends.azuread_tenant.AzureADTenantOAuth2")
        self.assertIs(s["SOCIAL_AUTH_RAISE_EXCEPTIONS"], False)
        self.assertFalse(s["SOCIAL_AUTH_USERNAME_IS_FULL_EMAIL"])
        self.assertTrue(s["SOCIAL_AUTH_REDIRECT_IS_HTTPS"])
        self.assertEqual(s["SOCIAL_AUTH_LOGIN_ERROR_URL"], "/signin-error")
        pipeline = s["SOCIAL_AUTH_PIPELINE"]
        self.assertNotIn("social_core.pipeline.social_auth.associate_by_email", pipeline)
        self.assertLess(pipeline.index("accounts.pipeline.enforce_allowlist"),
                        pipeline.index("social_core.pipeline.user.create_user"))
        self.assertEqual(pipeline[-1], "accounts.pipeline.finish_login")
        self.assertTrue(s["CSRF_COOKIE_SECURE"])

    def test_trust_proxy(self):
        """Behind the TLS proxy (MLC_TRUST_PROXY): the scheme and host it reports,
        so the SSO redirect URI and Django's CSRF origin check see https://<host>."""
        s = build_settings(dict(OIDC, TRUST_PROXY=1), debug=False, testing=False)
        self.assertEqual(s["SECURE_PROXY_SSL_HEADER"], ("HTTP_X_FORWARDED_PROTO", "https"))
        self.assertTrue(s["USE_X_FORWARDED_HOST"])
        s = build_settings(dict(OIDC), debug=False, testing=False)
        self.assertNotIn("SECURE_PROXY_SSL_HEADER", s)
        self.assertFalse(s.get("USE_X_FORWARDED_HOST", False))

    def test_none_mode_needs_no_azure_settings(self):
        s = build_settings({"AUTH_MODE": "none"}, debug=True, testing=False)
        self.assertEqual(s["SOCIAL_AUTH_AZUREAD_TENANT_OAUTH2_KEY"], "")
        self.assertFalse(s["SOCIAL_AUTH_REDIRECT_IS_HTTPS"])

    def test_weak_secret_key_refused(self):
        for bad in ("dev", "short-key-0123456789", "x" * 31, "<a long random string, e.g. from secrets.token_hex(32)>"):
            with self.subTest(bad=bad), self.assertRaises(ImproperlyConfigured) as cm:
                build_settings(dict(OIDC, SECRET_KEY=bad), debug=False, testing=False)
            self.assertIn("MLC_SECRET_KEY", str(cm.exception))
        build_settings(dict(OIDC, SECRET_KEY="x" * 32), debug=False, testing=False)
        build_settings({"AUTH_MODE": "none", "SECRET_KEY": "dev"}, debug=True, testing=False)   # development only

    def test_tenant_must_be_a_uuid(self):
        for bad in ("common", "organizations", "consumers", "cam.ac.uk", "6a3c1b6e"):
            with self.subTest(bad=bad), self.assertRaises(ImproperlyConfigured) as cm:
                build_settings(dict(OIDC, AZURE_TENANT_ID=bad), debug=False, testing=False)
            self.assertIn("MLC_AZURE_TENANT_ID", str(cm.exception))
        s = build_settings(dict(OIDC, AZURE_TENANT_ID=OIDC["AZURE_TENANT_ID"].upper()), debug=False, testing=False)
        self.assertEqual(s["SOCIAL_AUTH_AZUREAD_TENANT_OAUTH2_TENANT_ID"], OIDC["AZURE_TENANT_ID"])

    def test_password_validators(self):
        s = build_settings(dict(OIDC), debug=False, testing=False)
        names = [v["NAME"].rsplit(".", 1)[1] for v in s["AUTH_PASSWORD_VALIDATORS"]]
        self.assertEqual(names, ["UserAttributeSimilarityValidator", "MinimumLengthValidator",
                                 "CommonPasswordValidator", "NumericPasswordValidator"])

    def test_reload_content_is_strict(self):
        def reload(value):
            return build_settings({"RELOAD_CONTENT": value}, debug=True, testing=False)["RELOAD_CONTENT"]
        self.assertIsNone(build_settings({}, debug=True, testing=False)["RELOAD_CONTENT"])
        self.assertIsNone(reload(""))
        for v in ("no", "false", "0", 0, False, "off"):
            self.assertIs(reload(v), False, v)
        for v in ("yes", "true", "1", 1, True, "on"):
            self.assertIs(reload(v), True, v)
        with self.assertRaises(ImproperlyConfigured) as cm:
            reload("sometimes")
        self.assertIn("MLC_RELOAD_CONTENT", str(cm.exception))

    def test_oidc_requires_each_setting(self):
        for name in ("SECRET_KEY", "AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET", "AZURE_TENANT_ID"):
            for value in ("", None):
                env = dict(OIDC)
                env[name] = value
                with self.subTest(name=name, value=value):
                    with self.assertRaises(ImproperlyConfigured) as cm:
                        build_settings(env, debug=False, testing=False)
                    self.assertIn(name, str(cm.exception))
            env = dict(OIDC)
            del env[name]
            with self.subTest(name=name, value="absent"):
                with self.assertRaises(ImproperlyConfigured) as cm:
                    build_settings(env, debug=False, testing=False)
                self.assertIn(name, str(cm.exception))

    def test_values_pass_through(self):
        s = build_settings({"REVIEWERS": ["a"], "TRUST_PROXY": 1, "ASSISTANT_DAILY_LIMIT": 5},
                           debug=True, testing=False)
        self.assertEqual(s["REVIEWERS"], ["a"])
        self.assertEqual(s["TRUST_PROXY"], 1)
        self.assertEqual(s["ASSISTANT_DAILY_LIMIT"], 5)
        self.assertEqual(s["DEV_USER"], "dev")
        self.assertEqual(s["DATA_UPLOAD_MAX_MEMORY_SIZE"], 256 * 1024)


class Strictness(unittest.TestCase):
    def test_parse_bool(self):
        for v in ("1", "true", "True", "yes", "on", 1, True):
            with self.subTest(v=v):
                self.assertTrue(parse_bool(v, "DEBUG"))
        for v in ("False", "FALSE", "no", "off", "0", "", 0, False):
            with self.subTest(v=v):
                self.assertFalse(parse_bool(v, "DEBUG"))

    def test_parse_bool_rejects_unknown(self):
        for v in ("maybe", "2", "nope"):
            with self.subTest(v=v), self.assertRaises(ImproperlyConfigured):
                parse_bool(v, "DEBUG")

    def test_is_testing(self):
        self.assertFalse(is_testing(["gunicorn"], {}))
        self.assertFalse(is_testing(["manage.py", "runserver"], {"MLC_TESTING": ""}))
        self.assertFalse(is_testing(["x", "unittest"], {"MLC_TESTING": "false"}))
        self.assertTrue(is_testing(["manage.py", "test"], {}))
        self.assertTrue(is_testing(["x"], {"MLC_TESTING": "1"}))
        with self.assertRaises(ImproperlyConfigured):
            is_testing(["x"], {"MLC_TESTING": "banana"})

    def test_secrets_are_strings(self):
        env = dict(OIDC, SECRET_KEY=10 ** 40, AZURE_CLIENT_ID=1, AZURE_CLIENT_SECRET=2)
        s = build_settings(env, debug=False, testing=False)
        for k in ("SECRET_KEY", "AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET", "AZURE_TENANT_ID"):
            self.assertIsInstance(s[k], str)


if __name__ == "__main__":
    unittest.main()
