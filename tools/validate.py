#!/usr/bin/env python3
"""Validate course content against docs/content-spec.md.

Usage:
    python tools/validate.py [CONTENT_DIR] [--strict] [--reviews] [--quiet]

Exit status is 0 if there are no errors (and, with --strict, no warnings),
otherwise 1.
"""
from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote

try:
    import yaml
except ImportError:  # pragma: no cover
    sys.exit("PyYAML is required: pip install pyyaml")

REPO = Path(__file__).resolve().parent.parent
DEFAULT_SPEC = REPO / "docs" / "content-spec.md"
DEFAULT_CONTENT = REPO / "content"

# --------------------------------------------------------------------------
# Rules taken from the spec
# --------------------------------------------------------------------------

# (section name, required) in the required order
SECTIONS = {
    "course": [("Introduction", True), ("How to use this course", True), ("Units", True), ("Toolkit", True)],
    "unit": [("Introduction", True), ("Objectives", True), ("Passages", True), ("Grammar", True)],
    "passage": [
        ("Introduction", False),
        ("Text", True),
        ("Original text", False),
        ("Glosses", True),
        ("Translation", True),
        ("Literal translation", False),
        ("Notes", False),
        ("Exercises", False),
    ],
    "grammar": [("Summary", True), ("Explanation", True), ("Examples", True), ("See also", False)],
    # toolkit pages: Summary first, any free sections, optional Practice last
    "toolkit": [("Summary", True), ("Practice", False)],
}
FREE_SECTIONS = {"toolkit"}

FIELDS = {
    "course": ["title", "version"],
    "unit": ["id", "title", "level", "prerequisites", "grammar", "genres", "status"],
    "passage": [
        "id", "title", "title_zh", "unit", "level", "genre", "author", "date",
        "source", "rights", "rights_note", "grammar", "default_view", "status",
    ],
    "grammar": ["id", "title", "forms", "level", "status"],
    "toolkit": ["id", "title", "data", "status"],
}
LIST_FIELDS = {"prerequisites", "grammar", "genres", "forms", "data"}
EMPTY_LIST_OK = {"prerequisites", "grammar", "genres", "forms", "data"}
SOURCE_FIELDS = ["work", "edition", "location"]
# frontmatter field -> controlled-values list in spec section 2
CONTROLLED = {
    "level": "level",
    "status": "status",
    "genre": "genre",
    "genres": "genre",
    "rights": "rights",
    "default_view": "default_view",
}

UNIT_ID = re.compile(r"^u\d{2}$")
PASSAGE_ID = re.compile(r"^u\d{2}-p\d{2}$")
GRAMMAR_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SLUG = r"[a-z0-9]+(?:-[a-z0-9]+)*"
TOOLKIT_ID = re.compile(r"^t\d{2}$")
UNIT_DIR = re.compile(rf"^(u\d{{2}})-{SLUG}$")
PASSAGE_FILE = re.compile(rf"^(u\d{{2}}-p\d{{2}})-{SLUG}\.md$")
TOOLKIT_FILE = re.compile(rf"^(t\d{{2}})-{SLUG}\.md$")
DATA_FILE = re.compile(rf"^{SLUG}\.csv$")
CSV_COLUMN = re.compile(r"^[a-z][a-z0-9_]*$")

TEXT_PUNCT = set("，。、；：？！「」『』《》〈〉（）—…·・")
MARKDOWN_CHARS = set("*_[]`#<>|~\\")
ASCII_PUNCT = set(",.;:?!\"'()")
TONE_VOWELS = set("āáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜĀÁǍÀĒÉĚÈĪÍǏÌŌÓǑÒŪÚǓÙ")
# letters, tone marks, apostrophe, space, ellipsis, hyphen, and sentence punctuation for longer examples
PINYIN_CHARS = re.compile(r"^[A-Za-züÜ" + "".join(sorted(TONE_VOWELS)) + r"' …·,;:.?!\-]+$")

GLOSS_HEADER = ["Term", "Pinyin", "Gloss", "Grammar"]
EXAMPLE_HEADER = ["Chinese", "Pinyin", "Translation", "Source"]
EXERCISE_TYPES = {"choice", "short-answer", "translate", "punctuate"}
EXERCISE_LABELS = {"Answer", "Explanation", "Text"}

LINK = re.compile(r"(?<!!)\[([^\]]*)\]\(([^)]*)\)")
WIKILINK = re.compile(r"\[\[[^\]]+\]\]")
PLACEHOLDER = re.compile(r"<(?!https?:)[^<>\n]+>")
TERM = re.compile(r"^(?P<base>.+?)(?P<occ>(?:\s*#\d+)+)?$")
EX_HEAD = re.compile(r"^###\s+(\d+)\.\s+([a-z-]+)\s*$")
LABEL = re.compile(r"^\*\*([A-Za-z ]+):\*\*\s*(.*)$")
TASK = re.compile(r"^[-*]\s+\[( |x|X)\]\s+(.*)$")
NUMBERED_LINK = re.compile(r"^\d+\.\s+\[[^\]]+\]\(([^)]+)\)\s*$")
NUMBERED_ITEM = re.compile(r"^\d+\.\s+\S")
BULLET_LINK = re.compile(r"^[-*]\s+\[[^\]]+\]\(([^)]+)\)\s*$")


def load_controlled(spec: Path) -> dict[str, set[str]]:
    """Read the controlled-values table (section 2) from the spec."""
    text = spec.read_text(encoding="utf-8")
    m = re.search(r"^## 2\. Controlled values\s*$(.*?)^## ", text, re.M | re.S)
    if not m:
        sys.exit(f"Could not find '## 2. Controlled values' in {spec}")
    values: dict[str, set[str]] = {}
    for line in m.group(1).splitlines():
        row = re.match(r"^\|\s*`([a-z_]+)`\s*\|(.*)\|\s*$", line)
        if row:
            values[row.group(1)] = set(re.findall(r"`([^`]+)`", row.group(2)))
    missing = set(CONTROLLED.values()) - values.keys()
    if missing:
        sys.exit(f"Controlled values missing from spec: {', '.join(sorted(missing))}")
    return values


