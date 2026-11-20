"""The reading assistant's Django views: the page, its help page and the AI step endpoints.

Texts are sent by POST, so they never appear in URLs or server logs, and nothing the
learner pastes is stored. The API is protected by Django's CSRF middleware (header X-CSRF-Token).
"""
from __future__ import annotations

import json
import logging
import threading

from django.apps import apps
from django.conf import settings
from django.http import Http404, JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils.cache import patch_cache_control
from django.views.decorators.http import require_http_methods

from . import steps
from .client import ModelError, client_from_config
from .limits import Limits
from .lookup import Analysis, analyse
from ..content.reader import Segment, _segments
from ..content.render import render_inline

log = logging.getLogger("app.assistant")


class SettingsConfig:
    """The mapping `.get(name, default)` over Django settings that the framework-free modules expect."""

    def get(self, name, default=None):
        return getattr(settings, name, default)


def cfg(name, default):
    return getattr(settings, name, default)


def enabled():
    if not cfg("ASSISTANT_ENABLED", True):
        raise Http404


def no_store(resp):
    patch_cache_control(resp, no_store=True)
    return resp


def view_model(request, a: Analysis):
    """Segments and gloss data for the reader interface (the same as in passages)."""
    from ..views import ref_title, ref_url

    course = request.course
    text = a.prepared.text
    glosses, cover = [], [set() for _ in text]
    for m in a.matches:
        for e in m.entries:
            gi = len(glosses)
            first = e.first
            glosses.append({
                "term": text[m.start:m.end],
                "pinyin": e.pinyin,
                "gloss": str(render_inline(e.gloss, first.path, course.urls)),
                "ref": ref_url(e.grammar) if e.grammar else None,
                "refTitle": ref_title(e.grammar) if e.grammar else None,
                "len": m.end - m.start,
                "from": {"title": first.title, "unit": course.units[first.unit_id].number,
                         "url": reverse("pages.passage", kwargs={"uid": first.unit_id, "num": first.number})},
                "fromLabel": "Course glossary, first in ",
                "fromNote": "" if len(m.entries) == 1 else
                            f". The course glosses this term in {len(m.entries)} senses: choose the one that fits.",
            })
            for i in range(m.start, m.end):
                cover[i].add(f"{gi}-0")
    paragraphs: list[list[Segment]] = [_segments([(c, frozenset(cover[i])) for i, c in enumerate(text)])]
    return paragraphs, glosses


def function_word_rows(request, a: Analysis):
    """One row per distinct function word, in order of first appearance."""
    rows: dict[tuple[str, tuple[str, ...]], dict] = {}
    for fw in a.function_words:
        k = (fw.form, tuple(fw.grammar_ids))
        if k not in rows:
            rows[k] = {"form": fw.form, "grammar": [request.course.grammar[x] for x in fw.grammar_ids], "count": 0}
        rows[k]["count"] += 1
    return list(rows.values())


@require_http_methods(["GET", "HEAD", "POST"])
def page(request):
    enabled()
    max_chars = int(cfg("ASSISTANT_MAX_CHARS", 600))
    analysis = None
    raw = ""
    if request.method == "POST":
        raw = request.POST.get("text", "")[: max_chars * 4]
        if raw.strip():
            from ..views import glossary_entries
            analysis = analyse(raw, request.course, glossary_entries(), max_chars)
    ctx = dict(raw=raw, analysis=analysis, max_chars=max_chars)
    if analysis and analysis.prepared.text and not analysis.prepared.too_long:
        paragraphs, glosses = view_model(request, analysis)
        ctx.update(segments=paragraphs, glosses=glosses, words=function_word_rows(request, analysis),
                   gap_text=[analysis.prepared.text[a:b] for a, b in analysis.gaps])
    resp = render(request, "assistant.html", ctx)
    return no_store(resp)   # the page contains the learner's text


@require_http_methods(["GET", "HEAD"])
def help(request):
    enabled()
    return render(request, "assistant_help.html", {"daily": int(cfg("ASSISTANT_DAILY_LIMIT", 40))})


