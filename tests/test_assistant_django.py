"""The reading assistant's Django views (ported from the Flask tests in tests/test_assistant.py,
same assertions; the framework-free modules are tested there).

Run with:  python manage.py test tests.test_assistant_django
"""
import os
import re
import sys
import threading
import time
import unittest
from io import StringIO
from pathlib import Path

os.environ.setdefault("MLC_TESTING", "1")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()   # a no-op under `manage.py test`; needed under `unittest discover`

from django.apps import apps
from django.conf import settings
from django.core.management import CommandError, call_command
from django.test import Client, SimpleTestCase, override_settings

from app.assistant import client as client_mod
from app.assistant.client import ModelError, OllamaClient
from tests.django_helpers import CONTENT, ROOT, oidc_settings
from tests.test_assistant import ScriptedSession, stub  # noqa: E402  (the same model stubs as the Flask tests)

TEXT = "日本人之稱我中國也"
TOKEN_RE = r'name="csrf" value="([^"]+)"'


def scripted(*script, timeout=60.0):
    return OllamaClient("http://model.test", "test-model", session=ScriptedSession(*script), timeout=timeout,
                        retry_pause=0)


def config():
    return apps.get_app_config("app")


def set_client(c):
    config().set_assistant("client", c)


def django_settings(**extra):
    return override_settings(CONTENT_DIR=str(CONTENT), AUTH_MODE="none", **extra)


@django_settings()
class Page(SimpleTestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)

    def post(self, text):
        html = self.client.get("/assistant/").content.decode()
        token = re.search(TOKEN_RE, html).group(1)
        return self.client.post("/assistant/", {"csrf": token, "text": text})

    def test_form(self):
        self.assertEqual(self.client.get("/assistant/").status_code, 200)

    def test_analysis(self):
        r = self.post("光绪二十四年四月二十三日，内阁奉上谕")
        html = r.content.decode()
        self.assertEqual(r.status_code, 200)
        self.assertIn("converted to traditional", html)
        self.assertIn('id="gloss-data"', html)
        self.assertIn("1898", html)
        self.assertIn("no-store", r["Cache-Control"])

    def test_text_not_in_url_or_get(self):
        r = self.client.get("/assistant/?text=之乎者也")
        self.assertNotIn("之乎者也", r.content.decode())

    def test_needs_token(self):
        # Flask answered 400 from its own check; Django's CsrfViewMiddleware answers 403.
        self.assertEqual(self.client.post("/assistant/", {"text": "之"}).status_code, 403)

    def test_too_long(self):
        self.assertIn("longer than", self.post("之" * 700).content.decode())

    def test_can_be_switched_off(self):
        with override_settings(ASSISTANT_ENABLED=False):
            self.assertEqual(self.client.get("/assistant/").status_code, 404)
            self.assertEqual(self.client.get("/assistant/help").status_code, 404)
            self.assertNotIn("/assistant/", self.client.get("/").content.decode())
            token = "x"
            r = Client().post("/assistant/api/translate", {"text": TEXT}, content_type="application/json",
                              HTTP_X_CSRF_TOKEN=token)
            self.assertEqual(r.status_code, 404)

    def test_result_page_accessibility(self):
        sys.path.insert(0, str(ROOT / "tests"))
        from test_accessibility import parse
        root = parse(self.post("日本人之稱我中國也，一則曰老大帝國。光緒二十四年").content.decode())
        nodes = list(root.iter())
        ids = [n.attrs["id"] for n in nodes if "id" in n.attrs]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(sum(n.tag == "h1" for n in nodes), 1)
        textarea = next(n for n in nodes if n.tag == "textarea")
        self.assertTrue(any(n.tag == "label" and n.attrs.get("for") == textarea.attrs["id"] for n in nodes))