def strip_punct(s: str) -> str:
    """Keep only letters and digits (removes punctuation, symbols, spaces)."""
    return "".join(c for c in s if unicodedata.category(c)[0] in "LN")


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------

@dataclass
class Issue:
    level: str
    path: Path
    line: int | None
    msg: str


class Report:
    def __init__(self) -> None:
        self.issues: list[Issue] = []
        self.reviews: list[tuple[Path, int, str]] = []
        self.kinds: Counter = Counter()
        self.status: Counter = Counter()
        self.planned_passages = 0

    def error(self, path: Path, line: int | None, msg: str) -> None:
        self.issues.append(Issue("error", path, line, msg))

    def warn(self, path: Path, line: int | None, msg: str) -> None:
        self.issues.append(Issue("warning", path, line, msg))

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.level == "error"]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.level == "warning"]


def show_path(p: Path) -> str:
    try:
        return str(p.resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(p)


# --------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------

@dataclass
class Section:
    name: str
    line: int
    lines: list[tuple[int, str]] = field(default_factory=list)

    def nonblank(self) -> list[tuple[int, str]]:
        return [(n, l) for n, l in self.lines if l.strip()]

    def paragraphs(self) -> list[tuple[int, str]]:
        paras, cur, start = [], [], 0
        for n, l in self.lines:
            if l.strip():
                if not cur:
                    start = n
                cur.append(l.strip())
            elif cur:
                paras.append((start, "\n".join(cur)))
                cur = []
        if cur:
            paras.append((start, "\n".join(cur)))
        return paras


@dataclass
class Doc:
    path: Path
    kind: str
    meta: dict
    meta_lines: dict[str, int]
    body: list[tuple[int, str]]
    order: list[Section]
    sections: dict[str, Section] = field(default_factory=dict)
    text: str | None = None  # passage text, paragraphs joined with "\n"

    def line_of(self, key: str) -> int:
        return self.meta_lines.get(key, 1)

    @property
    def planned(self) -> bool:
        return self.meta.get("status") == "planned"

    def filled(self, name: str) -> Section | None:
        """The section if it exists and has content."""
        sec = self.sections.get(name)
        return sec if sec and sec.nonblank() else None


def parse_doc(path: Path, kind: str, rep: Report) -> Doc | None:
    try:
        raw = path.read_bytes().decode("utf-8")
    except UnicodeDecodeError:
        rep.error(path, None, "file is not valid UTF-8")
        return None
    if raw.startswith("﻿"):
        rep.error(path, 1, "remove the byte-order mark (BOM) at the start of the file")
        raw = raw[1:]
    if "\r" in raw:
        rep.error(path, None, "use LF line endings, not CRLF")
        raw = raw.replace("\r\n", "\n").replace("\r", "\n")
    if not unicodedata.is_normalized("NFC", raw):
        rep.error(path, None, "text is not Unicode NFC-normalised")

    def strip_comment(m: re.Match) -> str:
        body = m.group(1).strip()
        if body.startswith("REVIEW"):
            rep.reviews.append((path, raw.count("\n", 0, m.start()) + 1, body))
        return "\n" * m.group(0).count("\n")

    text = re.sub(r"<!--(.*?)-->", strip_comment, raw, flags=re.S)
    lines = text.split("\n")

    if not lines or lines[0].strip() != "---":
        rep.error(path, 1, "missing YAML frontmatter (the file must start with ---)")
        return None
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        rep.error(path, 1, "frontmatter is not closed with ---")
        return None
    try:
        meta = yaml.safe_load("\n".join(lines[1:end])) or {}
    except yaml.YAMLError as e:
        mark = getattr(e, "problem_mark", None)
        line = mark.line + 2 if mark else 1
        rep.error(path, line, f"invalid YAML in frontmatter: {getattr(e, 'problem', e)}")
        return None
    if not isinstance(meta, dict):
        rep.error(path, 1, "frontmatter must be a set of key: value fields")
        return None
    meta_lines = {}
    for i in range(1, end):
        m = re.match(r"^([A-Za-z_][\w-]*)\s*:", lines[i])
        if m:
            meta_lines.setdefault(m.group(1), i + 1)

    body = [(i + 1, lines[i]) for i in range(end + 1, len(lines))]
    order: list[Section] = []
    preamble: list[tuple[int, str]] = []
    cur: Section | None = None
    in_fence = False
    for n, l in body:
        if l.lstrip().startswith("```"):
            in_fence = not in_fence
        if not in_fence and re.match(r"^#\s", l):
            rep.error(path, n, "level-1 headings (# …) are not used; the title comes from the frontmatter")
            continue
        if not in_fence and l.startswith("## "):
            cur = Section(l[3:].strip(), n)
            order.append(cur)
            continue
        (cur.lines if cur else preamble).append((n, l))
    for n, l in preamble:
        if l.strip():
            rep.warn(path, n, "text before the first ## section is ignored")
            break
    return Doc(path, kind, meta, meta_lines, body, order)


def split_row(s: str) -> list[str]:
    s = s.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|") and not s.endswith("\\|"):
        s = s[:-1]
    return [c.replace("\\|", "|").strip() for c in re.split(r"(?<!\\)\|", s)]


def parse_table(doc: Doc, sec: Section, header: list[str], rep: Report) -> list[tuple[int, list[str]]]:
    rows: list[tuple[int, list[str]]] = []
    seen_header = seen_sep = False
    for n, l in sec.lines:
        s = l.strip()
        if not s:
            continue
        if not s.startswith("|"):
            rep.warn(doc.path, n, f"text outside the table in ## {sec.name} is ignored")
            continue
        cells = split_row(s)
        if not seen_header:
            seen_header = True
            if cells != header:
                rep.error(doc.path, n, f"table header must be | {' | '.join(header)} |")
            continue
        if not seen_sep:
            seen_sep = True
            if all(re.fullmatch(r":?-+:?", c) for c in cells):
                continue
            rep.error(doc.path, n, "missing table separator row (|---|---|…) under the header")
        if len(cells) != len(header):
            rep.error(doc.path, n, f"table row has {len(cells)} cells, expected {len(header)}")
            continue
        rows.append((n, cells))
    if not seen_header:
        rep.error(doc.path, sec.line, f"## {sec.name} must contain a table")
    elif not rows:
        rep.error(doc.path, sec.line, f"the table in ## {sec.name} has no rows")
    return rows


# --------------------------------------------------------------------------
# Checks common to all files
# --------------------------------------------------------------------------

def check_meta(doc: Doc, rep: Report, controlled: dict[str, set[str]]) -> None:
    fields = FIELDS[doc.kind]
    for f in fields:
        if f not in doc.meta:
            rep.error(doc.path, 1, f"missing frontmatter field `{f}`")
    for k in doc.meta:
        if k not in fields:
            rep.warn(doc.path, doc.line_of(k), f"unknown frontmatter field `{k}`")

    for k in fields:
        if k not in doc.meta:
            continue
        v, line = doc.meta[k], doc.line_of(k)
        if k in LIST_FIELDS:
            if v is None:
                v = []
            if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
                rep.error(doc.path, line, f"`{k}` must be a list, e.g. {k}: [a, b]")
                continue
            if not v and k not in EMPTY_LIST_OK:
                rep.error(doc.path, line, f"`{k}` must not be empty")
            values = v
        elif k == "source":
            if not isinstance(v, dict):
                rep.error(doc.path, line, "`source` must have the sub-fields " + ", ".join(SOURCE_FIELDS))
                continue
            for sf in SOURCE_FIELDS:
                if not isinstance(v.get(sf), str) or not v[sf].strip():
                    rep.error(doc.path, line, f"`source.{sf}` is missing or empty")
            for sf in v:
                if sf not in SOURCE_FIELDS:
                    rep.warn(doc.path, line, f"unknown field `source.{sf}`")
            values = []
        elif k == "version":
            if not isinstance(v, (str, int, float)):
                rep.error(doc.path, line, "`version` must be a number or text")
            values = []
        else:
            if isinstance(v, int) and k == "date":
                rep.error(doc.path, line, f'put the date in quotes: date: "{v}"')
                continue
            if not isinstance(v, str):
                rep.error(doc.path, line, f"`{k}` must be text")
                continue
            if not v.strip():
                rep.error(doc.path, line, f"`{k}` is empty")
            values = [v]
        if k in CONTROLLED:
            allowed = controlled[CONTROLLED[k]]
            for x in values:
                if x not in allowed:
                    rep.error(doc.path, line, f"`{k}`: '{x}' is not allowed; use one of: {', '.join(sorted(allowed))}")

    def walk(v, key):
        if isinstance(v, str) and PLACEHOLDER.search(v):
            rep.error(doc.path, doc.line_of(key), f"`{key}` still contains a template placeholder: {v}")
        elif isinstance(v, list):
            for x in v:
                walk(x, key)
        elif isinstance(v, dict):
            for x in v.values():
                walk(x, key)

    for k, v in doc.meta.items():
        walk(v, k)


def check_sections(doc: Doc, rep: Report) -> None:
    spec = SECTIONS[doc.kind]
    names = [name for name, _ in spec]
    free = doc.kind in FREE_SECTIONS
    if free:
        for i, sec in enumerate(doc.order):
            if sec.name in doc.sections:
                rep.error(doc.path, sec.line, f'duplicate section "## {sec.name}"')
                continue
            doc.sections[sec.name] = sec
            if sec.name == "Summary" and i != 0:
                rep.error(doc.path, sec.line, '"## Summary" must be the first section')
            if sec.name == "Practice" and i != len(doc.order) - 1:
                rep.error(doc.path, sec.line, '"## Practice" must be the last section')
        names = []
    last = -1
    for sec in doc.order if not free else []:
        if sec.name not in names:
            rep.error(doc.path, sec.line, f'unknown section "## {sec.name}"; allowed: {", ".join(names)}')
            continue
        if sec.name in doc.sections:
            rep.error(doc.path, sec.line, f'duplicate section "## {sec.name}"')
            continue
        idx = names.index(sec.name)
        if idx < last:
            rep.error(doc.path, sec.line, f'"## {sec.name}" is out of order; the order is: {", ".join(names)}')
        last = max(last, idx)
        doc.sections[sec.name] = sec
    if doc.planned:
        return  # placeholders may have missing or empty sections
    for name, required in spec:
        sec = doc.sections.get(name)
        if sec is None:
            if required:
                rep.error(doc.path, 1, f'missing required section "## {name}"')
        elif not sec.nonblank():
            (rep.error if required else rep.warn)(doc.path, sec.line, f'section "## {name}" is empty')
    if free:
        for sec in doc.order:
            if not sec.nonblank() and sec.name not in {name for name, _ in spec}:
                rep.warn(doc.path, sec.line, f'section "## {sec.name}" is empty')


def check_body(doc: Doc, rep: Report) -> None:
    in_fence = False
    for n, l in doc.body:
        if l.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        for m in PLACEHOLDER.finditer(l):
            rep.error(doc.path, n, f"template placeholder left in text: {m.group(0)}")
        if WIKILINK.search(l):
            rep.error(doc.path, n, "wiki-style [[link]]: use a standard Markdown link [text](relative/path.md)")
        for m in LINK.finditer(l):
            target = m.group(2).strip()
            if not target:
                rep.error(doc.path, n, f"link [{m.group(1)}]() has no target")
                continue
            if re.match(r"^[a-z][a-z0-9+.-]*:", target) or target.startswith("#"):
                continue
            p = unquote(target.split("#", 1)[0])
            if p and not (doc.path.parent / p).exists():
                rep.error(doc.path, n, f"broken link: {target}")


# --------------------------------------------------------------------------
# Index of all files
# --------------------------------------------------------------------------

@dataclass
class Index:
    root: Path
    course: Doc | None = None
    units: dict[str, Doc] = field(default_factory=dict)
    passages: dict[str, Doc] = field(default_factory=dict)
    grammar: dict[str, Doc] = field(default_factory=dict)
    toolkit: dict[str, Doc] = field(default_factory=dict)
    data_files: list[Path] = field(default_factory=list)
    by_path: dict[Path, Doc] = field(default_factory=dict)

    def resolve_link(self, doc: Doc, target: str) -> Doc | None:
        p = (doc.path.parent / unquote(target.split("#", 1)[0])).resolve()
        return self.by_path.get(p)


def discover(root: Path, rep: Report, idx: Index) -> list[tuple[Path, str]]:
    found: list[tuple[Path, str]] = []
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root)
        if any(part.startswith(".") for part in rel.parts):
            continue
        if p.is_dir():
            if len(rel.parts) == 2 and rel.parts[0] == "units" and not (p / "unit.md").exists():
                rep.error(p, None, "unit folder has no unit.md")
            continue
        parts = rel.parts
        if parts[:2] == ("toolkit", "data") and len(parts) == 3:
            if p.suffix == ".csv":
                idx.data_files.append(p)
            else:
                rep.warn(p, None, "only .csv files belong in toolkit/data/")
            continue
        if p.suffix != ".md":
            continue
        if rel == Path("course.md"):
            found.append((p, "course"))
        elif rel == Path("glossary.md") or parts[0] == "assistant":
            continue  # generated / not yet specified
        elif parts[0] == "units" and len(parts) == 3:
            found.append((p, "unit" if parts[2] == "unit.md" else "passage"))
        elif parts[0] == "grammar" and len(parts) == 2:
            found.append((p, "grammar"))
        elif parts[0] == "toolkit" and len(parts) == 2:
            found.append((p, "toolkit"))
        else:
            rep.warn(p, None, "file is not in a location defined by the spec; ignored")
    if not (root / "course.md").exists():
        rep.error(root, None, "course.md is missing")
    return found


