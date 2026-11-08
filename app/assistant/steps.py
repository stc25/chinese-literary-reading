"""The assistant's AI steps. Each step builds a prompt from the deterministic analysis,
calls the model, checks the reply against the text, and returns plain data.

Nothing the model says is trusted blindly: words, names and punctuation are kept only
if they match the learner's text, and grammar points only if they were offered.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..content.model import Course
from . import prompts as P
from .client import OllamaClient, Usage
from .lookup import Analysis, is_letter

CLAUSE_BREAK = re.compile(r"[，。、；：？！「」『』《》（）]")
MAX_GRAMMAR_ITEMS = 30


@dataclass
class StepResult:
    data: dict
    usage: Usage = field(default_factory=Usage)


def letters(s: str) -> str:
    return "".join(c for c in s if is_letter(c))


# --------------------------------------------------------------------------
# 1. Punctuation
# --------------------------------------------------------------------------

def punctuate(client: OllamaClient, text: str) -> StepResult:
    """Suggest punctuation for the text. The reply must keep every character unchanged."""
    bare = letters(text)

    def check(d):
        if letters(d["punctuated"]) != bare:
            raise ValueError("the characters were changed")

    reply = client.chat_json(P.SYSTEM, P.PUNCTUATE.format(text=P.text_block(bare)), P.PUNCTUATE_SCHEMA, check)
    return StepResult({"punctuated": reply.data["punctuated"].strip()}, reply.usage)


# --------------------------------------------------------------------------
# 2. Words not in the course glossary
# --------------------------------------------------------------------------

def _overlaps(a: int, b: int, spans: list[tuple[int, int]]) -> bool:
    return any(a < y and x < b for x, y in spans)


CHUNK = 150          # characters per request in the words step


def chunks(text: str, gaps: list[tuple[int, int]], size: int = CHUNK) -> list[tuple[int, int]]:
    """Pieces of the text of about `size` characters, cut after a sentence or clause break,
    that contain at least one gap. A small model glosses a long text only partly, so the
    words step sends one piece at a time."""
    pieces, start = [], 0
    while start < len(text):
        end = min(len(text), start + size)
        if end < len(text):
            cut = max((m.end() for m in re.finditer(r"[。；！？]", text[start:end])), default=0)
            if not cut:
                cut = max((m.end() for m in re.finditer(r"[，、：]", text[start:end])), default=0)
            if cut:
                end = start + cut
        # never cut through a gap
        for a, b in gaps:
            if a < end < b:
                end = b
        pieces.append((start, end))
        start = end
    return [(a, b) for a, b in pieces if _overlaps(a, b, gaps)]


def gloss_gaps(client: OllamaClient, analysis: Analysis) -> StepResult:
    """AI glosses for the parts of the text that the course glossary does not cover."""
    text, gaps = analysis.prepared.text, analysis.gaps
    if not gaps:
        return StepResult({"words": []})

    def check(d):
        for w in d["words"]:
            if not isinstance(w.get("word"), str) or not isinstance(w.get("gloss"), str):
                raise ValueError("malformed word")

    usage = Usage()
    words, seen = [], set()
    for a, b in chunks(text, gaps):
        piece_gaps = [(max(x, a), min(y, b)) for x, y in gaps if x < b and a < y]
        marked, pos = "", a
        for x, y in piece_gaps:
            marked += text[pos:x] + "【" + text[x:y] + "】"
            pos = y
        marked += text[pos:b]
        reply = client.chat_json(P.SYSTEM, P.WORDS.format(marked=marked), P.WORDS_SCHEMA, check)
        usage.add(reply.usage)
        for w in reply.data["words"]:
            word = "".join(w["word"].split())
            if not word or word in seen or not w["gloss"].strip():
                continue
            spans = []
            i = text.find(word)
            while i != -1:
                if _overlaps(i, i + len(word), gaps):
                    spans.append((i, i + len(word)))
                i = text.find(word, i + 1)
            if spans:                      # keep only words that are really in the uncovered parts
                seen.add(word)
                words.append({"word": word, "pinyin": w.get("pinyin", "").strip(), "gloss": w["gloss"].strip(),
                              "spans": spans})
    words.sort(key=lambda w: w["spans"][0][0])
    return StepResult({"words": words}, usage)


# --------------------------------------------------------------------------
# 3. Function words
# --------------------------------------------------------------------------

def clause_at(text: str, start: int, end: int) -> str:
    """The clause around a position, between punctuation marks."""
    a = max((m.end() for m in CLAUSE_BREAK.finditer(text, 0, start)), default=0)
    m = CLAUSE_BREAK.search(text, end)
    b = m.start() if m else len(text)
    return text[a:b] or text[max(0, start - 8):end + 8]


def grammar_notes(client: OllamaClient, analysis: Analysis, course: Course) -> StepResult:
    """Which grammar point each function word belongs to here, with a one-line note."""
    text = analysis.prepared.text
    items, seen = [], set()
    for fw in analysis.function_words:
        clause = clause_at(text, fw.start, fw.end)
        k = (fw.form, clause, tuple(fw.grammar_ids))
        if k in seen:
            continue
        seen.add(k)
        items.append((fw, clause))
        if len(items) >= MAX_GRAMMAR_ITEMS:
            break
    if not items:
        return StepResult({"notes": []})
    lines = []
    for n, (fw, clause) in enumerate(items, 1):
        options = "; ".join(f"{g} ({course.grammar[g].title})" for g in fw.grammar_ids)
        lines.append(f"{n}. {fw.form} in 「{clause}」: {options}")

    def check(d):
        for note in d["notes"]:
            if not isinstance(note.get("number"), int):
                raise ValueError("malformed note")

    reply = client.chat_json(P.SYSTEM, P.GRAMMAR.format(items="\n".join(lines), text=P.text_block(text)),
                             P.GRAMMAR_SCHEMA, check)
    notes = []
    for note in reply.data["notes"]:
        n = note["number"]
        if not 1 <= n <= len(items) or not str(note.get("note", "")).strip():
            continue
        fw, clause = items[n - 1]
        gid = note.get("grammar_id")
        gid = gid if gid in fw.grammar_ids else None                   # only a grammar point we offered
        notes.append({
            "form": fw.form, "start": fw.start, "end": fw.end, "clause": clause,
            "grammar_id": gid,
            "grammar_title": course.grammar[gid].title if gid else None,
            "candidates": fw.grammar_ids,
            "note": str(note["note"]).strip(),
        })
    return StepResult({"notes": notes}, reply.usage)


# --------------------------------------------------------------------------
# 4. Names, titles and allusions
# --------------------------------------------------------------------------

def names(client: OllamaClient, analysis: Analysis) -> StepResult:
    text = analysis.prepared.text
    reply = client.chat_json(P.SYSTEM, P.NAMES.format(text=P.text_block(text)), P.NAMES_SCHEMA)
    dates = [(d.start, d.end) for d in analysis.dates]
    out, seen = [], set()
    for item in reply.data["items"]:
        expr = "".join(str(item.get("text", "")).split())
        if not expr or expr in seen or expr not in text or not str(item.get("note", "")).strip():
            continue
        i = text.find(expr)
        if _overlaps(i, i + len(expr), dates):
            continue      # dates are converted by the date converter, never by the model
        seen.add(expr)
        kind = item.get("kind") if item.get("kind") in P.NAME_KINDS else "other"
        out.append({"text": expr, "kind": kind, "note": str(item["note"]).strip(), "start": text.find(expr)})
    out.sort(key=lambda x: x["start"])
    return StepResult({"items": out}, reply.usage)


# --------------------------------------------------------------------------
# 5. Translation
# --------------------------------------------------------------------------

def translate(client: OllamaClient, text: str, literal: bool = False) -> StepResult:
    prompt = P.TRANSLATE.format(literal=P.TRANSLATE_LITERAL if literal else "", text=P.text_block(text))

    def check(d):
        if not d["translation"].strip():
            raise ValueError("empty translation")

    reply = client.chat_json(P.SYSTEM, prompt, P.TRANSLATE_SCHEMA, check)
    data = {"translation": reply.data["translation"].strip()}
    if literal and reply.data.get("literal"):
        data["literal"] = reply.data["literal"].strip()
    return StepResult(data, reply.usage)


# --------------------------------------------------------------------------
# Follow-up questions
# --------------------------------------------------------------------------

MAX_QUESTIONS = 10
MAX_QUESTION_CHARS = 500


def ask(client: OllamaClient, text: str, history: list[dict], question: str) -> StepResult:
    """Answer a question about the text. The conversation so far is sent by the browser each
    time (nothing is kept on the server), and is cut to the last few exchanges."""
    past = ""
    for turn in history[-4:]:
        q = str(turn.get("q", ""))[:MAX_QUESTION_CHARS]
        a = str(turn.get("a", ""))[:2000]
        past += f"\nEarlier question: {q}\nYour answer: {a}"

    def check(d):
        if not d["answer"].strip():
            raise ValueError("empty answer")

    prompt = P.ASK.format(text=P.text_block(text), history=past, question=question[:MAX_QUESTION_CHARS])
    reply = client.chat_json(P.SYSTEM, prompt, P.ASK_SCHEMA, check)
    return StepResult({"answer": reply.data["answer"].strip()}, reply.usage)