class ApiBase(SimpleTestCase):
    extra = {}

    def setUp(self):
        self._cm = django_settings(**self.extra)
        self._cm.enable()
        self.addCleanup(self._cm.disable)
        config().reset_assistant()
        self.addCleanup(config().reset_assistant)
        self.client = Client(enforce_csrf_checks=True)
        html = self.client.get("/assistant/").content.decode()
        self.token = re.search(TOKEN_RE, html).group(1)

    def call(self, step, body, token=None):
        return self.client.post(f"/assistant/api/{step}", body, content_type="application/json",
                                HTTP_X_CSRF_TOKEN=self.token if token is None else token)


class Api(ApiBase):
    def test_translate_endpoint(self):
        set_client(stub({"translation": "When the Japanese speak of our China"}))
        r = self.call("translate", {"text": TEXT})
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertTrue(d["ok"])
        self.assertEqual(d["source"], "ai")
        self.assertIn("Japanese", d["data"]["translation"])
        self.assertIn("no-store", r["Cache-Control"])

    def test_needs_token(self):
        # Flask: 400 (its own check). Django: 403 from CsrfViewMiddleware.
        self.assertEqual(self.call("translate", {"text": "之"}, token="wrong").status_code, 403)

    def test_no_token_at_all(self):
        r = self.client.post("/assistant/api/translate", {"text": TEXT}, content_type="application/json")
        self.assertEqual(r.status_code, 403)

    def test_valid_token_gives_the_flask_json(self):
        set_client(stub({"translation": "x"}))
        d = self.call("translate", {"text": TEXT}).json()
        self.assertEqual(set(d), {"ok", "step", "source", "model", "data", "remaining"})
        self.assertEqual((d["ok"], d["step"], d["source"], d["model"]), (True, "translate", "ai", "test-model"))
        self.assertEqual(d["data"]["translation"], "x")

    def test_unknown_step(self):
        self.assertEqual(self.call("poem", {"text": "之"}).status_code, 404)

    def test_empty_or_long_text(self):
        self.assertEqual(self.call("translate", {"text": " "}).status_code, 400)
        self.assertEqual(self.call("translate", {"text": "之" * 700}).status_code, 400)

    def test_bad_json_is_an_empty_body(self):
        r = self.client.post("/assistant/api/translate", "not json", content_type="application/json",
                             HTTP_X_CSRF_TOKEN=self.token)
        self.assertEqual(r.status_code, 400)
        self.assertFalse(r.json()["ok"])

    def test_model_failure_is_reported(self):
        set_client(stub("bad", "bad"))
        r = self.call("punctuate", {"text": TEXT})
        self.assertEqual(r.status_code, 502)
        self.assertFalse(r.json()["ok"])

    def test_get_not_allowed(self):
        self.assertEqual(self.client.get("/assistant/api/translate").status_code, 405)


class AskAndLimits(ApiBase):
    extra = {"ASSISTANT_DAILY_LIMIT": 3}

    def test_ask(self):
        set_client(stub({"answer": "之 joins 日本人 and 稱."}))
        r = self.call("ask", {"text": TEXT, "question": "What does 之 do?",
                              "history": [{"q": "Who speaks?", "a": "The Japanese."}]})
        d = r.json()
        self.assertTrue(d["ok"])
        self.assertIn("之", d["data"]["answer"])
        sent = config().assistant_shared("client", None).session.requests[0]["json"]["messages"][1]["content"]
        self.assertIn("Earlier question: Who speaks?", sent)
        self.assertIn("Question: What does 之 do?", sent)

    def test_ask_needs_question_and_limits_history(self):
        self.assertEqual(self.call("ask", {"text": "之", "question": " "}).status_code, 400)
        history = [{"q": "q", "a": "a"}] * 10
        self.assertEqual(self.call("ask", {"text": "之", "question": "more?", "history": history}).status_code, 400)

    def test_daily_limit_returns_429(self):
        set_client(stub(*[{"translation": "x"}] * 5))
        codes = [self.call("translate", {"text": TEXT}).status_code for _ in range(4)]
        self.assertEqual(codes, [200, 200, 200, 429])

    def test_remaining_reported(self):
        set_client(stub({"translation": "x"}))
        self.assertEqual(self.call("translate", {"text": TEXT}).json()["remaining"], 2)


