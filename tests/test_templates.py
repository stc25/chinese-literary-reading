import os
import unittest

os.environ.setdefault("MLC_TESTING", "1")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()   # a no-op under `manage.py test`; needed under `unittest discover`

from django.test import RequestFactory, SimpleTestCase, override_settings
from django.template.loader import render_to_string
from django.urls import path

from app.jinja import url_for


def _view(request, **kw):
    raise NotImplementedError


urlpatterns = [
    path("", _view, name="pages.course_map"),
    path("units/<str:uid>", _view, name="pages.unit"),
    path("login", _view, name="auth.login"),
    path("summaries.json", _view, name="pages.summaries"),
    path("grammar", _view, name="pages.grammar_index"),
    path("grammar/<str:gid>", _view, name="pages.grammar"),
    path("glossary", _view, name="pages.glossary"),
    path("toolkit", _view, name="pages.toolkit_index"),
    path("assistant/", _view, name="assistant.page"),
    path("unit-passage/<str:uid>/<int:num>", _view, name="pages.passage"),
    path("logout", _view, name="auth.logout"),
    path("reviewer-mode", _view, name="auth.toggle_reviewer_mode"),
    path("review", _view, name="pages.review_list"),
    path("accessibility", _view, name="pages.accessibility"),
]


@override_settings(ROOT_URLCONF=__name__)
class UrlFor(SimpleTestCase):
    def test_path_kwargs(self):
        self.assertEqual(url_for("pages.unit", uid="u01"), "/units/u01")

    def test_static(self):
        self.assertEqual(url_for("static", filename="css/site.css"), "/static/css/site.css")

    def test_extra_kwargs_become_query(self):
        self.assertEqual(url_for("auth.login", next="/x"), "/login?next=%2Fx")
        self.assertEqual(url_for("pages.unit", uid="u01", next="/x"), "/units/u01?next=%2Fx")


@override_settings(ROOT_URLCONF=__name__)
class Render(SimpleTestCase):
    def test_404_renders_with_bare_request(self):
        request = RequestFactory().get("/nowhere")

        class Course:
            title = "Course"
            urls = {}

        request.course = Course()
        html = render_to_string("404.html", {}, request=request)
        self.assertIn("Page not found", html)
        self.assertIn('href="/"', html)

    def test_csrf_token_callable_in_templates(self):
        request = RequestFactory().get("/")
        from app.context import template_context
        ctx = template_context(request)
        self.assertTrue(ctx["csrf_token"]())
        self.assertIsNone(ctx["current_user"])
        self.assertFalse(ctx["reviewer_mode"])


if __name__ == "__main__":
    unittest.main()
