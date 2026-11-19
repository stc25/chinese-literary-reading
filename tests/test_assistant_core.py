"""The reading assistant's framework-free tests: lookup layer, model client, steps, limits, scoring."""
import json
import sys
import threading as _threading
import time as _time
import unittest
from datetime import date as _date
from pathlib import Path

import requests as _requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.assistant import client as _client_mod, steps  # noqa: E402
from app.assistant.client import ModelError, OllamaClient  # noqa: E402
from app.assistant.evaluate import (boundaries, break_positions, content_words, glosses_agree,  # noqa: E402
                                    score_punctuation, score_sets)
from app.assistant.limits import Limits  # noqa: E402
from app.assistant.lookup import (analyse, find_dates, find_function_words, find_glossary_matches,  # noqa: E402
                                  function_forms, glossary_index, key, parse_number, prepare, uncovered)
from app.content import load  # noqa: E402
from app.content.glossary import build  # noqa: E402
from tests.assistant_helpers import FakeResponse, FakeSession, ScriptedSession, scripted, stub  # noqa: E402,F401

CONTENT = ROOT / "content"
_CACHE = {}


def _course_and_entries():
    if not _CACHE:
        course = load(ROOT / "content")
        _CACHE["v"] = (course, build(course))
    return _CACHE["v"]


class Normalise(unittest.TestCase):
    def test_simplified_converted(self):
        p = prepare("国家 为 什么\n要发展经济", 600)
        self.assertTrue(p.converted)
        self.assertEqual(p.text, "國家爲什麼要發展經濟")

    def test_shared_characters_kept_in_traditional_text(self):
        from app.assistant.lookup import shared_characters
        shared = shared_characters(p.text for p in load(CONTENT).passages.values())
        for text in ("余嘗游於此", "孔子云", "于是"):
            p = prepare(text, 600, shared)
            self.assertEqual(p.text, text)
            self.assertFalse(p.converted)

    def test_traditional_unchanged(self):
        p = prepare("日本人之稱我中國也", 600)
        self.assertFalse(p.converted)
        self.assertFalse(p.has_punctuation)

    def test_too_long(self):
        self.assertTrue(prepare("之" * 601, 600).too_long)
        self.assertFalse(prepare("之，" * 600, 600).too_long)  # punctuation does not count

    def test_variant_keys(self):
        self.assertEqual(key("爲卽旣"), key("為即既"))

    def test_numbers(self):
        cases = {"元": 1, "三": 3, "十": 10, "十二": 12, "二十四": 24, "廿四": 24, "卅": 30, "九十九": 99}
        for s, n in cases.items():
            self.assertEqual(parse_number(s), n, s)
        for s in ("", "百", "十十", "abc"):
            self.assertIsNone(parse_number(s), s)


class Layer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.course = load(CONTENT)
        cls.glossary = build(cls.course)
        cls.index = glossary_index(cls.glossary)

    def test_longest_match_and_overlaps(self):
        text = "內閣奉上諭"
        matches = find_glossary_matches(text, self.index)
        spans = [(m.start, m.end) for m in matches]
        self.assertEqual(spans[0], (0, 5))          # the whole phrase is a glossary term
        self.assertIn((0, 2), spans)                # and so is 內閣 inside it

    def test_variant_forms_match(self):
        # the glossary has 為 terms; the text uses 爲 (and vice versa)
        terms = {e.term for e in self.glossary}
        sample = next(t for t in terms if "為" in t and len(t) >= 2)
        text = sample.replace("為", "爲")
        self.assertTrue(find_glossary_matches(text, self.index))

    def test_uncovered(self):
        text = "日本人之稱我中國也，乙丙丁"
        gaps = uncovered(text, find_glossary_matches(text, self.index))
        self.assertTrue(all(text[a:b] for a, b in gaps))
        self.assertNotIn("，", "".join(text[a:b] for a, b in gaps))

    def test_function_words(self):
        forms = function_forms(self.course)
        self.assertIn("所以", forms)
        self.assertNotIn(key("家"), forms)        # honorific forms are not function words
        found = find_function_words("此其所以不若也", forms)
        self.assertEqual([f.form for f in found][:3], ["此", "其", "所以"])

    def test_dates(self):
        d = find_dates("光緒二十四年，民國八年，辛酉秋，咸豐元年", self.course)
        texts = {x.text: x.lines[0] for x in d}
        self.assertIn("1898", texts["光緒二十四年"])
        self.assertIn("1919", texts["民國八年"])
        self.assertIn("1861", texts["辛酉"])
        self.assertIn("1851", texts["咸豐元年"])

    def test_every_course_passage_is_fully_covered(self):
        """Each passage's own glosses are in the glossary, so its glossed words must all be found."""
        for p in self.course.passages.values():
            a = analyse(p.text.replace("\n", ""), self.course, self.glossary, max_chars=5000)
            found = {a.prepared.text[m.start:m.end] for m in a.matches}
            for gl in p.glosses:
                if len(gl.parts) == 1 and gl.spans:
                    self.assertIn(key(gl.term), {key(t) for t in found}, f"{p.id}: {gl.term}")


