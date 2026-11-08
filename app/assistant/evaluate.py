"""Scoring the assistant against the course's reviewed passages (docs/assistant-plan.md, Evaluation).

The functions here are pure and tested; tools/eval_assistant.py runs the model and
writes the report.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .lookup import is_letter

BREAKS = set("，。、；：？！…—")
MAJOR = set("。；：？！")      # breaks between clauses and sentences, not commas
STOP = {
    "a", "an", "the", "of", "to", "and", "or", "in", "on", "at", "for", "with", "by", "as", "is", "be", "it", "its",
    "this", "that", "here", "there", "one", "ones", "used", "use", "sth", "someone", "something", "etc", "e", "g",
    "n", "v", "adj", "adv", "pron", "part", "prep", "conj", "num", "mw", "interj", "lit", "also", "very", "from",
}


# --------------------------------------------------------------------------
# Punctuation
# --------------------------------------------------------------------------

def break_positions(s: str, marks: set[str] = BREAKS) -> set[int]:
    """Indexes of the letters after which a break (，。、；：？！…) follows.

    Index -1 would be before the first letter; quotation marks alone are not breaks.
    """
    out, n = set(), -1
    for c in s:
        if is_letter(c):
            n += 1
        elif c in marks and n >= 0:
            out.add(n)
    return out


@dataclass
class PRF:
    tp: int
    fp: int
    fn: int

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if self.tp + self.fp else 1.0

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else 1.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if p + r else 0.0

    def __add__(self, other: "PRF") -> "PRF":
        return PRF(self.tp + other.tp, self.fp + other.fp, self.fn + other.fn)


def score_sets(predicted: set, gold: set) -> PRF:
    return PRF(len(predicted & gold), len(predicted - gold), len(gold - predicted))


def score_punctuation(predicted: str, gold: str) -> PRF:
    """Break positions of the model's punctuation against the passage's ## Text."""
    return score_sets(break_positions(predicted), break_positions(gold))


def score_major_breaks(predicted: str, gold: str) -> PRF:
    """Clause and sentence ends (。；：？！) compared with any break in the other text.

    A clause end in the model's text counts as right if the passage has any break there,
    and a clause end in the passage counts as found if the model has any break there.
    This forgives commas added after a topic, and a comma where the passage has a semicolon.
    """
    pm, pa = break_positions(predicted, MAJOR), break_positions(predicted)
    gm, ga = break_positions(gold, MAJOR), break_positions(gold)
    return PRF(len(gm & pa), len(pm - ga), len(gm - pa))


# --------------------------------------------------------------------------
# Words and glosses
# --------------------------------------------------------------------------

def boundaries(spans) -> set[int]:
    """Word boundaries (start and end positions) of a set of spans."""
    out = set()
    for a, b in spans:
        out.update((a, b))
    return out


def content_words(gloss: str) -> set[str]:
    """Lower-case English content words of a gloss, without Markdown, labels and stop words."""
    s = re.sub(r"[*_`]", "", gloss.lower())
    s = re.sub(r"\([^)]*\)", " ", s)      # parenthetical remarks (= 為, here "our" …)
    words = re.findall(r"[a-z]+", s)
    out = set()
    for w in words:
        if w in STOP or len(w) < 3:
            continue
        for suffix in ("ing", "ed", "es", "s"):
            if w.endswith(suffix) and len(w) - len(suffix) >= 3:
                w = w[: -len(suffix)]
                break
        out.add(w)
    return out


def glosses_agree(ai: str, course: str) -> bool | None:
    """True if the glosses share a content word, None if that cannot decide (no overlap)."""
    a, c = content_words(ai), content_words(course)
    if not a or not c:
        return None
    return True if a & c else None