@django_settings()
class A3Page(SimpleTestCase):
    def setUp(self):
        self.client = Client()

    def test_help_page(self):
        r = self.client.get("/assistant/help")
        self.assertEqual(r.status_code, 200)
        self.assertIn("How it goes wrong", r.content.decode())

    def test_ai_controls_and_notice(self):
        c = Client(enforce_csrf_checks=True)
        html = c.get("/assistant/").content.decode()
        token = re.search(TOKEN_RE, html).group(1)
        html = c.post("/assistant/", {"csrf": token, "text": "吾心目中有黿鼉"}).content.decode()
        self.assertIn("external AI service", html)
        for step in ("punctuate", "words", "grammar", "names", "translate"):
            self.assertIn(f'data-run="{step}"', html)
        self.assertIn("assistant.js", html)
        self.assertIn('data-text="吾心目中有黿鼉"', html)

    def test_api_url_shape(self):
        c = Client(enforce_csrf_checks=True)
        token = re.search(TOKEN_RE, c.get("/assistant/").content.decode()).group(1)
        html = c.post("/assistant/", {"csrf": token, "text": TEXT}).content.decode()
        self.assertIn('data-api="/assistant/api/"', html)

    def test_url_names(self):
        from django.urls import reverse
        self.assertEqual(reverse("assistant.page"), "/assistant/")
        self.assertEqual(reverse("assistant.help"), "/assistant/help")
        self.assertEqual(reverse("assistant.api", kwargs={"step": "words"}), "/assistant/api/words")


