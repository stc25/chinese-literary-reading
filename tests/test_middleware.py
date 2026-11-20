import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("MLC_TESTING", "1")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()   # a no-op under `manage.py test`; needed under `unittest discover`

from django.apps import apps
from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, override_settings

from app.content import ContentError
from app.middleware import CourseMiddleware
from app.store import CourseStore

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "valid"
PASSAGE = "units/u01-topic-and-comment/u01-p01-old-empire.md"
CSP = ("default-src 'self'; img-src 'self' data:; object-src 'none'; "
       "base-uri 'self'; form-action 'self'; frame-ancestors 'none'")


def copy_fixture():
    tmp = Path(tempfile.mkdtemp())
    root = tmp / "content"
    shutil.copytree(FIXTURE, root)
    return tmp, root


@override_settings(CONTENT_DIR=str(FIXTURE))
class Health(SimpleTestCase):
    def test_healthz(self):
        r = self.client.get("/healthz")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"status": "ok"})


@override_settings(CONTENT_DIR=str(FIXTURE))
class Headers(SimpleTestCase):
    def test_security_headers_on_pages(self):
        r = self.client.get("/healthz")
        self.assertEqual(r["Content-Security-Policy"], CSP)
        self.assertEqual(r["X-Content-Type-Options"], "nosniff")
        self.assertEqual(r["Referrer-Policy"], "same-origin")
        self.assertEqual(r["Permissions-Policy"], "camera=(), microphone=(), geolocation=()")
        self.assertNotIn("Strict-Transport-Security", r)

    def test_pages_are_private_no_cache(self):
        cc = self.client.get("/healthz")["Cache-Control"]
        self.assertIn("private", cc)
        self.assertIn("no-cache", cc)
        self.assertNotIn("public", cc)

    def test_static_is_public_and_has_headers(self):
        r = self.client.get("/static/css/" + sorted(p.name for p in (ROOT / "app/static/css").iterdir())[0])
        self.assertEqual(r.status_code, 200)
        self.assertIn("public", r["Cache-Control"])
        self.assertNotIn("private", r["Cache-Control"])
        self.assertEqual(r["Content-Security-Policy"], CSP)
        self.assertEqual(r["X-Content-Type-Options"], "nosniff")

    @override_settings(AUTH_MODE="oidc")
    def test_hsts_only_in_oidc_mode(self):
        self.assertIn("max-age", self.client.get("/healthz")["Strict-Transport-Security"])


class Logging(SimpleTestCase):
    """Production logging: errors on django.request (unhandled 500s) reach the stderr handler
    even with DEBUG off (Django's own console handler only works in debug)."""

    def test_unhandled_error_is_written_to_stderr(self):
        import io
        import logging

        from django.urls import path

        handler = next(h for h in logging.getLogger().handlers if h.name == "stderr")
        stream, level = io.StringIO(), handler.level
        old = handler.setStream(stream)
        handler.setLevel(logging.NOTSET)
        self.addCleanup(handler.setLevel, level)
        self.addCleanup(handler.setStream, old)

        def boom(request):
            raise RuntimeError("boom for the log")

        module = type(sys)("boom_urls")
        module.urlpatterns = [path("boom", boom)]
        sys.modules["boom_urls"] = module
        self.addCleanup(sys.modules.pop, "boom_urls")
        with override_settings(ROOT_URLCONF="boom_urls", DEBUG=False, CONTENT_DIR=str(FIXTURE)):
            from django.test import Client
            r = Client(raise_request_exception=False).get("/boom")
        self.assertEqual(r.status_code, 500)
        out = stream.getvalue()
        self.assertIn("ERROR django.request: Internal Server Error: /boom", out)
        self.assertIn("RuntimeError: boom for the log", out)

    def test_app_and_accounts_log_info(self):
        import logging
        self.assertEqual(logging.getLogger("app").level, logging.INFO)
        self.assertEqual(logging.getLogger("accounts").level, logging.INFO)
        self.assertEqual(logging.getLogger().level, logging.WARNING)