def register(doc: Doc, idx: Index, rep: Report) -> None:
    """Check the file's id against its location and add it to the index."""
    did = doc.meta.get("id")
    p = doc.path
    if doc.kind == "course":
        idx.course = doc
    elif doc.kind == "unit":
        m = UNIT_DIR.match(p.parent.name)
        if not m:
            rep.error(p, None, f"unit folder name '{p.parent.name}' must look like u01-some-slug")
        if isinstance(did, str):
            if not UNIT_ID.match(did):
                rep.error(p, doc.line_of("id"), f"unit id '{did}' must look like u01")
            elif m and m.group(1) != did:
                rep.error(p, doc.line_of("id"), f"unit id '{did}' does not match folder name '{p.parent.name}'")
            if did in idx.units:
                rep.error(p, doc.line_of("id"), f"duplicate unit id '{did}' (also in {show_path(idx.units[did].path)})")
            else:
                idx.units[did] = doc
    elif doc.kind == "passage":
        m = PASSAGE_FILE.match(p.name)
        if not m:
            rep.error(p, None, f"passage file name '{p.name}' must look like u01-p01-some-slug.md")
        dir_unit = UNIT_DIR.match(p.parent.name)
        if isinstance(did, str):
            if not PASSAGE_ID.match(did):
                rep.error(p, doc.line_of("id"), f"passage id '{did}' must look like u01-p01")
            elif m and m.group(1) != did:
                rep.error(p, doc.line_of("id"), f"passage id '{did}' does not match file name '{p.name}'")
            elif dir_unit and not did.startswith(dir_unit.group(1) + "-"):
                rep.error(p, doc.line_of("id"), f"passage id '{did}' does not belong to unit folder '{p.parent.name}'")
            if did in idx.passages:
                rep.error(p, doc.line_of("id"), f"duplicate passage id '{did}' (also in {show_path(idx.passages[did].path)})")
            else:
                idx.passages[did] = doc
        unit = doc.meta.get("unit")
        if dir_unit and isinstance(unit, str) and unit != dir_unit.group(1):
            rep.error(p, doc.line_of("unit"), f"`unit: {unit}` but the file is in folder '{p.parent.name}'")
    elif doc.kind == "grammar":
        if isinstance(did, str):
            if not GRAMMAR_ID.match(did):
                rep.error(p, doc.line_of("id"), f"grammar id '{did}' must be lowercase letters, digits and hyphens")
            elif p.stem != did:
                rep.error(p, doc.line_of("id"), f"grammar id '{did}' does not match file name '{p.name}'")
            if did in idx.grammar:
                rep.error(p, doc.line_of("id"), f"duplicate grammar id '{did}'")
            else:
                idx.grammar[did] = doc
    elif doc.kind == "toolkit":
        m = TOOLKIT_FILE.match(p.name)
        if not m:
            rep.error(p, None, f"toolkit file name '{p.name}' must look like t01-some-slug.md")
        if isinstance(did, str):
            if not TOOLKIT_ID.match(did):
                rep.error(p, doc.line_of("id"), f"toolkit id '{did}' must look like t01")
            elif m and m.group(1) != did:
                rep.error(p, doc.line_of("id"), f"toolkit id '{did}' does not match file name '{p.name}'")
            if did in idx.toolkit:
                rep.error(p, doc.line_of("id"), f"duplicate toolkit id '{did}'")
            else:
                idx.toolkit[did] = doc
    idx.by_path[p.resolve()] = doc