class Client(unittest.TestCase):
    def test_request_shape(self):
        c = stub({"punctuated": "之。"}, api_key="k")
        steps.punctuate(c, "之")
        req = c.session.requests[0]
        self.assertEqual(req["url"], "http://model.test/api/chat")
        self.assertEqual(req["json"]["model"], "test-model")
        self.assertIn("format", req["json"])
        self.assertFalse(req["json"]["stream"])
        self.assertEqual(req["headers"]["Authorization"], "Bearer k")
        self.assertIn("<text>", req["json"]["messages"][1]["content"])
        self.assertIn('"punctuated"', req["json"]["messages"][1]["content"])   # schema stated for cloud models

    def test_retry_then_fail(self):
        c = stub("not json", "still not json")
        with self.assertRaises(ModelError):
            steps.punctuate(c, "之乎")
        self.assertEqual(len(c.session.requests), 2)

    def test_fenced_json_accepted(self):
        from app.assistant.client import parse_json_object
        self.assertEqual(parse_json_object('```json\n{"a": 1}\n```'), {"a": 1})
        self.assertEqual(parse_json_object('Here it is: {"a": 1} '), {"a": 1})
        with self.assertRaises(ValueError):
            parse_json_object("no json here")

    def test_usage_limit(self):
        with self.assertRaises(ModelError) as cm:
            steps.translate(stub("{}", status=429), "之")
        self.assertIn("limit", str(cm.exception))


