"""Page routes."""
from __future__ import annotations

import re
from pathlib import Path

from django.conf import settings
from django.http import Http404, JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils.cache import patch_cache_control

from accounts.decorators import reviewer_required

from .context import current_course, current_request_var
from .content.glossary import build as build_glossary
from .content.glossary import initial as glossary_initial
from .content.glossary import plain_pinyin
from .content.glossary import passages_in_order
from .content.reader import earlier_glosses, gloss_length, original_segments, text_segments
from .content.render import render_inline
from .tools import Conversion, reign_to_western, reigns_from_rows, republic_to_western, western_to_chinese


def the_course():
    """The course for the request being served (set by CourseMiddleware)."""
    return current_course(None)


def current_user() -> dict | None:
    """The signed-in user of the request being served (set by accounts' RequireSignInMiddleware)."""
    return getattr(current_request_var.get(), "user_info", None)


def visible(page) -> bool:
    if settings.SHOW_UNREVIEWED or page.reviewed:
        return True
    user = current_user()
    return bool(user and user.get("reviewer"))


def get_or_404(mapping: dict, key: str):
    page = mapping.get(key)
    if page is None or not visible(page):
        raise Http404
    return page


def ref_url(ref: str) -> str | None:
    """URL for a grammar id or toolkit id used in a gloss table."""
    if ref in the_course().grammar:
        return f"/grammar/{ref}"
    if ref in the_course().toolkit:
        return f"/toolkit/{ref}"
    return None


def ref_title(ref: str) -> str:
    page = the_course().grammar.get(ref) or the_course().toolkit.get(ref)
    return page.title if page else ref


def course_map(request):
    if settings.AUTH_MODE == "oidc" and current_user() is None:   # not signed in (the sign-in check lets this page through)
        return welcome(request)
    return render(request, "course.html")


def welcome(request):
    """The landing page: what the site is, and the way in. Public, so it shows no course content,
    only the introduction and counts."""
    course = the_course()
    counts = {
        "units": sum(1 for u in course.units.values() if visible(u)),
        "passages": sum(1 for p in course.passages.values() if visible(p)),
        "grammar": sum(1 for x in course.grammar.values() if visible(x)),
        "terms": sum(1 for e in glossary_entries() if visible(e.first)),
    }
    return render(request, "welcome.html", dict(
        landing=True, counts=counts, assistant=getattr(settings, "ASSISTANT_ENABLED", True),
        daily=int(getattr(settings, "ASSISTANT_DAILY_LIMIT", 40))))


def unit(request, uid: str):
    course = the_course()
    u = get_or_404(course.units, uid)
    prev_id, next_id = course.neighbours(course.unit_order(), uid)
    passages = [course.passages[p] for p in u.passage_ids if visible(course.passages[p])]
    return render(request, "unit.html", dict(unit=u, passages=passages,
                                             prev=course.units.get(prev_id), next=course.units.get(next_id)))


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
            "gloss": str(render_inline(gl.gloss, page.path, the_course().urls)),
            "ref": ref_url(gl.grammar) if gl.grammar else None,
            "refTitle": ref_title(gl.grammar) if gl.grammar else None,
            "len": gloss_length(gl),
        }
        if source is not None:
            d["from"] = {"title": source.title, "unit": the_course().units[source.unit_id].number,
                         "url": reverse("pages.passage", kwargs={"uid": source.unit_id, "num": source.number})}
        out.append(d)
    return out


def passages_before(p) -> list:
    order = passages_in_order(the_course())
    return order[:order.index(p)] if p in order else []


def passage(request, uid: str, num: str):
    p = get_or_404(the_course().passages, f"{uid}-{num}")
    u = the_course().units[uid]
    prev_id, next_id = the_course().neighbours(u.passage_ids, p.id)
    default_view = p.meta.get("default_view", "modern")
    view = request.GET.get("view", default_view)
    if view not in VIEWS:
        view = default_view if default_view in VIEWS else "modern"
    extra = earlier_glosses(p, [x for x in passages_before(p) if visible(x)])
    return render(request, "passage.html", dict(
        p=p, unit=u,
        prev=the_course().passages.get(prev_id), next=the_course().passages.get(next_id),
        view=view, views=VIEWS, default_view=default_view,
        segments=text_segments(p, extra), original=original_segments(p, extra),
        glosses=gloss_data(p, extra), own=len(p.glosses),
    ))


