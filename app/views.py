"""Page routes."""
from __future__ import annotations

import re

from flask import Blueprint, abort, current_app, g, jsonify, render_template, request, url_for

from .content.glossary import build as build_glossary
from .content.glossary import initial as glossary_initial
from .content.glossary import plain_pinyin
from .content.glossary import passages_in_order
from .content.reader import earlier_glosses, gloss_length, original_segments, text_segments
from .content.render import render_inline
from .tools import Conversion, reign_to_western, reigns_from_rows, republic_to_western, western_to_chinese

bp = Blueprint("pages", __name__)


def visible(page) -> bool:
    return current_app.config["SHOW_UNREVIEWED"] or page.reviewed


def get_or_404(mapping: dict, key: str):
    page = mapping.get(key)
    if page is None or not visible(page):
        abort(404)
    return page


def ref_url(ref: str) -> str | None:
    """URL for a grammar id or toolkit id used in a gloss table."""
    if ref in g.course.grammar:
        return f"/grammar/{ref}"
    if ref in g.course.toolkit:
        return f"/toolkit/{ref}"
    return None


def ref_title(ref: str) -> str:
    page = g.course.grammar.get(ref) or g.course.toolkit.get(ref)
    return page.title if page else ref


@bp.app_context_processor
def view_helpers():
    return dict(ref_url=ref_url, ref_title=ref_title, visible=visible)


@bp.route("/")
def course_map():
    return render_template("course.html")


@bp.route("/units/<uid>")
def unit(uid: str):
    u = get_or_404(g.course.units, uid)
    prev_id, next_id = g.course.neighbours(g.course.unit_order(), uid)
    passages = [g.course.passages[p] for p in u.passage_ids if visible(g.course.passages[p])]
    return render_template("unit.html", unit=u, passages=passages,
                           prev=g.course.units.get(prev_id), next=g.course.units.get(next_id))


VIEWS = {
    "modern": "Punctuated",
    "unpunctuated": "Unpunctuated",
    "vertical": "Vertical",
    "vertical-unpunctuated": "Vertical, unpunctuated",
}


def gloss_data(p, extra) -> list[dict]:
    """The glosses as the reader's JavaScript needs them, own glosses first, then earlier ones."""
    out = []
    items = [(gl, p, None) for gl in p.glosses] + [(e.gloss, e.source, e.source) for e in extra]
    for gl, page, source in items:
        d = {
            "term": gl.term,
            "pinyin": gl.pinyin,
            "gloss": str(render_inline(gl.gloss, page.path, g.course.urls)),
            "ref": ref_url(gl.grammar) if gl.grammar else None,
            "refTitle": ref_title(gl.grammar) if gl.grammar else None,
            "len": gloss_length(gl),
        }
        if source is not None:
            d["from"] = {"title": source.title, "unit": g.course.units[source.unit_id].number,
                         "url": url_for("pages.passage", uid=source.unit_id, num=source.number)}
        out.append(d)
    return out


def passages_before(p) -> list:
    order = passages_in_order(g.course)
    return order[:order.index(p)] if p in order else []


@bp.route("/units/<uid>/<num>")
def passage(uid: str, num: str):
    p = get_or_404(g.course.passages, f"{uid}-{num}")
    u = g.course.units[uid]
    prev_id, next_id = g.course.neighbours(u.passage_ids, p.id)
    default_view = p.meta.get("default_view", "modern")
    view = request.args.get("view", default_view)
    if view not in VIEWS:
        view = default_view if default_view in VIEWS else "modern"
    extra = earlier_glosses(p, [x for x in passages_before(p) if visible(x)])
    return render_template(
        "passage.html", p=p, unit=u,
        prev=g.course.passages.get(prev_id), next=g.course.passages.get(next_id),
        view=view, views=VIEWS, default_view=default_view,
        segments=text_segments(p, extra), original=original_segments(p, extra),
        glosses=gloss_data(p, extra), own=len(p.glosses),
    )


