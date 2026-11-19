"""Tests for the reading assistant's deterministic layer (A1) and page."""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import create_app  # noqa: E402
from app.assistant.lookup import (analyse, find_dates, find_function_words, find_glossary_matches,  # noqa: E402
                                  function_forms, glossary_index, key, parse_number, prepare, uncovered)
from app.content import load  # noqa: E402
from app.content.glossary import build  # noqa: E402

CONTENT = ROOT / "content"


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


class Page(unittest.TestCase):
    def setUp(self):
        self.client = create_app({"TESTING": True}).test_client()

    def post(self, text):
        html = self.client.get("/assistant/").get_data(as_text=True)
        token = re.search(r'name="csrf" value="([^"]+)"', html).group(1)
        return self.client.post("/assistant/", data={"csrf": token, "text": text})

    def test_form(self):
        self.assertEqual(self.client.get("/assistant/").status_code, 200)

    def test_analysis(self):
        r = self.post("光绪二十四年四月二十三日，内阁奉上谕")
        html = r.get_data(as_text=True)
        self.assertEqual(r.status_code, 200)
        self.assertIn("converted to traditional", html)
        self.assertIn('id="gloss-data"', html)
        self.assertIn("1898", html)
        self.assertIn("no-store", r.headers["Cache-Control"])

    def test_text_not_in_url_or_get(self):
        r = self.client.get("/assistant/?text=之乎者也")
        self.assertNotIn("之乎者也", r.get_data(as_text=True))

    def test_needs_token(self):
        self.assertEqual(self.client.post("/assistant/", data={"text": "之"}).status_code, 400)

    def test_too_long(self):
        self.assertIn("longer than", self.post("之" * 700).get_data(as_text=True))

    def test_can_be_switched_off(self):
        client = create_app({"TESTING": True, "ASSISTANT_ENABLED": False}).test_client()
        self.assertEqual(client.get("/assistant/").status_code, 404)
        self.assertNotIn("/assistant/", client.get("/").get_data(as_text=True))

    def test_result_page_accessibility(self):
        sys.path.insert(0, str(ROOT / "tests"))
        from test_accessibility import parse
        root = parse(self.post("日本人之稱我中國也，一則曰老大帝國。光緒二十四年").get_data(as_text=True))
        nodes = list(root.iter())
        ids = [n.attrs["id"] for n in nodes if "id" in n.attrs]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(sum(n.tag == "h1" for n in nodes), 1)
        textarea = next(n for n in nodes if n.tag == "textarea")
        self.assertTrue(any(n.tag == "label" and n.attrs.get("for") == textarea.attrs["id"] for n in nodes))


if __name__ == "__main__":
    unittest.main()


# --------------------------------------------------------------------------
# A2: AI steps, with the model replaced by a stub
# --------------------------------------------------------------------------

import json  # noqa: E402

from app.assistant import steps  # noqa: E402
from app.assistant.client import ModelError, OllamaClient  # noqa: E402


class FakeResponse:
    def __init__(self, content, status=200):
        self.status_code = status
        self._body = {"message": {"content": content}, "prompt_eval_count": 10, "eval_count": 5}

    def json(self):
        return self._body


class FakeSession:
    """Returns the queued replies in order and records the requests."""

    def __init__(self, *replies, status=200):
        self.replies = list(replies)
        self.status = status
        self.requests = []

    def post(self, url, json=None, headers=None, timeout=None):
        self.requests.append({"url": url, "json": json, "headers": headers})
        content = self.replies.pop(0) if self.replies else "{}"
        return FakeResponse(content if isinstance(content, str) else globals()["json"].dumps(content), self.status)


def stub(*replies, status=200, api_key=""):
    return OllamaClient("http://model.test", "test-model", api_key=api_key, session=FakeSession(*replies, status=status))


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


class ApiBase(unittest.TestCase):
    def setUp(self):
        self.app = create_app({"TESTING": True})
        self.client = self.app.test_client()
        html = self.client.get("/assistant/").get_data(as_text=True)
        self.token = re.search(r'name="csrf" value="([^"]+)"', html).group(1)

    def call(self, step, body, token=None):
        return self.client.post(f"/assistant/api/{step}", json=body,
                                headers={"X-CSRF-Token": self.token if token is None else token})