# --------------------------------------------------------------------------
# AI steps (JSON)
# --------------------------------------------------------------------------

STEPS = ("punctuate", "words", "grammar", "names", "translate", "ask")

BUSY = ("The assistant is busy with other requests. Please try again in a minute; the course glossary, "
        "grammar and date steps still work.")


def _shared(name, make):
    return apps.get_app_config("app").assistant_shared(name, make)


def get_limits() -> Limits:
    return _shared("limits", lambda: Limits(
        int(cfg("ASSISTANT_DAILY_LIMIT", 40)),
        int(cfg("ASSISTANT_HOURLY_LIMIT", 150))))


def get_gate() -> threading.BoundedSemaphore:
    """At most ASSISTANT_MAX_CONCURRENT model calls at once, so a burst cannot tie up every thread."""
    return _shared("gate", lambda: threading.BoundedSemaphore(
        max(1, int(cfg("ASSISTANT_MAX_CONCURRENT", 6)))))


def get_client():
    """The model client; tests replace it with AppConfig.set_assistant("client", ...)."""
    return _shared("client", lambda: client_from_config(SettingsConfig()))


@require_http_methods(["POST"])
def api(request, step: str):
    enabled()
    if step not in STEPS:
        raise Http404
    from django.core.exceptions import RequestDataTooBig
    try:
        body = json.loads(request.body)
    except RequestDataTooBig:
        return JsonResponse({"ok": False, "error": "The request is too large."}, status=413)
    except ValueError:
        body = {}
    if not isinstance(body, dict):
        body = {}
    max_chars = int(cfg("ASSISTANT_MAX_CHARS", 600))
    raw = str(body.get("text", ""))[: max_chars * 4]
    from ..views import glossary_entries
    analysis = analyse(raw, request.course, glossary_entries(), max_chars)
    p = analysis.prepared
    if not p.text or p.too_long:
        return JsonResponse(dict(ok=False, error=f"Paste between 1 and {max_chars} characters."), status=400)
    question = ""
    history: list = []
    if step == "ask":
        question = str(body.get("question", "")).strip()
        history = body.get("history") if isinstance(body.get("history"), list) else []
        history = [h for h in history if isinstance(h, dict)]
        if not question:
            return JsonResponse(dict(ok=False, error="Type a question first."), status=400)
        if len(history) >= steps.MAX_QUESTIONS:
            return JsonResponse(dict(ok=False, error=f"You can ask up to {steps.MAX_QUESTIONS} questions about one text. "
                                                     "Analyse the text again to start a new conversation."), status=400)
    user = (getattr(request, "user_info", None) or {}).get("id", "anonymous")
    limits = get_limits()
    refused = limits.check_and_count(user)
    if refused:
        return JsonResponse(dict(ok=False, error=refused), status=429)
    client = get_client()
    gate = get_gate()
    if not gate.acquire(timeout=float(cfg("ASSISTANT_QUEUE_WAIT", 20))):
        limits.refund(user)
        log.warning("assistant: all %s model slots busy", cfg("ASSISTANT_MAX_CONCURRENT", 6))
        return JsonResponse(dict(ok=False, error=BUSY), status=503)
    try:
        with client.deadline(float(cfg("ASSISTANT_STEP_DEADLINE", 90))):
            if step == "punctuate":
                result = steps.punctuate(client, p.text)
            elif step == "words":
                result = steps.gloss_gaps(client, analysis)
            elif step == "grammar":
                result = steps.grammar_notes(client, analysis, request.course)
            elif step == "names":
                result = steps.names(client, analysis)
            elif step == "translate":
                result = steps.translate(client, p.text, literal=bool(body.get("literal")))
            else:
                result = steps.ask(client, p.text, history, question)
    except ModelError as e:
        if e.service_fault:
            limits.refund(user)
        return no_store(JsonResponse(dict(ok=False, error=str(e), remaining=limits.remaining(user)), status=502))
    finally:
        gate.release()
    return no_store(JsonResponse(dict(ok=True, step=step, source="ai", model=client.model, data=result.data,
                                      remaining=limits.remaining(user))))
