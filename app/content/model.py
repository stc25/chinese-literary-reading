"""The course as Python objects, built from the parsed Markdown files."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

REVIEWED = {"reviewed", "expert-reviewed"}


@dataclass
class Review:
    """A <!-- REVIEW(...): ... --> comment (shown only in reviewer mode)."""
    line: int
    body: str


@dataclass
class Page:
    """Fields shared by every content page."""
    id: str
    title: str
    status: str
    path: Path
    meta: dict
    sections: dict[str, str]  # section name -> Markdown source
    reviews: list[Review] = field(default_factory=list)

    @property
    def reviewed(self) -> bool:
        return self.status in REVIEWED


@dataclass
class Gloss:
    term: str                       # as written, e.g. "非 … 不"
    parts: list[str]                # ["非", "不"]
    occurrences: list[int]          # 1-based #n restrictions; empty = every occurrence
    pinyin: str
    gloss: str                      # Markdown (inline)
    grammar: str                    # grammar or toolkit id, or ""
    # character spans in Passage.text, one list of (start, end) per matched occurrence
    spans: list[list[tuple[int, int]]] = field(default_factory=list)


@dataclass
class Exercise:
    number: int
    type: str                       # choice, short-answer, translate, punctuate
    prompt: str                     # Markdown
    options: list[tuple[bool, str]] = field(default_factory=list)  # (correct, Markdown)
    answer: str = ""
    explanation: str = ""
    text: str = ""                  # punctuate: the unpunctuated text


@dataclass
class Passage(Page):
    unit_id: str = ""
    number: str = ""                # "p01"
    title_zh: str = ""
    paragraphs: list[str] = field(default_factory=list)          # ## Text, spaces removed
    original: list[str] = field(default_factory=list)            # ## Original text, as written
    glosses: list[Gloss] = field(default_factory=list)
    translation: list[str] = field(default_factory=list)         # Markdown, one per paragraph
    literal: list[str] = field(default_factory=list)
    exercises: list[Exercise] = field(default_factory=list)

    @property
    def text(self) -> str:
        """The passage text as the glosses see it: paragraphs joined with a newline."""
        return "\n".join(self.paragraphs)


@dataclass
class Unit(Page):
    level: str = ""
    number: int = 0                 # position in the course
    passage_ids: list[str] = field(default_factory=list)
    planned_passages: list[str] = field(default_factory=list)    # titles of passages not yet written
    grammar_ids: list[str] = field(default_factory=list)


@dataclass
class Grammar(Page):
    summary: str = ""
    examples: list[tuple[str, str, str, str]] = field(default_factory=list)  # zh, pinyin, translation, source


@dataclass
class Toolkit(Page):
    summary: str = ""
    data: list[str] = field(default_factory=list)
    practice: list["Exercise"] = field(default_factory=list)


@dataclass
class Course:
    title: str
    sections: dict[str, str]
    levels: dict[str, list[str]]    # "beginner" / "intermediate" -> unit ids in order
    toolkit_ids: list[str]
    units: dict[str, Unit]
    passages: dict[str, Passage]
    grammar: dict[str, Grammar]
    toolkit: dict[str, Toolkit]
    urls: dict[Path, str]           # resolved file path -> app URL
    warnings: list[str] = field(default_factory=list)
    data: dict[str, list[dict]] = field(default_factory=dict)   # toolkit data file name -> rows

    def unit_order(self) -> list[str]:
        return [u for level in ("beginner", "intermediate") for u in self.levels.get(level, [])]

    def neighbours(self, seq: list[str], item: str) -> tuple[str | None, str | None]:
        if item not in seq:
            return None, None
        i = seq.index(item)
        return (seq[i - 1] if i > 0 else None, seq[i + 1] if i + 1 < len(seq) else None)

    def passages_for_grammar(self, gid: str) -> list[Passage]:
        return [p for p in self.passages.values() if gid in (p.meta.get("grammar") or [])
                or any(g.grammar == gid for g in p.glosses)]