class Api(ApiBase):
    def test_translate_endpoint(self):
        self.app.extensions["assistant_client"] = stub({"translation": "When the Japanese speak of our China"})
        r = self.call("translate", {"text": "日本人之稱我中國也"})
        self.assertEqual(r.status_code, 200)
        d = r.get_json()
        self.assertTrue(d["ok"])
        self.assertEqual(d["source"], "ai")
        self.assertIn("Japanese", d["data"]["translation"])
        self.assertIn("no-store", r.headers["Cache-Control"])

    def test_needs_token(self):
        self.assertEqual(self.call("translate", {"text": "之"}, token="wrong").status_code, 400)

    def test_unknown_step(self):
        self.assertEqual(self.call("poem", {"text": "之"}).status_code, 404)

    def test_empty_or_long_text(self):
        self.assertEqual(self.call("translate", {"text": " "}).status_code, 400)
        self.assertEqual(self.call("translate", {"text": "之" * 700}).status_code, 400)

    def test_model_failure_is_reported(self):
        self.app.extensions["assistant_client"] = stub("bad", "bad")
        r = self.call("punctuate", {"text": "日本人之稱我中國也"})
        self.assertEqual(r.status_code, 502)
        self.assertFalse(r.get_json()["ok"])


# --------------------------------------------------------------------------
# A3: limits, questions, page
# --------------------------------------------------------------------------

from datetime import date as _date  # noqa: E402

from app.assistant.limits import Limits  # noqa: E402


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


class AskAndLimits(unittest.TestCase):
    def setUp(self):
        self.app = create_app({"TESTING": True, "ASSISTANT_DAILY_LIMIT": 3})
        self.client = self.app.test_client()
        html = self.client.get("/assistant/").get_data(as_text=True)
        self.token = re.search(r'name="csrf" value="([^"]+)"', html).group(1)

    def call(self, step, body):
        return self.client.post(f"/assistant/api/{step}", json=body, headers={"X-CSRF-Token": self.token})

    def test_ask(self):
        self.app.extensions["assistant_client"] = stub({"answer": "之 joins 日本人 and 稱."})
        r = self.call("ask", {"text": "日本人之稱我中國也", "question": "What does 之 do?",
                              "history": [{"q": "Who speaks?", "a": "The Japanese."}]})
        d = r.get_json()
        self.assertTrue(d["ok"])
        self.assertIn("之", d["data"]["answer"])
        sent = self.app.extensions["assistant_client"].session.requests[0]["json"]["messages"][1]["content"]
        self.assertIn("Earlier question: Who speaks?", sent)
        self.assertIn("Question: What does 之 do?", sent)

    def test_ask_needs_question_and_limits_history(self):
        self.assertEqual(self.call("ask", {"text": "之", "question": " "}).status_code, 400)
        history = [{"q": "q", "a": "a"}] * 10
        self.assertEqual(self.call("ask", {"text": "之", "question": "more?", "history": history}).status_code, 400)

    def test_daily_limit_returns_429(self):
        self.app.extensions["assistant_client"] = stub(*[{"translation": "x"}] * 5)
        codes = [self.call("translate", {"text": "日本人之稱我中國也"}).status_code for _ in range(4)]
        self.assertEqual(codes, [200, 200, 200, 429])

    def test_remaining_reported(self):
        self.app.extensions["assistant_client"] = stub({"translation": "x"})
        self.assertEqual(self.call("translate", {"text": "日本人之稱我中國也"}).get_json()["remaining"], 2)


class A3Page(unittest.TestCase):
    def setUp(self):
        self.client = create_app({"TESTING": True}).test_client()

    def test_help_page(self):
        r = self.client.get("/assistant/help")
        self.assertEqual(r.status_code, 200)
        self.assertIn("How it goes wrong", r.get_data(as_text=True))

    def test_ai_controls_and_notice(self):
        html = self.client.get("/assistant/").get_data(as_text=True)
        token = re.search(r'name="csrf" value="([^"]+)"', html).group(1)
        html = self.client.post("/assistant/", data={"csrf": token, "text": "吾心目中有黿鼉"}).get_data(as_text=True)
        self.assertIn("external AI service", html)
        for step in ("punctuate", "words", "grammar", "names", "translate"):
            self.assertIn(f'data-run="{step}"', html)
        self.assertIn("assistant.js", html)
        self.assertIn('data-text="吾心目中有黿鼉"', html)


# --------------------------------------------------------------------------
# A4: scoring
# --------------------------------------------------------------------------

from app.assistant.evaluate import (boundaries, break_positions, content_words, glosses_agree,  # noqa: E402
                                    score_punctuation, score_sets)


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


# --------------------------------------------------------------------------
# A5: hardening
# --------------------------------------------------------------------------

import threading as _threading  # noqa: E402
import time as _time  # noqa: E402

import requests as _requests  # noqa: E402

from app.assistant import client as _client_mod  # noqa: E402


class ScriptedSession:
    """Each item is a status code, an exception to raise, or a reply (dict or str) with status 200."""

    def __init__(self, *script):
        self.script = list(script)
        self.timeouts = []

    def post(self, url, json=None, headers=None, timeout=None):
        self.timeouts.append(timeout)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        if isinstance(item, int):
            r = FakeResponse("{}", item)
            r.text = "refused"
            return r
        return FakeResponse(item if isinstance(item, str) else globals()["json"].dumps(item))


