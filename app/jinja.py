"""Jinja2 environment for Django: Flask-style helpers so the existing templates keep working."""
from __future__ import annotations

from urllib.parse import urlencode

from django.conf import settings
from django.urls import get_resolver, reverse
from jinja2 import Environment


def url_for(name: str, **kwargs) -> str:
    """Flask's url_for on Django's reverse(): kwargs not in the URL pattern become a query string."""
    if name == "static":
        return settings.STATIC_URL + kwargs.pop("filename")
    resolver = get_resolver()
    used = set()
    for possibility, _pattern, _defaults, _converters in resolver.reverse_dict.getlist(name):
        for params in (p[1] for p in possibility):
            if set(params) <= set(kwargs):
                used = set(params)
                break
        else:
            continue
        break
    path_kwargs = {k: kwargs[k] for k in used}
    query = {k: v for k, v in kwargs.items() if k not in used and v is not None}
    url = reverse(name, kwargs=path_kwargs)
    return f"{url}?{urlencode(query)}" if query else url


def csrf_token() -> str:
    """Placeholder global; app.context.template_context overrides it with a request-bound one."""
    return ""


def first_index(occ_id: str) -> int:
    return int(occ_id.split("-")[0])


def passage_progress_item(pid):
    from .context import current_course
    course = current_course(None)
    p = course.passages.get(pid) if course else None
    return [pid, len(p.exercises) if p else 0]


def environment(**options) -> Environment:
    env = Environment(**options)
    env.globals.update(url_for=url_for, csrf_token=csrf_token)
    env.filters["first_index"] = first_index
    env.filters["passage_progress_item"] = passage_progress_item
    return env
