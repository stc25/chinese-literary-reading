"""Prepare a passage for the interactive reader.

The text is cut into segments: maximal runs of characters that are covered by
the same set of gloss occurrences and are either all punctuation or none.
Each glossed segment becomes a button; activating it shows every gloss that
covers it, longest first (docs/content-spec.md, 5.3).
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass

from .model import Passage


def is_punct(c: str) -> bool:
    """Anything but a letter or digit (the validator's strip_punct keeps only these)."""
    return unicodedata.category(c)[0] not in "LN"


@dataclass
class Segment:
    text: str
    occ: tuple[str, ...]      # gloss occurrence ids covering it, e.g. ("3-0", "7-1")
    punct: bool


def coverage(p: Passage) -> list[set[str]]:
    """For each character of p.text, the ids of the gloss occurrences covering it.

    An occurrence id is "<gloss index>-<occurrence index>".
    """
    cover: list[set[str]] = [set() for _ in p.text]
    for gi, gl in enumerate(p.glosses):
        for oi, spans in enumerate(gl.spans):
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


def text_segments(p: Passage) -> list[list[Segment]]:
    """Segments for each paragraph of ## Text."""
    cover = coverage(p)
    paras, pos = [], 0
    for para in p.paragraphs:
        chars = [(c, frozenset(cover[pos + i])) for i, c in enumerate(para)]
        paras.append(_segments(chars))
        pos += len(para) + 1  # the "\n" between paragraphs
    return paras


def original_segments(p: Passage) -> list[list[Segment]]:
    """Segments for each paragraph of ## Original text, with glosses carried over.

    The original has the same letters as the text but may differ in punctuation
    and spacing, so its letters are aligned one by one with the letters of the text.
    """
    if not p.original:
        return []
    cover = coverage(p)
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


def gloss_length(p: Passage, gi: int) -> int:
    return sum(len(part) for part in p.glosses[gi].parts)
