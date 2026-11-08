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

    def test_retry_then_fail(self):
        c = stub("not json", "still not json")
        with self.assertRaises(ModelError):
            steps.punctuate(c, "之乎")
        self.assertEqual(len(c.session.requests), 2)

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


class Api(unittest.TestCase):
    def setUp(self):
        self.app = create_app({"TESTING": True})
        self.client = self.app.test_client()
        html = self.client.get("/assistant/").get_data(as_text=True)
        self.token = re.search(r'name="csrf" value="([^"]+)"', html).group(1)

    def call(self, step, body, token=None):
        return self.client.post(f"/assistant/api/{step}", json=body,
                                headers={"X-CSRF-Token": self.token if token is None else token})

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