def scripted(*script, timeout=60.0):
    return OllamaClient("http://model.test", "test-model", session=ScriptedSession(*script), timeout=timeout,
                        retry_pause=0)


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
        replies = [Html(""), FakeResponse(globals()["json"].dumps({"translation": "It is."}))]
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


_CACHE = {}


def _course_and_entries():
    if not _CACHE:
        course = load(ROOT / "content")
        _CACHE["v"] = (course, build(course))
    return _CACHE["v"]


class ApiHardening(ApiBase):
    def test_service_failure_not_counted(self):
        self.app.extensions["assistant_client"] = scripted(503, 503)
        r = self.call("translate", {"text": "日本人之稱我中國也"})
        self.assertEqual(r.status_code, 502)
        self.assertEqual(r.get_json()["remaining"], self.app.config["ASSISTANT_DAILY_LIMIT"])

    def test_learner_side_failure_counted(self):
        self.app.extensions["assistant_client"] = stub("bad", "bad")
        r = self.call("translate", {"text": "日本人之稱我中國也"})
        self.assertEqual(r.status_code, 502)
        self.assertEqual(r.get_json()["remaining"], self.app.config["ASSISTANT_DAILY_LIMIT"] - 1)

    def test_busy_when_all_slots_taken(self):
        self.app.config.update(ASSISTANT_MAX_CONCURRENT=1, ASSISTANT_QUEUE_WAIT=0.1)
        self.app.extensions.pop("assistant_gate", None)
        self.app.extensions["assistant_client"] = stub({"translation": "x"})
        with self.app.app_context():
            from app.assistant.flask_views import get_gate
            gate = get_gate()
        gate.acquire()
        try:
            r = self.call("translate", {"text": "日本人之稱我中國也"})
        finally:
            gate.release()
        self.assertEqual(r.status_code, 503)
        self.assertIn("busy", r.get_json()["error"])
        self.assertEqual(self.call("translate", {"text": "日本人之稱我中國也"}).status_code, 200)

    def test_concurrent_requests_respect_the_cap(self):
        self.app.config.update(ASSISTANT_MAX_CONCURRENT=2, ASSISTANT_QUEUE_WAIT=5, ASSISTANT_DAILY_LIMIT=0,
                               ASSISTANT_HOURLY_LIMIT=0)
        self.app.extensions.pop("assistant_gate", None)
        self.app.extensions.pop("assistant_limits", None)
        state = {"now": 0, "max": 0}
        lock = _threading.Lock()

        class Slow:
            model = "slow"

            def deadline(self, s):
                return OllamaClient("x", "y").deadline(s)

            def chat_json(self, *a, **k):
                with lock:
                    state["now"] += 1
                    state["max"] = max(state["max"], state["now"])
                _time.sleep(0.1)
                with lock:
                    state["now"] -= 1
                return _client_mod.Reply({"translation": "x"})

        self.app.extensions["assistant_client"] = Slow()
        codes = []

        def one():
            c = self.app.test_client()
            c.get("/assistant/")
            with c.session_transaction() as s:
                s["csrf"] = "t"
            codes.append(c.post("/assistant/api/translate", json={"text": "是也"},
                                headers={"X-CSRF-Token": "t"}).status_code)

        threads = [_threading.Thread(target=one) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(codes, [200] * 8)
        self.assertLessEqual(state["max"], 2)

    def test_request_size_limited(self):
        r = self.client.post("/assistant/api/translate", data="x" * 300_000, content_type="application/json",
                             headers={"X-CSRF-Token": self.token})
        self.assertEqual(r.status_code, 413)


class DeploymentSettings(unittest.TestCase):
    def test_timeouts_fit_together(self):
        app = create_app({"TESTING": True})
        step = app.config["ASSISTANT_STEP_DEADLINE"] + app.config["ASSISTANT_QUEUE_WAIT"]
        gconf = {}
        exec((ROOT / "deploy" / "gunicorn.conf.py").read_text(), gconf)
        self.assertGreater(gconf["timeout"], step)
        self.assertEqual(gconf["workers"], 1)              # the usage limits are kept in one process
        self.assertGreaterEqual(gconf["threads"], app.config["ASSISTANT_MAX_CONCURRENT"] + 4)
        nginx = (ROOT / "deploy" / "nginx.conf.example").read_text()
        api = re.search(r"location /assistant/api/ \{(.*?)\}", nginx, re.S).group(1)
        self.assertGreaterEqual(int(re.search(r"proxy_read_timeout (\d+)s", api).group(1)), gconf["timeout"])
