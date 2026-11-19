"""Framework-free tests of the content layer: spans, segments, loader and the date tools."""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.content import ContentError, load  # noqa: E402
from app.content.loader import find_spans  # noqa: E402
from app.content.reader import original_segments, text_segments  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "valid"
CONTENT = ROOT / "content"
PASSAGE = "units/u01-topic-and-comment/u01-p01-old-empire.md"


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
        finally:
            shutil.rmtree(tmp)


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


if __name__ == "__main__":
    unittest.main()