def grammar_index(request):
    """Grammar points grouped by the unit that introduces them, in course order."""
    course = the_course()
    seen, groups = set(), []
    for uid in course.unit_order():
        u = course.units[uid]
        items = [course.grammar[x] for x in u.grammar_ids if x not in seen and visible(course.grammar[x])]
        seen.update(u.grammar_ids)
        if items and visible(u):
            groups.append((u, items))
    other = sorted((gr for gid, gr in course.grammar.items() if gid not in seen and visible(gr)), key=lambda x: x.title)
    return render(request, "grammar_index.html", dict(groups=groups, other=other))


def grammar(request, gid: str):
    gr = get_or_404(the_course().grammar, gid)
    used = [p for p in the_course().passages_for_grammar(gid) if visible(p)]
    used.sort(key=lambda p: p.id)
    units = [the_course().units[u] for u in the_course().unit_order() if gid in the_course().units[u].grammar_ids]
    return render(request, "grammar.html", dict(gr=gr, used=used, units=units))


def summaries(request):
    """Titles and summaries of grammar and toolkit pages, for link tooltips."""
    course = the_course()
    out = {}
    for gid, gr in course.grammar.items():
        if visible(gr):
            out[f"/grammar/{gid}"] = {"title": gr.title, "summary": str(render_inline(gr.summary, gr.path, course.urls))}
    for tid, t in course.toolkit.items():
        if visible(t):
            out[f"/toolkit/{tid}"] = {"title": t.title, "summary": str(render_inline(t.summary, t.path, course.urls))}
    resp = JsonResponse(out, json_dumps_params={"sort_keys": True})   # Flask's jsonify sorted keys
    patch_cache_control(resp, max_age=300)
    return resp


def toolkit_index(request):
    return render(request, "toolkit_index.html")


def toolkit(request, tid: str):
    t = get_or_404(the_course().toolkit, tid)
    converter = None
    if "qing-reign-periods.csv" in t.data:
        converter = date_converter(reigns_from_rows(the_course().data.get("qing-reign-periods.csv", [])))
    return render(request, "toolkit.html", dict(t=t, converter=converter))


def date_converter(reigns) -> dict:
    """State of the date converter on the dates toolkit page (works as a plain GET form)."""
    args = current_request_var.get().GET
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
    course = the_course()
    if getattr(course, "_glossary", None) is None:
        course._glossary = build_glossary(course)
    return course._glossary


def strip_html(html: str) -> str:
    return re.sub(r"<[^>]+>", "", html)


def glossary(request):
    entries = [e for e in glossary_entries() if visible(e.first)]
    q = request.GET.get("q", "").strip()
    if q:
        pq = plain_pinyin(q).replace(" ", "")
        ql = q.lower()
        entries = [e for e in entries if q in e.term
                   or (pq and pq in plain_pinyin(e.pinyin).replace(" ", ""))
                   or ql in strip_html(str(render_inline(e.gloss))).lower()]
    groups: dict[str, list] = {}
    for e in entries:
        groups.setdefault(glossary_initial(e), []).append(e)
    return render(request, "glossary.html", dict(
        groups=groups, q=q, count=len(entries), plain_pinyin=plain_pinyin, strip_html=strip_html))


def page_url(page) -> str:
    return the_course().urls.get(page.path.resolve(), "/")


@reviewer_required
def review_list(request):
    """Every REVIEW comment in the course, for reviewers."""
    course = the_course()
    groups = []
    ordered = [course.units[u] for u in course.unit_order()]
    for u in ordered:
        groups.append(u)
        groups.extend(course.passages[p] for p in u.passage_ids)
    groups += sorted(course.grammar.values(), key=lambda x: x.id) + sorted(course.toolkit.values(), key=lambda x: x.id)
    pages = [(pg, page_url(pg), pg.path.relative_to(Path(settings.CONTENT_DIR).resolve())) for pg in groups if pg.reviews]
    total = sum(len(pg.reviews) for pg, _, _ in pages)
    return render(request, "review_list.html", dict(pages=pages, total=total, warnings=course.warnings))


def accessibility(request):
    """The accessibility statement (public, as required for public-sector websites)."""
    return render(request, "accessibility.html", dict(contact=getattr(settings, "ACCESSIBILITY_CONTACT", "")))


def not_found(request, exception=None):
    """handler404: the friendly page, with status 404."""
    return render(request, "404.html", status=404)
