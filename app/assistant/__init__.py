"""The reading assistant (docs/assistant-plan.md).

The page (A1) shows the deterministic layer: course glossary, grammar forms, dates.
The AI steps (A2) are JSON endpoints under /assistant/api/, called by the page's script.
Texts are sent by POST, so they never appear in URLs or server logs, and nothing the
learner pastes is stored.
"""
from __future__ import annotations

import secrets

from flask import Blueprint, abort, current_app, g, jsonify, render_template, request, session

from ..auth import check_csrf
from . import steps
from .client import ModelError, client_from_config
from ..content.reader import Segment, _segments
from ..content.render import render_inline
from .lookup import Analysis, analyse

bp = Blueprint("assistant", __name__, url_prefix="/assistant")


@bp.before_request
def enabled():
    if not current_app.config.get("ASSISTANT_ENABLED", True):
        abort(404)


def view_model(a: Analysis):
    """Segments and gloss data for the reader interface (the same as in passages)."""
    from ..views import ref_title, ref_url

    course = g.course
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
                         "url": f"/units/{first.unit_id}/{first.number}"},
                "fromLabel": "Course glossary, first in ",
                "fromNote": "" if len(m.entries) == 1 else
                            f". The course glosses this term in {len(m.entries)} senses: choose the one that fits.",
            })
            for i in range(m.start, m.end):
                cover[i].add(f"{gi}-0")
    paragraphs: list[list[Segment]] = [_segments([(c, frozenset(cover[i])) for i, c in enumerate(text)])]
    return paragraphs, glosses


def function_word_rows(a: Analysis):
    """One row per distinct function word, in order of first appearance."""
    rows: dict[tuple[str, tuple[str, ...]], dict] = {}
    for fw in a.function_words:
        k = (fw.form, tuple(fw.grammar_ids))
        if k not in rows:
            rows[k] = {"form": fw.form, "grammar": [g.course.grammar[x] for x in fw.grammar_ids], "count": 0}
        rows[k]["count"] += 1
    return list(rows.values())


@bp.route("/", methods=["GET", "POST"])
def page():
    max_chars = int(current_app.config.get("ASSISTANT_MAX_CHARS", 600))
    analysis = None
    raw = ""
    if request.method == "POST":
        check_csrf()
        raw = request.form.get("text", "")[: max_chars * 4]
        if raw.strip():
            from ..views import glossary_entries
            analysis = analyse(raw, g.course, glossary_entries(), max_chars)
    ctx = dict(raw=raw, analysis=analysis, max_chars=max_chars)
    if analysis and analysis.prepared.text and not analysis.prepared.too_long:
        paragraphs, glosses = view_model(analysis)
        ctx.update(segments=paragraphs, glosses=glosses, words=function_word_rows(analysis),
                   gap_text=[analysis.prepared.text[a:b] for a, b in analysis.gaps])
    resp = current_app.make_response(render_template("assistant.html", **ctx))
    resp.headers["Cache-Control"] = "no-store"   # the page contains the learner's text
    return resp


# --------------------------------------------------------------------------
# AI steps (JSON)
# --------------------------------------------------------------------------

STEPS = ("punctuate", "words", "grammar", "names", "translate")


def get_client():
    """The model client; tests replace it through app.extensions["assistant_client"]."""
    client = current_app.extensions.get("assistant_client")
    if client is None:
        client = current_app.extensions["assistant_client"] = client_from_config(current_app.config)
    return client


@bp.route("/api/<step>", methods=["POST"])
def api(step: str):
    if step not in STEPS:
        abort(404)
    expected = session.get("csrf")
    if not expected or not secrets.compare_digest(request.headers.get("X-CSRF-Token", ""), expected):
        abort(400)
    body = request.get_json(silent=True) or {}
    max_chars = int(current_app.config.get("ASSISTANT_MAX_CHARS", 600))
    raw = str(body.get("text", ""))[: max_chars * 4]
    from ..views import glossary_entries
    analysis = analyse(raw, g.course, glossary_entries(), max_chars)
    p = analysis.prepared
    if not p.text or p.too_long:
        return jsonify(ok=False, error=f"Paste between 1 and {max_chars} characters."), 400
    client = get_client()
    try:
        if step == "punctuate":
            result = steps.punctuate(client, p.text)
        elif step == "words":
            result = steps.gloss_gaps(client, analysis)
        elif step == "grammar":
            result = steps.grammar_notes(client, analysis, g.course)
        elif step == "names":
            result = steps.names(client, analysis)
        else:
            result = steps.translate(client, p.text, literal=bool(body.get("literal")))
    except ModelError as e:
        return jsonify(ok=False, error=str(e)), 502
    resp = jsonify(ok=True, step=step, source="ai", model=client.model, data=result.data)
    resp.headers["Cache-Control"] = "no-store"
    return resp