# --------------------------------------------------------------------------
# File-type checks
# --------------------------------------------------------------------------

def check_course(doc: Doc, idx: Index, rep: Report) -> None:
    sec = doc.sections.get("Units")
    if not sec:
        return
    level = None
    listed: dict[str, int] = {}
    for n, l in sec.lines:
        s = l.strip()
        if not s:
            continue
        h = re.match(r"^###\s+(.+)$", s)
        if h:
            name = h.group(1).strip()
            if name in ("Beginner", "Intermediate"):
                level = name.lower()
            else:
                rep.error(doc.path, n, f'unknown subheading "### {name}"; use ### Beginner or ### Intermediate')
                level = None
            continue
        m = NUMBERED_LINK.match(s)
        if not m:
            rep.warn(doc.path, n, "unexpected line in ## Units; expected a numbered link to a unit.md file")
            continue
        if level is None:
            rep.error(doc.path, n, "unit listed outside a ### Beginner / ### Intermediate subheading")
        unit = idx.resolve_link(doc, m.group(1))
        if unit is None or unit.kind != "unit":
            if (doc.path.parent / unquote(m.group(1))).exists():
                rep.error(doc.path, n, f"{m.group(1)} is not a unit.md file")
            continue
        uid = unit.meta.get("id")
        if uid in listed:
            rep.error(doc.path, n, f"unit {uid} is listed twice (first on line {listed[uid]})")
            continue
        listed[uid] = n
        if level and unit.meta.get("level") != level:
            rep.error(doc.path, n, f"unit {uid} has level '{unit.meta.get('level')}' but is listed under {level.title()}")
    for uid, unit in idx.units.items():
        if uid not in listed:
            rep.warn(unit.path, None, f"unit {uid} is not listed in course.md")

    sec = doc.sections.get("Toolkit")
    if not sec:
        return
    listed_t: set[str] = set()
    for n, l in sec.nonblank():
        m = BULLET_LINK.match(l.strip())
        if not m:
            rep.warn(doc.path, n, "unexpected line in ## Toolkit; expected a bullet link to a toolkit page")
            continue
        t = idx.resolve_link(doc, m.group(1))
        if t is None:
            continue
        if t.kind != "toolkit":
            rep.error(doc.path, n, f"{m.group(1)} is not a toolkit page")
            continue
        tid = t.meta.get("id")
        if tid in listed_t:
            rep.error(doc.path, n, f"toolkit page {tid} is listed twice")
        listed_t.add(tid)
    for tid, t in idx.toolkit.items():
        if tid not in listed_t:
            rep.warn(t.path, None, f"toolkit page {tid} is not listed in course.md")


