"""Prepare a passage for the interactive reader.

The text is cut into segments: maximal runs of characters that are covered by
the same set of gloss occurrences and are either all punctuation or none.
Each glossed segment becomes a button; activating it shows every gloss that
covers it, longest first (docs/content-spec.md, 5.3).
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass

from .model import Gloss, Passage


def is_punct(c: str) -> bool:
    """Anything but a letter or digit (the validator's strip_punct keeps only these)."""
    return unicodedata.category(c)[0] not in "LN"


@dataclass
class Segment:
    text: str
    occ: tuple[str, ...]      # gloss occurrence ids covering it, e.g. ("3-0", "7-1")
    punct: bool


@dataclass
class EarlierGloss:
    """A gloss from an earlier passage, offered where this passage has none (spec 5.3, "What to gloss")."""
    gloss: Gloss
    source: Passage
    spans: list[list[tuple[int, int]]]


def earlier_glosses(p: Passage, earlier: list[Passage], min_len: int = 2) -> list[EarlierGloss]:
    """Glosses from earlier passages for multi-character terms left unglossed here.

    Single characters are left out: their sense varies too much to reuse safely.
    Longer terms win; a term is used only where none of its characters is glossed
    in this passage or by a longer earlier term.
    """
    taken = [False] * len(p.text)
    for gl in p.glosses:
        for spans in gl.spans:
            for a, b in spans:
                for i in range(a, b):
                    taken[i] = True
    candidates: dict[str, list[tuple[Gloss, Passage]]] = {}
    for src in earlier:
        for gl in src.glosses:
            if len(gl.parts) == 1 and len(gl.term) >= min_len and gl.term in p.text:
                lst = candidates.setdefault(gl.term, [])
                if all(" ".join(x.gloss.split()) != " ".join(gl.gloss.split()) for x, _ in lst):
                    lst.append((gl, src))
    out: list[EarlierGloss] = []
    for term in sorted(candidates, key=lambda t: (-len(t), t)):
        spans = []
        i = p.text.find(term)
        while i != -1:
            j = i + len(term)
            if not any(taken[i:j]):
                spans.append([(i, j)])
                for k in range(i, j):
                    taken[k] = True
            i = p.text.find(term, i + 1)
        if spans:
            for gl, src in candidates[term]:
                out.append(EarlierGloss(gl, src, spans))
    return out


def all_glosses(p: Passage, extra: list[EarlierGloss] | None = None) -> list[tuple[Gloss, list]]:
    """The passage's own glosses followed by the earlier ones, each with its spans."""
    return [(gl, gl.spans) for gl in p.glosses] + [(e.gloss, e.spans) for e in (extra or [])]


def coverage(p: Passage, extra: list[EarlierGloss] | None = None) -> list[set[str]]:
    """For each character of p.text, the ids of the gloss occurrences covering it.

    An occurrence id is "<gloss index>-<occurrence index>"; earlier glosses are
    numbered after the passage's own.
    """
    cover: list[set[str]] = [set() for _ in p.text]
    for gi, (gl, gl_spans) in enumerate(all_glosses(p, extra)):
        for oi, spans in enumerate(gl_spans):
            for a, b in spans:
                for i in range(a, b):
                    cover[i].add(f"{gi}-{oi}")
    return cover


def _segments(chars: list[tuple[str, frozenset[str]]]) -> list[Segment]:
    out: list[Segment] = []
    for c, occ in chars:
        punct = is_punct(c)
        key = tuple(sorted(occ, key=lambda s: tuple(int(x) for x in s.split("-"))))
        if out and out[-1].occ == key and out[-1].punct == punct:
            out[-1].text += c
        else:
            out.append(Segment(c, key, punct))
    return out


def text_segments(p: Passage, extra: list[EarlierGloss] | None = None) -> list[list[Segment]]:
    """Segments for each paragraph of ## Text."""
    cover = coverage(p, extra)
    paras, pos = [], 0
    for para in p.paragraphs:
        chars = [(c, frozenset(cover[pos + i])) for i, c in enumerate(para)]
        paras.append(_segments(chars))
        pos += len(para) + 1  # the "\n" between paragraphs
    return paras


def original_segments(p: Passage, extra: list[EarlierGloss] | None = None) -> list[list[Segment]]:
    """Segments for each paragraph of ## Original text, with glosses carried over.

    The original has the same letters as the text but may differ in punctuation
    and spacing, so its letters are aligned one by one with the letters of the text.
    """
    if not p.original:
        return []
    cover = coverage(p, extra)
    letters = [i for i, c in enumerate(p.text) if not is_punct(c) and c != "\n"]
    li = 0
    paras = []
    for para in p.original:
        chars = []
        for c in para:
            if not is_punct(c) and li < len(letters):
                chars.append((c, frozenset(cover[letters[li]])))
                li += 1
            else:
                chars.append((c, frozenset()))
        paras.append(_segments(chars))
    return paras


def gloss_length(gl: Gloss) -> int:
    return sum(len(part) for part in gl.parts)
