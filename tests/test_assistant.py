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