def check_unit(doc: Doc, idx: Index, rep: Report) -> None:
    uid = doc.meta.get("id")
    obj = doc.filled("Objectives") if doc.planned else doc.sections.get("Objectives")
    if obj and not any(re.match(r"^\s*[-*]\s+\S", l) for _, l in obj.lines):
        rep.error(doc.path, obj.line, "## Objectives must contain a bullet list")

    sec = doc.sections.get("Passages")
    if sec:
        listed: dict[str, int] = {}
        for n, l in sec.nonblank():
            m = NUMBERED_LINK.match(l.strip())
            if not m:
                if NUMBERED_ITEM.match(l.strip()) and not LINK.search(l):
                    rep.planned_passages += 1  # planned passage, not yet written
                else:
                    rep.warn(doc.path, n, "unexpected line in ## Passages; expected a numbered link to a passage file")
                continue
            p = idx.resolve_link(doc, m.group(1))
            if p is None:
                continue  # broken link already reported
            if p.kind != "passage" or p.path.parent != doc.path.parent:
                rep.error(doc.path, n, f"{m.group(1)} is not a passage in this unit's folder")
                continue
            pid = p.meta.get("id")
            if pid in listed:
                rep.error(doc.path, n, f"passage {pid} is listed twice")
            listed[pid] = n
        for pid, p in idx.passages.items():
            if p.path.parent == doc.path.parent and pid not in listed:
                rep.error(p.path, None, f"passage {pid} is not listed in ## Passages of {show_path(doc.path)}")

    meta_grammar = doc.meta.get("grammar") or []
    if isinstance(meta_grammar, list):
        for g in meta_grammar:
            if g not in idx.grammar:
                rep.error(doc.path, doc.line_of("grammar"), f"unknown grammar id '{g}'")
    sec = doc.sections.get("Grammar")
    if sec and isinstance(meta_grammar, list):
        linked = set()
        for n, l in sec.nonblank():
            m = BULLET_LINK.match(l.strip())
            if not m:
                rep.warn(doc.path, n, "unexpected line in ## Grammar; expected a bullet link to a grammar file")
                continue
            g = idx.resolve_link(doc, m.group(1))
            if g is None:
                continue
            if g.kind != "grammar":
                rep.error(doc.path, n, f"{m.group(1)} is not a grammar file")
                continue
            linked.add(g.meta.get("id"))
        for g in set(meta_grammar) - linked:
            rep.warn(doc.path, sec.line, f"grammar point '{g}' is in the frontmatter but not linked in ## Grammar")
        for g in linked - set(meta_grammar):
            rep.warn(doc.path, sec.line, f"grammar point '{g}' is linked in ## Grammar but not listed in the frontmatter")

    prereq = doc.meta.get("prerequisites") or []
    if isinstance(prereq, list):
        for p in prereq:
            if p == uid:
                rep.error(doc.path, doc.line_of("prerequisites"), "a unit cannot be its own prerequisite")
            elif p not in idx.units:
                rep.error(doc.path, doc.line_of("prerequisites"), f"unknown unit '{p}' in prerequisites")