class Steps(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.course = load(CONTENT)
        cls.glossary = build(cls.course)

    def analysis(self, text):
        return analyse(text, self.course, self.glossary)

    def test_punctuation_must_keep_characters(self):
        c = stub({"punctuated": "日本人稱中國，"}, {"punctuated": "日本人之稱我中國也。"})
        r = steps.punctuate(c, "日本人之稱我中國也")
        self.assertEqual(r.data["punctuated"], "日本人之稱我中國也。")
        self.assertEqual(r.usage.calls, 2)      # the first reply changed the characters

    def test_words_kept_only_in_gaps(self):
        a = self.analysis("黿鼉之")
        self.assertEqual(a.gaps, [(0, 2)])
        c = stub({"words": [
            {"word": "黿鼉", "pinyin": "yuántuó", "gloss": "n. turtles and alligators"},
            {"word": "日本", "pinyin": "Rìběn", "gloss": "Japan"},      # not in the text
            {"word": "之", "pinyin": "zhī", "gloss": "part."},          # in the text but covered by the glossary
        ]})
        r = steps.gloss_gaps(c, a)
        self.assertEqual([w["word"] for w in r.data["words"]], ["黿鼉"])
        self.assertIn("【", c.session.requests[0]["json"]["messages"][1]["content"])

    def test_grammar_ids_must_be_offered(self):
        a = self.analysis("此其所以不若也")
        c = stub({"notes": [
            {"number": 1, "grammar_id": "demonstratives", "note": "this"},
            {"number": 2, "grammar_id": "made-up-id", "note": "his"},
            {"number": 99, "grammar_id": None, "note": "out of range"},
        ]})
        notes = steps.grammar_notes(c, a, self.course).data["notes"]
        self.assertEqual(len(notes), 2)
        self.assertEqual(notes[0]["grammar_id"], "demonstratives")
        self.assertIsNone(notes[1]["grammar_id"])

    def test_names_never_include_dates(self):
        a = self.analysis("光緒二十六年，梁啓超作此文。")
        c = stub({"items": [
            {"text": "光緒二十六年", "kind": "title", "note": "1899"},
            {"text": "梁啓超", "kind": "person", "note": "Liang Qichao"},
            {"text": "孫文", "kind": "person", "note": "not in the text"},
        ]})
        items = steps.names(c, a).data["items"]
        self.assertEqual([i["text"] for i in items], ["梁啓超"])

    def test_dates_are_not_gaps(self):
        a = self.analysis("光緒二十六年")
        self.assertEqual(a.gaps, [])

    def test_translate(self):
        r = steps.translate(stub({"translation": " This is it. ", "literal": "this be it"}), "是也", literal=True)
        self.assertEqual(r.data, {"translation": "This is it.", "literal": "this be it"})


class LimitsTest(unittest.TestCase):
    def test_daily_limit_and_reset(self):
        day = [_date(2027, 1, 1)]
        lim = Limits(2, 0, today=lambda: day[0])
        self.assertIsNone(lim.check_and_count("a"))
        self.assertIsNone(lim.check_and_count("a"))
        self.assertIn("today's limit", lim.check_and_count("a"))
        self.assertIsNone(lim.check_and_count("b"))      # per user
        day[0] = _date(2027, 1, 2)
        self.assertIsNone(lim.check_and_count("a"))      # a new day
        self.assertEqual(lim.remaining("a"), 1)

    def test_global_hourly_limit(self):
        now = [1000.0]
        lim = Limits(0, 3, clock=lambda: now[0])
        for u in "abc":
            self.assertIsNone(lim.check_and_count(u))
        self.assertIn("hourly limit", lim.check_and_count("d"))
        now[0] += 3601
        self.assertIsNone(lim.check_and_count("d"))


class Scoring(unittest.TestCase):
    def test_break_positions(self):
        self.assertEqual(break_positions("日本人之稱我中國也，一則曰「老大帝國」。"), {8, 15})
        self.assertEqual(break_positions("「之」"), set())      # quotation marks are not breaks

    def test_score_punctuation(self):
        gold = "甲乙，丙丁。戊己。"
        s = score_punctuation("甲乙。丙丁戊己，", gold)
        self.assertEqual((s.tp, s.fp, s.fn), (2, 0, 1))     # breaks after 乙 and 己 found, after 丁 missed
        self.assertAlmostEqual(score_punctuation(gold, gold).f1, 1.0)

    def test_segmentation(self):
        s = score_sets(boundaries({(0, 2), (2, 3)}), boundaries({(0, 2), (2, 4)}))
        self.assertEqual((s.tp, s.fp, s.fn), (2, 1, 1))

    def test_gloss_agreement(self):
        self.assertTrue(glosses_agree("v. to ask, request", "*v.* to request"))
        self.assertIsNone(glosses_agree("n. the past", "*adv.* formerly"))
        self.assertEqual(content_words("*n.* the selection of heaven (Yan Fu's term)"), {"selection", "heaven"})


class Gaps(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = glossary_index(build(load(CONTENT)))

    def test_gap_extends_over_weak_neighbour(self):
        from app.assistant.lookup import Match
        text = "如朝陽"
        # 朝 covered only by a single-character gloss, 陽 not at all
        matches = [Match(1, 2, []), Match(0, 1, [])]
        self.assertEqual(uncovered(text, matches), [(1, 3)])

    def test_strong_coverage_is_not_extended(self):
        from app.assistant.lookup import Match
        matches = [Match(0, 2, [])]          # a two-character term
        self.assertEqual(uncovered("中國陽", matches), [(2, 3)])

    def test_major_breaks_forgive_commas(self):
        from app.assistant.evaluate import score_major_breaks
        gold = "老年人如夕照，少年人如朝陽；老年人如僧。"
        pred = "老年人，如夕照；少年人，如朝陽。老年人，如僧。"
        s = score_major_breaks(pred, gold)
        self.assertEqual((s.fp, s.fn), (0, 0))


class Chunks(unittest.TestCase):
    def test_chunks_cut_at_breaks_and_keep_gaps_whole(self):
        from app.assistant.steps import chunks
        text = "甲乙丙丁。" * 40              # 200 characters
        gaps = [(2, 4), (148, 152), (190, 192)]
        pieces = chunks(text, gaps, size=150)
        self.assertTrue(all(text[b - 1] == "。" or b == len(text) or any(a2 < b <= b2 for a2, b2 in gaps)
                            for a, b in pieces))
        for g0, g1 in gaps:                   # every gap lies inside one piece
            self.assertTrue(any(a <= g0 and g1 <= b for a, b in pieces))

    def test_one_call_per_chunk(self):
        a = analyse("黿鼉之。" * 60, load(CONTENT), build(load(CONTENT)), max_chars=5000)
        c = stub(*[{"words": [{"word": "黿鼉", "pinyin": "yuántuó", "gloss": "n. turtles"}]}] * 5)
        r = steps.gloss_gaps(c, a)
        self.assertGreater(len(c.session.requests), 1)
        self.assertEqual([w["word"] for w in r.data["words"]], ["黿鼉"])


class Hardening(unittest.TestCase):
    def test_setup_errors_are_not_retried(self):
        for status in (401, 402, 403, 404):
            c = scripted(status)
            with self.assertRaises(ModelError) as cm:
                steps.translate(c, "是也")
            self.assertIn("not set up correctly", str(cm.exception))

    def test_temporary_failures_retried(self):
        c = scripted(503, {"translation": "It is."})
        self.assertEqual(steps.translate(c, "是也").data["translation"], "It is.")
        c = scripted(_requests.ConnectionError(), {"translation": "It is."})
        self.assertEqual(steps.translate(c, "是也").data["translation"], "It is.")
        with self.assertRaises(ModelError) as cm:
            steps.translate(scripted(500, 502), "是也")
        self.assertIn("not available", str(cm.exception))

    def test_answer_that_is_not_json(self):
        class Html(FakeResponse):
            def json(self):
                raise ValueError("html")
        s = ScriptedSession()
        replies = [Html(""), FakeResponse(json.dumps({"translation": "It is."}))]
        s.post = lambda *a, **k: replies.pop(0)
        c = OllamaClient("http://model.test", "m", session=s, retry_pause=0)
        self.assertEqual(steps.translate(c, "是也").data["translation"], "It is.")

    def test_timeout_message(self):
        with self.assertRaises(ModelError) as cm:
            steps.translate(scripted(_requests.Timeout()), "是也")
        self.assertIn("too long", str(cm.exception))

    def test_deadline_shortens_and_stops_calls(self):
        c = scripted({"translation": "It is."}, timeout=60)
        with c.deadline(10):
            steps.translate(c, "是也")
        self.assertLessEqual(c.session.timeouts[0], 10)
        c = scripted({"translation": "It is."})
        with self.assertRaises(ModelError):
            with c.deadline(0.5):
                steps.translate(c, "是也")
        self.assertEqual(c.session.timeouts, [])          # no call started without time left

    def test_deadline_is_per_thread(self):
        c = scripted({"translation": "It is."})
        seen = []
        with c.deadline(0.5):
            t = _threading.Thread(target=lambda: seen.append(c._time_left()))
            t.start(); t.join()
        self.assertEqual(seen, [60.0])

    def test_sessions_are_per_thread(self):
        c = OllamaClient("http://model.test", "m")
        other = []
        t = _threading.Thread(target=lambda: other.append(c.session))
        t.start(); t.join()
        self.assertIsNot(c.session, other[0])
        self.assertIs(c.session, c.session)

    def test_words_keep_parts_that_succeeded(self):
        text = "甲乙丙丁" * 50
        analysis = analyse(text, *_course_and_entries(), 600)
        n = len(steps.chunks(analysis.prepared.text, analysis.gaps))
        self.assertGreater(n, 1)
        script = [{"words": [{"word": "甲乙丙丁甲乙", "pinyin": "", "gloss": "a phrase"}]}] + [400] * (n - 1)
        r = steps.gloss_gaps(scripted(*script), analysis)
        self.assertTrue(r.data["incomplete"])
        self.assertEqual(r.data["words"][0]["word"], "甲乙丙丁甲乙")
        self.assertTrue(r.data["words"][0]["phrase"])
        with self.assertRaises(ModelError):
            steps.gloss_gaps(scripted(*([400] * n)), analysis)

    def test_ask_ignores_malformed_history(self):
        c = stub({"answer": "It is a particle."})
        r = steps.ask(c, "是也", ["junk", None, {"q": "What?", "a": "This."}], "And 也?")
        self.assertEqual(r.data["answer"], "It is a particle.")

    def test_refund(self):
        lim = Limits(2, 10)
        self.assertIsNone(lim.check_and_count("u"))
        lim.refund("u")
        self.assertEqual(lim.remaining("u"), 2)
        self.assertEqual(len(lim._recent), 0)
