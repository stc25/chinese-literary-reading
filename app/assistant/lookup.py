"""The assistant's deterministic layer: everything that needs no AI model.

- normalise the learner's text (simplified → traditional, spaces removed);
- gloss words from the reviewed course glossary, longest match first;
- find function words from the grammar files' `forms` lists;
- find reign, Republican and cyclical dates and convert them with the course's date converter.

The AI steps (A2) fill only the gaps this layer leaves.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache

from ..content.glossary import Entry
from ..content.model import Course
from ..tools import BRANCHES, STEMS, cyclical, reign_to_western, reigns_from_rows, republic_to_western

# --------------------------------------------------------------------------
# Normalising the text
# --------------------------------------------------------------------------

# Variant forms treated as the same character when matching against the glossary.
# Both the learner's text and the glossary are reduced to the right-hand forms; what the
# learner sees is never changed. (See toolkit T1, "Variant forms".)
VARIANTS = {
    "爲": "為", "眞": "真", "卽": "即", "旣": "既", "敎": "教", "衞": "衛", "靑": "青", "説": "說",
    "决": "決", "减": "減", "内": "內", "緖": "緒", "尙": "尚", "絶": "絕", "愼": "慎", "吿": "告",
    "淸": "清", "黄": "黃", "争": "爭", "衆": "眾", "裡": "裏", "綫": "線", "峯": "峰", "鷄": "雞",
    "册": "冊", "啓": "啟", "塲": "場", "汚": "污", "敍": "敘", "叙": "敘", "箇": "個", "并": "並",
    "閒": "間",
}


def key(s: str) -> str:
    """The matching form of a string: variants reduced, one character for one character."""
    return "".join(VARIANTS.get(c, c) for c in s)


@lru_cache(maxsize=1)
def _converter():
    try:
        import opencc
    except ImportError:  # pragma: no cover - listed in requirements.txt
        return None
    return opencc.OpenCC("s2t")


@dataclass
class Prepared:
    text: str                 # the text as analysed: traditional characters, no spaces
    original: str             # what the learner pasted
    converted: bool           # True if simplified characters were converted
    too_long: bool = False
    has_punctuation: bool = False


def is_letter(c: str) -> bool:
    return unicodedata.category(c)[0] in "LN"


# Characters that are both simplified forms and ordinary traditional characters (余 "I" / 餘,
# 于 / 於, 云 "to say" / 雲 …). In a traditional text they must not be converted. The course's own
# texts add more (see shared_characters).
SHARED = set("余于云后干里台只面谷丑斗松制范冲系征向咸御准周党出卷姜几胡划才沈奸借仆朴凶困卜症游")


def shared_characters(texts) -> set[str]:
    """Characters used in traditional course texts that OpenCC would still convert."""
    conv = _converter()
    if conv is None:
        return set(SHARED)
    chars = {c for t in texts for c in t if is_letter(c)}
    return SHARED | {c for c in chars if conv.convert(c) != c}


def prepare(raw: str, max_chars: int, shared: set[str] | None = None) -> Prepared:
    """Clean the pasted text and convert simplified characters to traditional ones.

    The text is converted only if it contains at least one character that is clearly simplified;
    a traditional text is never changed, even where it uses characters such as 余 or 于.
    """
    original = raw
    text = "".join(raw.split())
    text = unicodedata.normalize("NFC", text)
    converted_text = text
    conv = _converter()
    shared = SHARED if shared is None else shared
    if conv is not None:
        clearly_simplified = any(conv.convert(c) != c and c not in shared for c in text if is_letter(c))
        if clearly_simplified:
            out = conv.convert(text)
            # keep the result only if the length is unchanged, so that positions stay meaningful
            if len(out) == len(text):
                converted_text = out
    letters = sum(1 for c in converted_text if is_letter(c))
    return Prepared(
        text=converted_text,
        original=original,
        converted=converted_text != text,
        too_long=letters > max_chars,
        has_punctuation=any(not is_letter(c) for c in converted_text),
    )


# --------------------------------------------------------------------------
# Glossary
# --------------------------------------------------------------------------

@dataclass
class Match:
    start: int
    end: int
    entries: list[Entry]      # every course gloss for this term (several senses possible)


def glossary_index(entries: list[Entry]) -> dict[str, list[Entry]]:
    """Glossary entries by matching key. Split terms (A … B) are left out."""
    index: dict[str, list[Entry]] = {}
    for e in entries:
        if "…" in e.term:
            continue
        index.setdefault(key(e.term), []).append(e)
    return index


def find_glossary_matches(text: str, index: dict[str, list[Entry]]) -> list[Match]:
    """Every occurrence of every glossary term in the text, longest terms first."""
    k = key(text)
    longest = max((len(t) for t in index), default=0)
    matches = []
    for i in range(len(k)):
        for n in range(min(longest, len(k) - i), 0, -1):
            entries = index.get(k[i:i + n])
            if entries:
                matches.append(Match(i, i + n, entries))
    matches.sort(key=lambda m: (-(m.end - m.start), m.start))
    return matches


def uncovered(text: str, matches: list[Match]) -> list[tuple[int, int]]:
    """Runs of letters that no glossary term covers (left for the AI)."""
    covered = [False] * len(text)
    for m in matches:
        for i in range(m.start, m.end):
            covered[i] = True
    runs, start = [], None
    for i, c in enumerate(text):
        gap = is_letter(c) and not covered[i]
        if gap and start is None:
            start = i
        elif not gap and start is not None:
            runs.append((start, i))
            start = None
    if start is not None:
        runs.append((start, len(text)))
    return runs


# --------------------------------------------------------------------------
# Function words
# --------------------------------------------------------------------------

# Grammar files about function words: all beginner files, and these intermediate ones.
# Files about vocabulary or conventions (honorifics, philosophical terms, biography …) are left out,
# because their `forms` are ordinary words that would be flagged everywhere.
FUNCTION_FILES_INTERMEDIATE = {
    "argument-structure", "boundary-particles", "vernacular-elements", "legal-language",
    "memorial-formulas", "epistolary-formulas", "edict-formulas", "embedded-citation", "directive-language",
}


@dataclass
class FunctionWord:
    start: int
    end: int
    form: str
    grammar_ids: list[str]    # one or more grammar points that may apply


def function_forms(course: Course) -> dict[str, list[str]]:
    """Matching key of each form → grammar ids, in course order."""
    forms: dict[str, list[str]] = {}
    order = [g for u in course.unit_order() for g in course.units[u].grammar_ids]
    rank = {g: i for i, g in enumerate(order)}
    for gid, gr in sorted(course.grammar.items(), key=lambda kv: rank.get(kv[0], 999)):
        if gr.meta.get("level") != "beginner" and gid not in FUNCTION_FILES_INTERMEDIATE:
            continue
        for form in gr.meta.get("forms") or []:
            f = "".join(c for c in str(form) if is_letter(c))
            if f:
                ids = forms.setdefault(key(f), [])
                if gid not in ids:
                    ids.append(gid)
    return forms


def find_function_words(text: str, forms: dict[str, list[str]]) -> list[FunctionWord]:
    """Function words in the text; a longer form (所以) wins over a shorter one inside it (所)."""
    k = key(text)
    longest = max((len(f) for f in forms), default=0)
    found, i = [], 0
    while i < len(k):
        for n in range(min(longest, len(k) - i), 0, -1):
            ids = forms.get(k[i:i + n])
            if ids:
                found.append(FunctionWord(i, i + n, text[i:i + n], ids))
                i += n
                break
        else:
            i += 1
    return found


# --------------------------------------------------------------------------
# Dates
# --------------------------------------------------------------------------

NUM = "〇零一二三四五六七八九十廿卅"
_DIGIT = {c: i for i, c in enumerate("〇一二三四五六七八九")}
_DIGIT["零"] = 0


def parse_number(s: str) -> int | None:
    """Chinese numbers from 1 to 99: 元, 三, 十, 十二, 二十四, 廿四, 卅."""
    if s == "元":
        return 1
    s = s.replace("廿", "二十").replace("卅", "三十")
    if not s or any(c not in _DIGIT and c != "十" for c in s):
        return None
    if "十" in s:
        tens, _, units = s.partition("十")
        if len(tens) > 1 or len(units) > 1 or (tens and tens not in _DIGIT) or (units and units not in _DIGIT):
            return None
        n = (_DIGIT[tens] if tens else 1) * 10 + (_DIGIT[units] if units else 0)
    elif len(s) == 1:
        n = _DIGIT[s]
    else:
        return None
    return n if 0 < n < 100 else None


@dataclass
class DateMention:
    start: int
    end: int
    text: str
    lines: list[str]          # the conversion, from the course's date converter
    note: str = ""


def find_dates(text: str, course: Course) -> list[DateMention]:
    reigns = reigns_from_rows(course.data.get("qing-reign-periods.csv", []))
    names = "|".join(re.escape(r.reign) for r in reigns) or "(?!)"
    out: list[DateMention] = []
    taken: list[tuple[int, int]] = []

    def add(m, lines, note=""):
        if any(a < m.end() and m.start() < b for a, b in taken):
            return
        taken.append((m.start(), m.end()))
        out.append(DateMention(m.start(), m.end(), m.group(0), lines, note))

    for m in re.finditer(rf"({names})([元{NUM}]+)年", text):
        n = parse_number(m.group(2))
        if n:
            r = reign_to_western(reigns, m.group(1), n)
            add(m, r.lines, r.message)
    for m in re.finditer(rf"民國([元{NUM}]+)年", text):
        n = parse_number(m.group(1))
        if n:
            r = republic_to_western(n)
            add(m, r.lines, r.message)
    first = min((r.first_year for r in reigns), default=1796)
    for m in re.finditer(rf"([{STEMS}][{BRANCHES}])(?=[年歲春夏秋冬])", text):
        years = [y for y in range(first, 1950) if cyclical(y) == m.group(1)]
        if years:
            add(m, [f"{m.group(1)}: " + ", ".join(str(y) for y in years)],
                "A cyclical year repeats every sixty years: choose the one that fits the text.")
    out.sort(key=lambda d: d.start)
    return out


# --------------------------------------------------------------------------
# The whole layer
# --------------------------------------------------------------------------

@dataclass
class Analysis:
    prepared: Prepared
    matches: list[Match] = field(default_factory=list)
    gaps: list[tuple[int, int]] = field(default_factory=list)
    function_words: list[FunctionWord] = field(default_factory=list)
    dates: list[DateMention] = field(default_factory=list)

    @property
    def coverage(self) -> float:
        letters = sum(1 for c in self.prepared.text if is_letter(c))
        gap = sum(b - a for a, b in self.gaps)
        return 1 - gap / letters if letters else 0.0


@lru_cache(maxsize=4)
def _course_shared(course_id: int, texts: tuple[str, ...]) -> frozenset[str]:
    return frozenset(shared_characters(texts))


def analyse(raw: str, course: Course, glossary: list[Entry], max_chars: int = 600) -> Analysis:
    texts = tuple(p.text for p in course.passages.values())
    p = prepare(raw, max_chars, set(_course_shared(id(course), texts)))
    a = Analysis(p)
    if not p.text or p.too_long:
        return a
    a.matches = find_glossary_matches(p.text, glossary_index(glossary))
    a.gaps = uncovered(p.text, a.matches)
    a.function_words = find_function_words(p.text, function_forms(course))
    a.dates = find_dates(p.text, course)
    return a