def check_text_chars(doc: Doc, sec: Section, rep: Report) -> None:
    for n, l in sec.lines:
        bad_md, bad_ascii, latin, odd, space = set(), set(), False, set(), False
        for c in l.strip():
            if c in MARKDOWN_CHARS:
                bad_md.add(c)
            elif c in ASCII_PUNCT:
                bad_ascii.add(c)
            elif c.isascii() and c.isalpha():
                latin = True
            elif c.isspace():
                space = True
            elif unicodedata.category(c)[0] in "PS" and c not in TEXT_PUNCT:
                odd.add(c)
        if bad_md:
            rep.error(doc.path, n, f"Markdown formatting is not allowed in ## {sec.name}: {' '.join(sorted(bad_md))}")
        if bad_ascii:
            rep.error(doc.path, n, f"ASCII punctuation in ## {sec.name}: {' '.join(sorted(bad_ascii))} (use full-width ，。；：？！「」 etc.)")
        if latin:
            rep.warn(doc.path, n, f"Latin letters in ## {sec.name}; check this is intended")
        if space and sec.name == "Text":
            rep.warn(doc.path, n, "spaces in ## Text are ignored by the app; remove them")
        if odd and sec.name == "Text":
            rep.warn(doc.path, n, f"punctuation not in the spec's list: {' '.join(sorted(odd))}")


def find_term(text: str, parts: list[str]) -> list[int]:
    """Start positions of every occurrence of a (possibly split) term."""
    positions = []
    i = text.find(parts[0])
    while i != -1:
        j, ok = i + len(parts[0]), True
        for part in parts[1:]:
            k = text.find(part, j)
            if k == -1:
                ok = False
                break
            j = k + len(part)
        if ok:
            positions.append(i)
        i = text.find(parts[0], i + 1)
    return positions


def check_pinyin(doc: Doc, n: int, pinyin: str, term: str, rep: Report) -> None:
    if not pinyin:
        rep.error(doc.path, n, f"no pinyin for “{term}”")
        return
    if "..." in pinyin:
        rep.error(doc.path, n, "use the ellipsis character … in pinyin, not three dots")
        pinyin = pinyin.replace("...", "…")
    if re.search(r"\d", pinyin):
        rep.error(doc.path, n, f"pinyin “{pinyin}” uses tone numbers; use tone marks (ā á ǎ à)")
    elif not PINYIN_CHARS.match(pinyin):
        rep.error(doc.path, n, f"pinyin “{pinyin}” contains unexpected characters")
    elif not TONE_VOWELS & set(pinyin):
        rep.warn(doc.path, n, f"pinyin “{pinyin}” has no tone marks; check it")
    if pinyin.count("…") != term.count("…"):
        rep.error(doc.path, n, f"pinyin “{pinyin}” and term “{term}” must have the same number of … parts")


def check_glosses(doc: Doc, sec: Section, idx: Index, rep: Report) -> None:
    text = doc.text or ""
    claims: dict[str, list[tuple[int, list[int]]]] = defaultdict(list)
    for n, (term, pinyin, gloss, gram) in parse_table(doc, sec, GLOSS_HEADER, rep):
        if not term:
            rep.error(doc.path, n, "gloss row has no term")
            continue
        m = TERM.match(term)
        base = m.group("base").strip()
        occ = [int(x) for x in re.findall(r"#(\d+)", m.group("occ") or "")]
        if "..." in base:
            rep.error(doc.path, n, "use the ellipsis character … in split terms, not three dots")
            base = base.replace("...", "…")
        if "#" in base:
            rep.error(doc.path, n, f"malformed term “{term}”; occurrences go at the end, e.g. 之 #2")
            continue
        parts = [p.strip() for p in base.split("…")]
        if any(not p for p in parts):
            rep.error(doc.path, n, f"split term “{base}” has an empty part")
            continue
        positions = find_term(text, parts)
        if not positions:
            rep.error(doc.path, n, f"term “{base}” is not found in ## Text")
            continue
        for k in occ:
            if k < 1 or k > len(positions):
                rep.error(doc.path, n, f"“{base}” #{k}: ## Text has only {len(positions)} occurrence(s)")
        if len(occ) != len(set(occ)):
            rep.error(doc.path, n, f"“{term}” lists the same occurrence twice")
        claims[base].append((n, occ))
        check_pinyin(doc, n, pinyin, base, rep)
        if not gloss:
            rep.error(doc.path, n, f"no gloss for “{base}”")
        if gram and gram not in idx.grammar and gram not in idx.toolkit:
            rep.error(doc.path, n, f"unknown grammar or toolkit id '{gram}'")

    for base, rows in claims.items():
        bare = [n for n, occ in rows if not occ]
        numbered = [(n, occ) for n, occ in rows if occ]
        if len(bare) > 1:
            rep.warn(doc.path, bare[1], f"“{base}” is glossed more than once for every occurrence; add #n to say which occurrence each gloss is for")
        if bare and numbered:
            rep.warn(doc.path, numbered[0][0], f"“{base}” has both a general gloss and an occurrence-specific (#n) gloss")
        seen: dict[int, int] = {}
        for n, occ in numbered:
            for k in occ:
                if k in seen:
                    rep.error(doc.path, n, f"occurrence #{k} of “{base}” is already glossed on line {seen[k]}")
                seen.setdefault(k, n)


