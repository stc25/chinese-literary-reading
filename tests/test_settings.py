import os
import tempfile
import unittest
from pathlib import Path

# `unittest discover -s tests` imports this file as a top-level module, so tests/__init__.py
# does not run; opt in to the test configuration explicitly before config.settings loads.
os.environ.setdefault("MLC_TESTING", "1")

from django.core.exceptions import ImproperlyConfigured

from config.envfile import read_env_file
from config.settings import build_settings, is_testing, parse_bool

OIDC = {
    "AUTH_MODE": "oidc",
    "SECRET_KEY": "s",
    "AZURE_CLIENT_ID": "id",
    "AZURE_CLIENT_SECRET": "secret",
    "AZURE_TENANT_ID": "tenant",
}


class EnvFile(unittest.TestCase):
    def read(self, text=None):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / ".env"
            if text is not None:
                p.write_text(text, encoding="utf-8")
            return read_env_file(p)

    def test_ollama_alias(self):
        self.assertEqual(self.read("Ollama_API=k\n"), {"OLLAMA_API_KEY": "k"})

    def test_json_values(self):
        self.assertEqual(self.read('MLC_REVIEWERS=["cz201"]\n'), {"REVIEWERS": ["cz201"]})

    def test_comments_and_blank_lines_ignored(self):
        self.assertEqual(self.read("# note\n\nOTHER=1\n"), {})

    def test_missing_file(self):
        self.assertEqual(self.read(None), {})


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
        env = dict(OIDC, SECRET_KEY=12345, AZURE_CLIENT_ID=1, AZURE_CLIENT_SECRET=2, AZURE_TENANT_ID=3)
        s = build_settings(env, debug=False, testing=False)
        for k in ("SECRET_KEY", "AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET", "AZURE_TENANT_ID"):
            self.assertIsInstance(s[k], str)


if __name__ == "__main__":
    unittest.main()
