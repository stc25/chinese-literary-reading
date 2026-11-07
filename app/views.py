"""Page routes."""
from __future__ import annotations

from flask import Blueprint, abort, current_app, g, render_template, request

from .content.reader import gloss_length, original_segments, text_segments
from .content.render import render_inline

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


def gloss_data(p) -> list[dict]:
    """The glosses as the reader's JavaScript needs them."""
    out = []
    for i, gl in enumerate(p.glosses):
        out.append({
            "term": gl.term,
            "pinyin": gl.pinyin,
            "gloss": str(render_inline(gl.gloss, p.path, g.course.urls)),
            "ref": ref_url(gl.grammar) if gl.grammar else None,
            "refTitle": ref_title(gl.grammar) if gl.grammar else None,
            "len": gloss_length(p, i),
        })
    return out


@bp.route("/units/<uid>/<num>")
def passage(uid: str, num: str):
    p = get_or_404(g.course.passages, f"{uid}-{num}")
    u = g.course.units[uid]
    prev_id, next_id = g.course.neighbours(u.passage_ids, p.id)
    default_view = p.meta.get("default_view", "modern")
    view = request.args.get("view", default_view)
    if view not in VIEWS:
        view = default_view if default_view in VIEWS else "modern"
    return render_template(
        "passage.html", p=p, unit=u,
        prev=g.course.passages.get(prev_id), next=g.course.passages.get(next_id),
        view=view, views=VIEWS, default_view=default_view,
        segments=text_segments(p), original=original_segments(p), glosses=gloss_data(p),
    )


@bp.route("/grammar/<gid>")
def grammar(gid: str):
    gr = get_or_404(g.course.grammar, gid)
    used = [p for p in g.course.passages_for_grammar(gid) if visible(p)]
    used.sort(key=lambda p: p.id)
    return render_template("grammar.html", gr=gr, used=used)


@bp.route("/toolkit/<tid>")
def toolkit(tid: str):
    t = get_or_404(g.course.toolkit, tid)
    return render_template("toolkit.html", t=t)


@bp.app_errorhandler(404)
def not_found(e):
    return render_template("404.html"), 404