def check_exercises(doc: Doc, sec: Section, rep: Report) -> None:
    exercises: list[dict] = []
    cur = None
    for n, l in sec.lines:
        s = l.strip()
        if s.startswith("###"):
            m = EX_HEAD.match(s)
            if not m:
                rep.error(doc.path, n, 'exercise heading must look like "### 1. choice"')
                cur = None
                continue
            cur = {"line": n, "num": int(m.group(1)), "type": m.group(2), "lines": []}
            exercises.append(cur)
            continue
        if cur is None:
            if s:
                rep.warn(doc.path, n, "text before the first exercise is ignored")
            continue
        cur["lines"].append((n, s))

    for i, ex in enumerate(exercises, 1):
        line, kind = ex["line"], ex["type"]
        if ex["num"] != i:
            rep.warn(doc.path, line, f"exercise is numbered {ex['num']}, expected {i}")
        if kind not in EXERCISE_TYPES:
            rep.error(doc.path, line, f"unknown exercise type '{kind}'; use one of: {', '.join(sorted(EXERCISE_TYPES))}")
            continue
        prompt: list[str] = []
        options: list[tuple[int, bool, str]] = []
        labels: dict[str, list] = {}
        label = None
        for n, s in ex["lines"]:
            if not s:
                continue
            lm = LABEL.match(s)
            if lm:
                label = lm.group(1).strip()
                if label not in EXERCISE_LABELS:
                    rep.warn(doc.path, n, f"unknown label **{label}:**; use Answer, Explanation or Text")
                if label in labels:
                    rep.error(doc.path, n, f"**{label}:** appears twice in this exercise")
                labels[label] = [n, lm.group(2).strip()]
                continue
            tm = TASK.match(s)
            if tm:
                options.append((n, tm.group(1).lower() == "x", tm.group(2).strip()))
                label = None
                continue
            if label:
                labels[label][1] = (labels[label][1] + "\n" + s).strip()
            elif not options:
                prompt.append(s)
            else:
                rep.warn(doc.path, n, "text after the options must start with a label such as **Explanation:**")
        if not prompt:
            rep.error(doc.path, line, "exercise has no prompt")
        for name, (n, value) in labels.items():
            if not value:
                rep.error(doc.path, n, f"**{name}:** is empty")

        if kind == "choice":
            if len(options) < 2:
                rep.error(doc.path, line, "a choice exercise needs at least two options (- [x] / - [ ])")
            elif not any(ok for _, ok, _ in options):
                rep.error(doc.path, line, "no option is marked correct with - [x]")
            for n, _, text in options:
                if not text:
                    rep.error(doc.path, n, "empty option")
        else:
            if options:
                rep.error(doc.path, options[0][0], "checkbox options are only used in choice exercises")
            if "Answer" not in labels:
                rep.error(doc.path, line, f"a {kind} exercise needs an **Answer:**")
        if kind == "punctuate":
            if "Text" not in labels:
                rep.error(doc.path, line, "a punctuate exercise needs a **Text:** line")
            else:
                n, t = labels["Text"]
                if strip_punct(t) != "".join(t.split()):
                    rep.error(doc.path, n, "**Text:** in a punctuate exercise must have no punctuation")
                if "Answer" in labels and strip_punct(labels["Answer"][1]) != strip_punct(t):
                    rep.error(doc.path, labels["Answer"][0], "**Answer:** without punctuation does not match **Text:**")
        elif "Text" in labels:
            rep.warn(doc.path, labels["Text"][0], "**Text:** is only used in punctuate exercises")


def first_difference(a: str, b: str) -> str:
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            return f"first difference at character {i + 1}: “{a[max(0, i - 3):i + 4]}” vs “{b[max(0, i - 3):i + 4]}”"
    return f"one is longer ({len(a)} vs {len(b)} characters)"


def check_passage(doc: Doc, idx: Index, rep: Report) -> None:
    for g in doc.meta.get("grammar") or []:
        if isinstance(g, str) and g not in idx.grammar:
            rep.error(doc.path, doc.line_of("grammar"), f"unknown grammar id '{g}'")
    unit = doc.meta.get("unit")
    if isinstance(unit, str) and UNIT_ID.match(unit) and unit not in idx.units:
        rep.error(doc.path, doc.line_of("unit"), f"unit '{unit}' has no unit.md")

    text_sec = doc.sections.get("Text")
    paras: list[tuple[int, str]] = []
    if text_sec:
        check_text_chars(doc, text_sec, rep)
        paras = [(n, "".join(p.split())) for n, p in text_sec.paragraphs()]
        doc.text = "\n".join(p for _, p in paras)

    orig = doc.sections.get("Original text")
    if orig and doc.text is not None:
        check_text_chars(doc, orig, rep)
        a = strip_punct("".join(p for _, p in orig.paragraphs()))
        b = strip_punct(doc.text)
        if a != b:
            rep.error(doc.path, orig.line, f"## Original text does not contain the same characters as ## Text; {first_difference(a, b)}")

    gl = doc.filled("Glosses") if doc.planned else doc.sections.get("Glosses")
    if gl and doc.text is not None:
        check_glosses(doc, gl, idx, rep)

    for name in ("Translation", "Literal translation"):
        sec = doc.sections.get(name)
        if sec and paras:
            k = len(sec.paragraphs())
            if k != len(paras):
                rep.error(doc.path, sec.line, f"## {name} has {k} paragraph(s) but ## Text has {len(paras)}; they must match one-to-one")

    ex = doc.sections.get("Exercises")
    if ex:
        check_exercises(doc, ex, rep)