@bp.route("/grammar")
def grammar_index():
    """Grammar points grouped by the unit that introduces them, in course order."""
    course = g.course
    seen, groups = set(), []
    for uid in course.unit_order():
        u = course.units[uid]
        items = [course.grammar[x] for x in u.grammar_ids if x not in seen and visible(course.grammar[x])]
        seen.update(u.grammar_ids)
        if items and visible(u):
            groups.append((u, items))
    other = sorted((gr for gid, gr in course.grammar.items() if gid not in seen and visible(gr)), key=lambda x: x.title)
    return render_template("grammar_index.html", groups=groups, other=other)


@bp.route("/grammar/<gid>")
def grammar(gid: str):
    gr = get_or_404(g.course.grammar, gid)
    used = [p for p in g.course.passages_for_grammar(gid) if visible(p)]
    used.sort(key=lambda p: p.id)
    units = [g.course.units[u] for u in g.course.unit_order() if gid in g.course.units[u].grammar_ids]
    return render_template("grammar.html", gr=gr, used=used, units=units)


@bp.route("/summaries.json")
def summaries():
    """Titles and summaries of grammar and toolkit pages, for link tooltips."""
    course = g.course
    out = {}
    for gid, gr in course.grammar.items():
        if visible(gr):
            out[f"/grammar/{gid}"] = {"title": gr.title, "summary": str(render_inline(gr.summary, gr.path, course.urls))}
    for tid, t in course.toolkit.items():
        if visible(t):
            out[f"/toolkit/{tid}"] = {"title": t.title, "summary": str(render_inline(t.summary, t.path, course.urls))}
    resp = jsonify(out)
    resp.cache_control.max_age = 300
    return resp


@bp.route("/toolkit")
def toolkit_index():
    return render_template("toolkit_index.html")


@bp.route("/toolkit/<tid>")
def toolkit(tid: str):
    t = get_or_404(g.course.toolkit, tid)
    converter = None
    if "qing-reign-periods.csv" in t.data:
        converter = date_converter(reigns_from_rows(g.course.data.get("qing-reign-periods.csv", [])))
    return render_template("toolkit.html", t=t, converter=converter)


def date_converter(reigns) -> dict:
    """State of the date converter on the dates toolkit page (works as a plain GET form)."""
    args = request.args
    result = None
    mode = args.get("mode")

    def number(name):
        try:
            return int(args.get(name, "").strip())
        except ValueError:
            return None

    if mode == "reign":
        n = number("year")
        result = reign_to_western(reigns, args.get("reign", ""), n) if n is not None else \
            Conversion(False, [], "Enter the year of the reign as a number, e.g. 24.")
    elif mode == "western":
        y = number("western")
        result = western_to_chinese(reigns, y) if y is not None else \
            Conversion(False, [], "Enter a Western year, e.g. 1898.")
    elif mode == "republic":
        n = number("ryear")
        result = republic_to_western(n) if n is not None else \
            Conversion(False, [], "Enter the Republican year as a number, e.g. 8.")
    return {"reigns": reigns, "mode": mode, "result": result, "args": args}


def glossary_entries():
    course = g.course
    if getattr(course, "_glossary", None) is None:
        course._glossary = build_glossary(course)
    return course._glossary


def strip_html(html: str) -> str:
    return re.sub(r"<[^>]+>", "", html)


@bp.route("/glossary")
def glossary():
    entries = [e for e in glossary_entries() if visible(e.first)]
    q = request.args.get("q", "").strip()
    if q:
        pq = plain_pinyin(q).replace(" ", "")
        ql = q.lower()
        entries = [e for e in entries if q in e.term
                   or (pq and pq in plain_pinyin(e.pinyin).replace(" ", ""))
                   or ql in strip_html(str(render_inline(e.gloss))).lower()]
    groups: dict[str, list] = {}
    for e in entries:
        groups.setdefault(glossary_initial(e), []).append(e)
    return render_template("glossary.html", groups=groups, q=q, count=len(entries),
                           plain_pinyin=plain_pinyin, strip_html=strip_html)


@bp.app_errorhandler(404)
def not_found(e):
    return render_template("404.html"), 404