class ApiHardening(ApiBase):
    def test_service_failure_not_counted(self):
        set_client(scripted(503, 503))
        r = self.call("translate", {"text": TEXT})
        self.assertEqual(r.status_code, 502)
        self.assertEqual(r.json()["remaining"], settings.ASSISTANT_DAILY_LIMIT)

    def test_learner_side_failure_counted(self):
        set_client(stub("bad", "bad"))
        r = self.call("translate", {"text": TEXT})
        self.assertEqual(r.status_code, 502)
        self.assertEqual(r.json()["remaining"], settings.ASSISTANT_DAILY_LIMIT - 1)

    def test_busy_when_all_slots_taken(self):
        with override_settings(ASSISTANT_MAX_CONCURRENT=1, ASSISTANT_QUEUE_WAIT=0.1):
            set_client(stub({"translation": "x"}))
            from app.assistant.views import get_gate
            gate = get_gate()
            gate.acquire()
            try:
                r = self.call("translate", {"text": TEXT})
            finally:
                gate.release()
            self.assertEqual(r.status_code, 503)
            self.assertIn("busy", r.json()["error"])
            self.assertEqual(self.call("translate", {"text": TEXT}).status_code, 200)

    def test_busy_refunds_the_call(self):
        with override_settings(ASSISTANT_MAX_CONCURRENT=1, ASSISTANT_QUEUE_WAIT=0.1):
            set_client(stub({"translation": "x"}))
            from app.assistant.views import get_gate, get_limits
            gate = get_gate()
            gate.acquire()
            try:
                self.call("translate", {"text": TEXT})
            finally:
                gate.release()
            self.assertEqual(get_limits().remaining("dev"), settings.ASSISTANT_DAILY_LIMIT)

    def test_gate_released_after_an_error(self):
        with override_settings(ASSISTANT_MAX_CONCURRENT=1, ASSISTANT_QUEUE_WAIT=0.1):
            set_client(stub("bad", "bad", {"translation": "x"}))
            self.assertEqual(self.call("punctuate", {"text": TEXT}).status_code, 502)
            self.assertEqual(self.call("translate", {"text": TEXT}).status_code, 200)

    def test_deadline_is_applied(self):
        seen = []

        class Spy:
            model = "spy"

            def deadline(self, s):
                seen.append(s)
                return OllamaClient("x", "y").deadline(s)

            def chat_json(self, *a, **k):
                return client_mod.Reply({"translation": "x"})

        with override_settings(ASSISTANT_STEP_DEADLINE=12):
            set_client(Spy())
            self.assertEqual(self.call("translate", {"text": TEXT}).status_code, 200)
        self.assertEqual(seen, [12.0])

    def test_concurrent_requests_respect_the_cap(self):
        with override_settings(ASSISTANT_MAX_CONCURRENT=2, ASSISTANT_QUEUE_WAIT=5, ASSISTANT_DAILY_LIMIT=0,
                               ASSISTANT_HOURLY_LIMIT=0):
            state = {"now": 0, "max": 0}
            lock = threading.Lock()

            class Slow:
                model = "slow"

                def deadline(self, s):
                    return OllamaClient("x", "y").deadline(s)

                def chat_json(self, *a, **k):
                    with lock:
                        state["now"] += 1
                        state["max"] = max(state["max"], state["now"])
                    time.sleep(0.1)
                    with lock:
                        state["now"] -= 1
                    return client_mod.Reply({"translation": "x"})

            set_client(Slow())
            codes = []

            def one():
                c = Client(enforce_csrf_checks=True)
                token = re.search(TOKEN_RE, c.get("/assistant/").content.decode()).group(1)
                codes.append(c.post("/assistant/api/translate", {"text": "是也"}, content_type="application/json",
                                    HTTP_X_CSRF_TOKEN=token).status_code)

            threads = [threading.Thread(target=one) for _ in range(8)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            self.assertEqual(codes, [200] * 8)
            self.assertLessEqual(state["max"], 2)

    def test_request_size_limited(self):
        r = self.client.post("/assistant/api/translate", "x" * 300_000, content_type="application/json",
                             HTTP_X_CSRF_TOKEN=self.token)
        self.assertEqual(r.status_code, 413)


class DeploymentSettings(SimpleTestCase):
    def test_timeouts_fit_together(self):
        step = settings.ASSISTANT_STEP_DEADLINE + settings.ASSISTANT_QUEUE_WAIT
        gconf = {}
        exec((ROOT / "deploy" / "gunicorn.conf.py").read_text(), gconf)
        self.assertGreater(gconf["timeout"], step)
        self.assertEqual(gconf["workers"], 1)              # the usage limits are kept in one process
        self.assertGreaterEqual(gconf["threads"], settings.ASSISTANT_MAX_CONCURRENT + 4)
        nginx = (ROOT / "deploy" / "nginx.conf.example").read_text()
        api = re.search(r"location /assistant/api/ \{(.*?)\}", nginx, re.S).group(1)
        self.assertGreaterEqual(int(re.search(r"proxy_read_timeout (\d+)s", api).group(1)), gconf["timeout"])


@oidc_settings(CONTENT_DIR=str(CONTENT))
class Anonymous(SimpleTestCase):
    def test_api_needs_sign_in(self):
        r = Client().post("/assistant/api/translate", {"text": TEXT}, content_type="application/json")
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.json(), {"error": "sign-in required"})


@django_settings()
class CheckCommand(SimpleTestCase):
    def run_command(self, client):
        from unittest import mock
        out = StringIO()
        with mock.patch("app.management.commands.assistant_check.client_from_config", return_value=client):
            call_command("assistant_check", stdout=out)
        return out.getvalue()

    def test_ok(self):
        out = self.run_command(stub({"translation": "Study and practise it in due time"}))
        self.assertIn("Model test-model at http://model.test; API key not set.", out)
        self.assertRegex(out, r"OK: answered in [\d.]+ s \(15 tokens\): Study and practise")

    def test_failure(self):
        with self.assertRaises(CommandError) as cm:
            self.run_command(stub("bad", "bad"))
        self.assertIn("see the log lines above", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