def check_grammar(doc: Doc, idx: Index, rep: Report) -> None:
    summary = doc.sections.get("Summary")
    if summary and len(" ".join(l.strip() for _, l in summary.lines)) > 400:
        rep.warn(doc.path, summary.line, "## Summary is long; it is shown in tooltips, so keep it to one or two sentences")
    ex = doc.filled("Examples") if doc.planned else doc.sections.get("Examples")
    if not ex:
        return
    for n, (zh, pinyin, tr, src) in parse_table(doc, ex, EXAMPLE_HEADER, rep):
        if not zh:
            rep.error(doc.path, n, "example has no Chinese")
            continue
        check_pinyin(doc, n, pinyin, zh, rep)
        if not tr:
            rep.error(doc.path, n, "example has no translation")
        if not src:
            rep.error(doc.path, n, "example has no source (passage id or citation)")
        elif PASSAGE_ID.match(src):
            p = idx.passages.get(src)
            if p is None:
                rep.error(doc.path, n, f"source passage '{src}' does not exist")
            elif p.text is not None and strip_punct(zh) not in strip_punct(p.text):
                rep.warn(doc.path, n, f"example is not found in the text of passage {src}")


def check_toolkit(doc: Doc, idx: Index, rep: Report) -> None:
    data = doc.meta.get("data") or []
    if isinstance(data, list):
        names = {p.name for p in idx.data_files}
        for d in data:
            if d not in names:
                rep.error(doc.path, doc.line_of("data"), f"data file '{d}' not found in toolkit/data/")
    practice = doc.sections.get("Practice")
    if practice and practice.nonblank():
        check_exercises(doc, practice, rep)


def check_data_files(idx: Index, rep: Report) -> None:
    import csv

    used = set()
    for t in idx.toolkit.values():
        if isinstance(t.meta.get("data"), list):
            used.update(t.meta["data"])
    for p in idx.data_files:
        if not DATA_FILE.match(p.name):
            rep.error(p, None, "data file names must be lowercase with hyphens, e.g. qing-reign-periods.csv")
        if p.name not in used:
            rep.warn(p, None, "data file is not listed in the `data` field of any toolkit page")
        try:
            text = p.read_bytes().decode("utf-8")
        except UnicodeDecodeError:
            rep.error(p, None, "file is not valid UTF-8")
            continue
        if text.startswith("﻿"):
            rep.error(p, 1, "remove the byte-order mark (BOM); save as plain UTF-8 CSV")
            text = text[1:]
        rows = list(csv.reader(text.splitlines()))
        if not rows:
            rep.error(p, None, "data file is empty")
            continue
        header = rows[0]
        for col in header:
            if not CSV_COLUMN.match(col):
                rep.error(p, 1, f"column name '{col}' must be lowercase snake_case")
        if len(set(header)) != len(header):
            rep.error(p, 1, "duplicate column names")
        if len(rows) == 1:
            rep.warn(p, None, "data file has a header but no rows")
        for i, row in enumerate(rows[1:], 2):
            if row and len(row) != len(header):
                rep.error(p, i, f"row has {len(row)} cells, the header has {len(header)}")


# --------------------------------------------------------------------------
# Driver
# --------------------------------------------------------------------------

def validate(root: Path, spec: Path = DEFAULT_SPEC) -> Report:
    rep = Report()
    controlled = load_controlled(spec)
    if not root.is_dir():
        rep.error(root, None, "content folder not found")
        return rep
    idx = Index(root)
    docs: list[Doc] = []
    for path, kind in discover(root, rep, idx):
        doc = parse_doc(path, kind, rep)
        if doc is None:
            continue
        check_meta(doc, rep, controlled)
        check_sections(doc, rep)
        check_body(doc, rep)
        register(doc, idx, rep)
        docs.append(doc)
        rep.kinds[kind] += 1
        if isinstance(doc.meta.get("status"), str):
            rep.status[doc.meta["status"]] += 1

    # Passages before grammar: grammar examples are checked against passage text.
    for kind, check in (("course", check_course), ("unit", check_unit),
                        ("passage", check_passage), ("grammar", check_grammar),
                        ("toolkit", check_toolkit)):
        for doc in docs:
            if doc.kind == kind:
                check(doc, idx, rep)
    check_data_files(idx, rep)
    return rep


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Validate course content against docs/content-spec.md")
    ap.add_argument("content", nargs="?", type=Path, default=DEFAULT_CONTENT, help="content folder (default: content/)")
    ap.add_argument("--spec", type=Path, default=DEFAULT_SPEC, help="path to the content spec")
    ap.add_argument("--strict", action="store_true", help="treat warnings as errors")
    ap.add_argument("--reviews", action="store_true", help="list REVIEW comments")
    ap.add_argument("--quiet", action="store_true", help="show errors only")
    args = ap.parse_args(argv)

    rep = validate(args.content, args.spec)
    shown = rep.errors if args.quiet else rep.issues
    for i in sorted(shown, key=lambda i: (str(i.path), i.line or 0)):
        loc = show_path(i.path) + (f":{i.line}" if i.line else "")
        print(f"{loc}: {i.level}: {i.msg}")

    if args.reviews and rep.reviews:
        print("\nREVIEW comments:")
        for path, line, body in rep.reviews:
            print(f"  {show_path(path)}:{line}: {' '.join(body.split())}")

    kinds = ", ".join(f"{rep.kinds[k]} {k}" for k in ("course", "unit", "passage", "grammar", "toolkit") if rep.kinds[k])
    status = ", ".join(f"{v} {k}" for k, v in sorted(rep.status.items()))
    print(f"\nChecked: {kinds or 'no files'}.")
    if status:
        print(f"Status: {status}.")
    if rep.planned_passages:
        print(f"Planned passages not yet written: {rep.planned_passages}.")
    if rep.reviews and not args.reviews:
        print(f"{len(rep.reviews)} REVIEW comment(s); use --reviews to list them.")
    print(f"{len(rep.errors)} error(s), {len(rep.warnings)} warning(s).")
    failed = rep.errors or (args.strict and rep.warnings)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
