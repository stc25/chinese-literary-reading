"""Load the course from content/ using the validator's parser and index.

The app refuses to load content that the validator reports errors in, so the
pages always rest on files that meet docs/content-spec.md.
"""
from __future__ import annotations

import csv
import re
from collections import defaultdict
from pathlib import Path
from urllib.parse import unquote

from tools import validate as v

from .model import Course, Exercise, Gloss, Grammar, Page, Passage, Review, Toolkit, Unit


class ContentError(Exception):
    """The content has validation errors."""

    def __init__(self, messages: list[str]):
        self.messages = messages
        super().__init__(f"{len(messages)} validation error(s) in the content:\n" + "\n".join(messages[:20]))


def section_md(doc: v.Doc, name: str) -> str:
    sec = doc.sections.get(name)
    return "\n".join(l for _, l in sec.lines).strip() if sec else ""


def find_spans(text: str, parts: list[str]) -> list[list[tuple[int, int]]]:
    """Character spans of every occurrence of a (possibly split) term.

    Matches exactly the occurrences that the validator's find_term counts.
    """
    found = []
    i = text.find(parts[0])
    while i != -1:
        spans, j, ok = [(i, i + len(parts[0]))], i + len(parts[0]), True
        for part in parts[1:]:
            k = text.find(part, j)
            if k == -1:
                ok = False
                break
            spans.append((k, k + len(part)))
            j = k + len(part)
        if ok:
            found.append(spans)
        i = text.find(parts[0], i + 1)
    return found


def parse_glosses(doc: v.Doc, text: str, rep: v.Report) -> list[Gloss]:
    sec = doc.sections.get("Glosses")
    if not sec or not sec.nonblank():
        return []
    glosses = []
    for _, (term, pinyin, gloss, grammar) in v.parse_table(doc, sec, v.GLOSS_HEADER, rep):
        m = v.TERM.match(term)
        base = m.group("base").strip()
        occ = [int(x) for x in re.findall(r"#(\d+)", m.group("occ") or "")]
        parts = [p.strip() for p in base.split("…")]
        found = find_spans(text, parts)
        spans = [found[k - 1] for k in occ if 0 < k <= len(found)] if occ else found
        glosses.append(Gloss(base, parts, occ, pinyin, gloss, grammar, spans))
    return glosses


def parse_exercises(sec: v.Section | None) -> list[Exercise]:
    """Mirror of the validator's check_exercises, returning the parsed exercises."""
    if not sec:
        return []
    exercises: list[Exercise] = []
    cur: Exercise | None = None
    label = None
    prompt: list[str] = []

    def finish():
        if cur is not None:
            cur.prompt = "\n".join(prompt).strip()

    for _, l in sec.lines:
        s = l.strip()
        m = v.EX_HEAD.match(s)
        if m:
            finish()
            cur = Exercise(int(m.group(1)), m.group(2), "")
            exercises.append(cur)
            label, prompt = None, []
            continue
        if cur is None or not s:
            continue
        lm = v.LABEL.match(s)
        if lm:
            label = lm.group(1).strip().lower()
            if label in ("answer", "explanation", "text"):
                setattr(cur, label, lm.group(2).strip())
            continue
        tm = v.TASK.match(s)
        if tm:
            cur.options.append((tm.group(1).lower() == "x", tm.group(2).strip()))
            label = None
            continue
        if label in ("answer", "explanation", "text"):
            setattr(cur, label, (getattr(cur, label) + "\n" + s).strip())
        elif not cur.options:
            prompt.append(s)
    finish()
    return exercises


def linked_docs(doc: v.Doc, idx: v.Index, name: str, pattern: re.Pattern) -> list[v.Doc]:
    out = []
    sec = doc.sections.get(name)
    for _, l in (sec.nonblank() if sec else []):
        m = pattern.match(l.strip())
        if m:
            target = idx.resolve_link(doc, m.group(1))
            if target is not None:
                out.append(target)
    return out


def page_fields(doc: v.Doc, reviews: dict[Path, list[Review]]) -> dict:
    return dict(
        id=str(doc.meta.get("id", "")),
        title=str(doc.meta.get("title", "")),
        status=str(doc.meta.get("status", "")),
        path=doc.path,
        meta=doc.meta,
        sections={sec.name: section_md(doc, sec.name) for sec in doc.order},
        reviews=reviews.get(doc.path, []),
    )


