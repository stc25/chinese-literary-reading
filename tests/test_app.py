"""Tests for the Flask app (app/).

Run with:  python -m unittest discover -s tests
"""
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import create_app  # noqa: E402
from app.content import ContentError, load  # noqa: E402
from app.content.loader import find_spans  # noqa: E402
from app.content.reader import original_segments, text_segments  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "valid"
CONTENT = ROOT / "content"
PASSAGE = "units/u01-topic-and-comment/u01-p01-old-empire.md"


def make_app(content=FIXTURE, **config):
    return create_app({"TESTING": True, "CONTENT_DIR": content, **config})


class Spans(unittest.TestCase):
    def test_simple_term(self):
        self.assertEqual(find_spans("中國之中", ["中"]), [[(0, 1)], [(3, 4)]])

    def test_split_term(self):
        self.assertEqual(find_spans("非禮勿視非義不行", ["非", "不"]), [[(0, 1), (6, 7)], [(4, 5), (6, 7)]])

    def test_split_term_missing_second_part(self):
        self.assertEqual(find_spans("非禮勿視", ["非", "不"]), [])


class Segments(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.course = load(CONTENT)

    def test_segments_rebuild_the_text(self):
        for p in self.course.passages.values():
            paras = ["".join(s.text for s in para) for para in text_segments(p)]
            self.assertEqual(paras, p.paragraphs, p.id)

    def test_punctuation_is_marked(self):
        p = self.course.passages["u17-p02"]
        for para in text_segments(p):
            for s in para:
                if s.text in ("，", "。"):
                    self.assertTrue(s.punct)

    def test_overlapping_glosses(self):
        # 由散入群 is glossed as a phrase, and its 由 also as the 7th 由
        p = self.course.passages["u17-p02"]
        segs = [s for para in text_segments(p) for s in para]
        self.assertTrue(any(len(s.occ) > 1 for s in segs))

    def test_original_text_keeps_every_gloss(self):
        for p in self.course.passages.values():
            if not p.original:
                continue
            orig = {o for para in original_segments(p) for s in para for o in s.occ}
            text = {o for para in text_segments(p) for s in para for o in s.occ}
            self.assertEqual(orig, text, p.id)
            self.assertEqual(["".join(s.text for s in para) for para in original_segments(p)], p.original)


class Loader(unittest.TestCase):
    def test_fixture_loads(self):
        course = load(FIXTURE)
        self.assertIn("u01", course.units)
        self.assertEqual(course.levels["beginner"], ["u01"])
        p = course.passages["u01-p01"]
        self.assertTrue(p.paragraphs)
        self.assertTrue(p.glosses)

    def test_every_gloss_has_spans(self):
        course = load(FIXTURE)
        for p in course.passages.values():
            for gl in p.glosses:
                self.assertTrue(gl.spans, f"{p.id}: {gl.term}")
                for spans in gl.spans:
                    self.assertEqual("".join(p.text[a:b] for a, b in spans), "".join(gl.parts))

    def test_occurrence_gloss_selects_spans(self):
        course = load(FIXTURE)
        p = course.passages["u01-p01"]
        numbered = [gl for gl in p.glosses if gl.occurrences]
        for gl in numbered:
            self.assertEqual(len(gl.spans), len(gl.occurrences))

    def test_invalid_content_is_refused(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            root = tmp / "content"
            shutil.copytree(FIXTURE, root)
            f = root / PASSAGE
            f.write_text(f.read_text(encoding="utf-8").replace("status: draft", "status: finished"), encoding="utf-8")
            with self.assertRaises(ContentError):
                load(root)
            with self.assertRaises(ContentError):
                make_app(root)
        finally:
            shutil.rmtree(tmp)


class Pages(unittest.TestCase):
    def setUp(self):
        self.client = make_app().test_client()

    def test_course_map(self):
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn('href="/units/u01"', html)

    def test_unit_page(self):
        r = self.client.get("/units/u01")
        self.assertEqual(r.status_code, 200)
        self.assertIn('href="/units/u01/p01"', r.get_data(as_text=True))

    def test_passage_page(self):
        r = self.client.get("/units/u01/p01")
        self.assertEqual(r.status_code, 200)
        html = r.get_data(as_text=True)
        self.assertIn('lang="zh-Hant"', html)
        self.assertIn('class="translation-para"', html)
        self.assertIn('id="gloss-data"', html)

    def test_glossed_words_are_buttons(self):
        html = self.client.get("/units/u01/p01").get_data(as_text=True)
        self.assertIn('<button type="button" class="g" data-occ="0-0"', html)
        # the second 曰 is the second occurrence of gloss 8
        self.assertIn('data-occ="8-1"', html)

    def test_view_parameter(self):
        html = self.client.get("/units/u01/p01?view=vertical").get_data(as_text=True)
        self.assertIn('class="reader view-vertical"', html)
        html = self.client.get("/units/u01/p01?view=sideways").get_data(as_text=True)
        self.assertIn('class="reader view-modern"', html)

    def test_draft_label(self):
        html = self.client.get("/units/u01/p01").get_data(as_text=True)
        self.assertIn("badge-draft", html)

    def test_unknown_pages(self):
        for url in ("/units/u99", "/units/u01/p09", "/grammar/nothing", "/toolkit/t99"):
            self.assertEqual(self.client.get(url).status_code, 404, url)

    def test_hide_unreviewed(self):
        client = make_app(SHOW_UNREVIEWED=False).test_client()
        self.assertEqual(client.get("/units/u01/p01").status_code, 404)


class RealContent(unittest.TestCase):
    """Every page of the real course renders, and no link points at a Markdown file."""

    @classmethod
    def setUpClass(cls):
        cls.app = make_app(CONTENT)
        cls.client = cls.app.test_client()
        cls.course = cls.app.extensions["course_store"].course

    def urls(self):
        c = self.course
        yield from ("/", "/grammar", "/toolkit", "/glossary")
        yield from (f"/units/{u}" for u in c.units)
        yield from (f"/units/{p.unit_id}/{p.number}" for p in c.passages.values())
        yield from (f"/grammar/{g}" for g in c.grammar)
        yield from (f"/toolkit/{t}" for t in c.toolkit)

    def test_all_pages_render(self):
        for url in self.urls():
            with self.subTest(url=url):
                r = self.client.get(url)
                self.assertEqual(r.status_code, 200)
                hrefs = re.findall(r'href="([^"]+)"', r.get_data(as_text=True))
                self.assertFalse([h for h in hrefs if re.search(r"\.md($|#)", h)], "unresolved .md link")

    def test_internal_links_resolve(self):
        seen = set()
        for url in self.urls():
            html = self.client.get(url).get_data(as_text=True)
            for h in re.findall(r'href="(/[^"#]*)', html):
                if h.startswith("/static/") or h in seen:
                    continue
                seen.add(h)
                with self.subTest(link=h, page=url):
                    self.assertEqual(self.client.get(h).status_code, 200)


if __name__ == "__main__":
    unittest.main()


class Tools(unittest.TestCase):
    def setUp(self):
        from app.tools import reigns_from_rows
        self.reigns = reigns_from_rows(load(CONTENT).data["qing-reign-periods.csv"])

    def test_cyclical(self):
        from app.tools import cyclical
        self.assertEqual(cyclical(1864), "甲子")
        self.assertEqual(cyclical(1898), "戊戌")
        self.assertEqual(cyclical(1911), "辛亥")

    def test_year_names(self):
        from app.tools import year_name
        self.assertEqual([year_name(n) for n in (1, 2, 10, 11, 24, 30)], ["元年", "二年", "十年", "十一年", "二十四年", "三十年"])

    def test_reign_to_western(self):
        from app.tools import reign_to_western
        r = reign_to_western(self.reigns, "光緒", 24)
        self.assertTrue(r.ok)
        self.assertIn("1898", r.lines[0])
        self.assertFalse(reign_to_western(self.reigns, "宣統", 4).ok)

    def test_western_to_chinese(self):
        from app.tools import western_to_chinese
        self.assertIn("道光二十二年", western_to_chinese(self.reigns, 1842).lines[0])
        self.assertIn("民國八年", western_to_chinese(self.reigns, 1919).lines[0])
        self.assertFalse(western_to_chinese(self.reigns, 1700).ok)


class M3Pages(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = make_app(CONTENT).test_client()
        cls.course = load(CONTENT)

    def test_converter_form(self):
        html = self.client.get("/toolkit/t02?mode=reign&reign=光緒&year=24").get_data(as_text=True)
        self.assertIn("光緒二十四年 = 1898 (戊戌)", html)

    def test_glossary_search(self):
        all_html = self.client.get("/glossary").get_data(as_text=True)
        html = self.client.get("/glossary?q=qun").get_data(as_text=True)
        self.assertIn(">群<", html)
        self.assertLess(len(html), len(all_html))
        self.assertIn(">群<", self.client.get("/glossary?q=society").get_data(as_text=True))

    def test_index_pages(self):
        for url in ("/grammar", "/toolkit", "/glossary"):
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_summaries(self):
        data = self.client.get("/summaries.json").get_json()
        self.assertIn("/grammar/suo", data)
        self.assertIn("/toolkit/t02", data)

    def test_glossary_entries(self):
        from app.content.glossary import build
        entries = build(self.course)
        keys = [(e.term, " ".join(e.gloss.split())) for e in entries]
        self.assertEqual(len(keys), len(set(keys)))
        total = sum(len(p.glosses) for p in self.course.passages.values())
        self.assertLessEqual(len(entries), total)

    def test_glossary_md_up_to_date(self):
        from app.content.glossary import build, to_markdown
        text = to_markdown(self.course, build(self.course))
        current = (CONTENT / "glossary.md").read_text(encoding="utf-8")
        self.assertEqual(current, text, "content/glossary.md is out of date: run python3 tools/build_glossary.py")

    def test_earlier_glosses_never_overlap_own(self):
        from app.content.glossary import passages_in_order
        from app.content.reader import earlier_glosses
        order = passages_in_order(self.course)
        for i, p in enumerate(order):
            own = {k for gl in p.glosses for spans in gl.spans for a, b in spans for k in range(a, b)}
            for e in earlier_glosses(p, order[:i]):
                self.assertGreaterEqual(len(e.gloss.term), 2)
                for spans in e.spans:
                    for a, b in spans:
                        self.assertFalse(own & set(range(a, b)), f"{p.id}: {e.gloss.term}")

    def test_earlier_gloss_marked(self):
        html = self.client.get("/units/u17/p02").get_data(as_text=True)
        self.assertIn("g-earlier", html)
        self.assertIn('"from"', html)
