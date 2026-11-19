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