def load(root: Path, spec: Path = v.DEFAULT_SPEC) -> Course:
    rep, idx = v.build(root, spec)
    if rep.errors:
        raise ContentError([
            f"{v.show_path(i.path)}{':' + str(i.line) if i.line else ''}: {i.msg}" for i in rep.errors
        ])
    reviews: dict[Path, list[Review]] = defaultdict(list)
    for path, line, body in rep.reviews:
        reviews[path].append(Review(line, " ".join(body.split())))

    urls: dict[Path, str] = {}
    units: dict[str, Unit] = {}
    passages: dict[str, Passage] = {}
    grammar: dict[str, Grammar] = {}
    toolkit: dict[str, Toolkit] = {}

    for gid, doc in idx.grammar.items():
        examples = []
        ex = doc.sections.get("Examples")
        if ex and ex.nonblank():
            examples = [tuple(cells) for _, cells in v.parse_table(doc, ex, v.EXAMPLE_HEADER, rep)]
        grammar[gid] = Grammar(**page_fields(doc, reviews), summary=section_md(doc, "Summary"), examples=examples)
        urls[doc.path.resolve()] = f"/grammar/{gid}"

    for tid, doc in idx.toolkit.items():
        toolkit[tid] = Toolkit(**page_fields(doc, reviews), summary=section_md(doc, "Summary"),
                               data=list(doc.meta.get("data") or []),
                               practice=parse_exercises(doc.sections.get("Practice")))
        urls[doc.path.resolve()] = f"/toolkit/{tid}"

    for pid, doc in idx.passages.items():
        text_sec = doc.sections.get("Text")
        paragraphs = ["".join(p.split()) for _, p in text_sec.paragraphs()] if text_sec else []
        orig = doc.sections.get("Original text")
        original = [p.replace("\n", "") for _, p in orig.paragraphs()] if orig else []
        trans = doc.sections.get("Translation")
        lit = doc.sections.get("Literal translation")
        unit_id, number = pid.split("-", 1)
        p = Passage(
            **page_fields(doc, reviews),
            unit_id=unit_id, number=number, title_zh=str(doc.meta.get("title_zh", "")),
            paragraphs=paragraphs, original=original,
            translation=[t for _, t in trans.paragraphs()] if trans else [],
            literal=[t for _, t in lit.paragraphs()] if lit else [],
            exercises=parse_exercises(doc.sections.get("Exercises")),
        )
        p.glosses = parse_glosses(doc, p.text, rep)
        passages[pid] = p
        urls[doc.path.resolve()] = f"/units/{unit_id}/{number}"

    for uid, doc in idx.units.items():
        listed = linked_docs(doc, idx, "Passages", v.NUMBERED_LINK)
        planned = []
        sec = doc.sections.get("Passages")
        for _, l in (sec.nonblank() if sec else []):
            s = l.strip()
            if v.NUMBERED_ITEM.match(s) and not v.LINK.search(s):
                planned.append(re.sub(r"^\d+\.\s*", "", s))
        units[uid] = Unit(
            **page_fields(doc, reviews), level=str(doc.meta.get("level", "")),
            passage_ids=[d.meta["id"] for d in listed if d.kind == "passage"],
            planned_passages=planned,
            grammar_ids=[g for g in (doc.meta.get("grammar") or []) if g in grammar],
        )
        urls[doc.path.resolve()] = f"/units/{uid}"

    course_doc = idx.course
    levels: dict[str, list[str]] = {"beginner": [], "intermediate": []}
    sec = course_doc.sections.get("Units")
    level = None
    for _, l in (sec.nonblank() if sec else []):
        s = l.strip()
        h = re.match(r"^###\s+(.+)$", s)
        if h:
            level = h.group(1).strip().lower()
            continue
        m = v.NUMBERED_LINK.match(s)
        if m and level in levels:
            target = idx.resolve_link(course_doc, m.group(1))
            if target is not None and target.kind == "unit":
                levels[level].append(target.meta["id"])
    toolkit_ids = [d.meta["id"] for d in linked_docs(course_doc, idx, "Toolkit", v.BULLET_LINK) if d.kind == "toolkit"]
    urls[course_doc.path.resolve()] = "/"

    course = Course(
        title=str(course_doc.meta.get("title", "Course")),
        sections={s.name: section_md(course_doc, s.name) for s in course_doc.order},
        levels=levels, toolkit_ids=toolkit_ids,
        units=units, passages=passages, grammar=grammar, toolkit=toolkit, urls=urls,
        warnings=[f"{v.show_path(i.path)}: {i.msg}" for i in rep.warnings],
    )
    for n, uid in enumerate(course.unit_order(), 1):
        units[uid].number = n
    for path in idx.data_files:
        with path.open(encoding="utf-8", newline="") as f:
            course.data[path.name] = list(csv.DictReader(f))
    return course


def content_signature(root: Path) -> tuple[int, float]:
    """Number of files and latest modification time, to detect edits in development."""
    count, latest = 0, 0.0
    for p in root.rglob("*"):
        if p.is_file() and not any(part.startswith(".") for part in p.relative_to(root).parts):
            count += 1
            latest = max(latest, p.stat().st_mtime)
    return count, latest


def resolve_href(base: Path, href: str, urls: dict[Path, str]) -> str | None:
    """App URL for a relative Markdown link from the file at `base`, or None."""
    if re.match(r"^[a-z][a-z0-9+.-]*:", href) or href.startswith(("#", "/")):
        return None
    path, _, anchor = href.partition("#")
    if not path:
        return None
    url = urls.get((base.parent / unquote(path)).resolve())
    if url is None:
        return None
    return url + (f"#{anchor}" if anchor else "")
