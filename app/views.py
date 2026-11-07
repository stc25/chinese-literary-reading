"""Page routes."""
from __future__ import annotations

from flask import Blueprint, abort, current_app, g, render_template

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


@bp.route("/units/<uid>/<num>")
def passage(uid: str, num: str):
    p = get_or_404(g.course.passages, f"{uid}-{num}")
    u = g.course.units[uid]
    prev_id, next_id = g.course.neighbours(u.passage_ids, p.id)
    return render_template("passage.html", p=p, unit=u,
                           prev=g.course.passages.get(prev_id), next=g.course.passages.get(next_id))


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