class Request(SimpleTestCase):
    def run_middleware(self, path):
        seen = {}

        def view(request):
            seen["request"] = request
            return HttpResponse("ok")

        with override_settings(CONTENT_DIR=str(FIXTURE)):
            CourseMiddleware(view)(RequestFactory().get(path))
        return seen["request"]

    def test_course_and_content_error(self):
        request = self.run_middleware("/healthz")
        self.assertIn("u01", request.course.units)
        self.assertIsNone(request.content_error)

    def test_endpoint_is_the_url_name(self):
        self.assertEqual(self.run_middleware("/healthz").endpoint, "health")
        self.assertIsNone(self.run_middleware("/no/such/page").endpoint)

    def test_full_path_includes_query(self):
        self.assertEqual(self.run_middleware("/healthz?a=1").full_path, "/healthz?a=1")
        self.assertEqual(self.run_middleware("/healthz").full_path, "/healthz")

    def test_current_course_inside_request_only(self):
        from app.context import current_course
        from app.jinja import passage_progress_item
        inside = {}

        def view(request):
            inside["course"] = current_course(None)
            inside["item"] = passage_progress_item("u01-p01")
            return HttpResponse("ok")

        with override_settings(CONTENT_DIR=str(FIXTURE)):
            CourseMiddleware(view)(RequestFactory().get("/healthz"))
            course = apps.get_app_config("app").course_store.course
            self.assertIs(inside["course"], course)
            self.assertGreater(inside["item"][1], 0)


class Reload(SimpleTestCase):
    def setUp(self):
        self.tmp, self.root = copy_fixture()
        self.addCleanup(shutil.rmtree, self.tmp)

    def test_edit_is_seen_by_next_request_in_debug(self):
        with override_settings(CONTENT_DIR=str(self.root), DEBUG=True):
            self.assertEqual(self.client.get("/healthz").status_code, 200)
            store = apps.get_app_config("app").course_store
            self.assertTrue(store.reload)
            old = store.course
            f = self.root / PASSAGE
            f.write_text(f.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            os.utime(f, (f.stat().st_atime + 10, f.stat().st_mtime + 10))
            self.client.get("/healthz")
            self.assertIsNot(store.course, old)

    def test_broken_edit_keeps_old_course_and_healthz_answers(self):
        with override_settings(CONTENT_DIR=str(self.root), DEBUG=True):
            self.client.get("/healthz")
            store = apps.get_app_config("app").course_store
            old = store.course
            f = self.root / PASSAGE
            f.write_text(f.read_text(encoding="utf-8").replace("status: draft", "status: finished"), encoding="utf-8")
            r = self.client.get("/healthz")
            self.assertEqual(r.status_code, 200)
            self.assertIs(store.course, old)
            self.assertIsInstance(store.error, ContentError)

    def test_no_reload_outside_debug(self):
        with override_settings(CONTENT_DIR=str(self.root), DEBUG=False):
            self.client.get("/healthz")
            self.assertFalse(apps.get_app_config("app").course_store.reload)
        with override_settings(CONTENT_DIR=str(self.root), DEBUG=False, RELOAD_CONTENT=True):
            self.client.get("/healthz")
            self.assertTrue(apps.get_app_config("app").course_store.reload)

    def test_broken_content_is_refused(self):
        f = self.root / PASSAGE
        f.write_text(f.read_text(encoding="utf-8").replace("status: draft", "status: finished"), encoding="utf-8")
        with self.assertRaises(ContentError):
            CourseStore(self.root, False)
        with override_settings(CONTENT_DIR=str(self.root)):
            with self.assertRaises(ContentError):
                apps.get_app_config("app").build_store(self.root, False)

    def test_store_can_be_replaced(self):
        config = apps.get_app_config("app")
        store = config.build_store(FIXTURE, False)
        with override_settings(CONTENT_DIR=str(self.root)):
            config.course_store = store
            self.assertIs(config.course_store, store)


if __name__ == "__main__":
    unittest.main()
