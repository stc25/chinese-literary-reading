"""Tests for tools/validate.py.

Run with:  python -m unittest discover tests
"""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import validate  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "valid"
UNIT = "units/u01-topic-and-comment/unit.md"
PASSAGE = "units/u01-topic-and-comment/u01-p01-old-empire.md"
GRAMMAR = "grammar/zhi-nominaliser.md"


class ValidFixture(unittest.TestCase):
    def test_valid_fixture_has_no_issues(self):
        rep = validate.validate(FIXTURE)
        self.assertEqual([i.msg for i in rep.issues], [])
        self.assertEqual(rep.kinds["passage"], 1)
        self.assertEqual(len(rep.reviews), 1)


class BrokenContent(unittest.TestCase):
    """Each test breaks one thing in a copy of the valid fixture."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.root = self.tmp / "content"
        shutil.copytree(FIXTURE, self.root)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def edit(self, rel, old, new):
        p = self.root / rel
        text = p.read_text(encoding="utf-8")
        self.assertIn(old, text, f"test setup: {old!r} not in {rel}")
        p.write_text(text.replace(old, new, 1), encoding="utf-8")

    def assertError(self, fragment):
        rep = validate.validate(self.root)
        msgs = [i.msg for i in rep.errors]
        self.assertTrue(any(fragment in m for m in msgs), f"no error containing {fragment!r}; got {msgs}")

    def assertWarning(self, fragment):
        rep = validate.validate(self.root)
        msgs = [i.msg for i in rep.warnings]
        self.assertTrue(any(fragment in m for m in msgs), f"no warning containing {fragment!r}; got {msgs}")

    # frontmatter -----------------------------------------------------------
    def test_missing_frontmatter(self):
        p = self.root / GRAMMAR
        p.write_text(p.read_text(encoding="utf-8").replace("---\n", "", 1), encoding="utf-8")
        self.assertError("missing YAML frontmatter")

    def test_bad_controlled_value(self):
        self.edit(PASSAGE, "status: draft", "status: done")
        self.assertError("'done' is not allowed")

    def test_unquoted_date(self):
        self.edit(PASSAGE, 'date: "1900"', "date: 1900")
        self.assertError("put the date in quotes")

    def test_missing_field(self):
        self.edit(PASSAGE, "rights_note: Author died 1929.\n", "")
        self.assertError("missing frontmatter field `rights_note`")

    def test_placeholder_in_frontmatter(self):
        self.edit(PASSAGE, "title_zh: 少年中國說（節選）", "title_zh: <Chinese title>")
        self.assertError("template placeholder")

    def test_id_does_not_match_filename(self):
        self.edit(PASSAGE, "id: u01-p01", "id: u01-p02")
        self.assertError("does not match file name")

    # sections --------------------------------------------------------------
    def test_unknown_section(self):
        self.edit(PASSAGE, "## Notes", "## Commentary")
        self.assertError('unknown section "## Commentary"')

    def test_section_out_of_order(self):
        p = self.root / PASSAGE
        text = p.read_text(encoding="utf-8")
        intro_start = text.index("## Introduction")
        text_start = text.index("## Text")
        intro = text[intro_start:text_start]
        text = text.replace(intro, "")
        text = text.replace("## Notes", intro + "## Notes")
        p.write_text(text, encoding="utf-8")
        self.assertError("is out of order")

    def test_missing_required_section(self):
        p = self.root / PASSAGE
        text = p.read_text(encoding="utf-8")
        start, end = text.index("## Translation"), text.index("## Literal translation")
        p.write_text(text[:start] + text[end:], encoding="utf-8")
        self.assertError('missing required section "## Translation"')

    # links -----------------------------------------------------------------
    def test_broken_link(self):
        self.edit(PASSAGE, "../../grammar/ye-topic.md", "../../grammar/ye-final.md")
        self.assertError("broken link")

    def test_wikilink(self):
        self.edit(PASSAGE, "[也](../../grammar/ye-topic.md)", "[[ye-topic]]")
        self.assertError("wiki-style")

    # text ------------------------------------------------------------------
    def test_ascii_punctuation(self):
        self.edit(PASSAGE, "中國也，一則", "中國也, 一則")
        self.assertError("ASCII punctuation")

    def test_markdown_in_text(self):
        self.edit(PASSAGE, "日本人之稱我中國也，", "日本人**之**稱我中國也，")
        self.assertError("Markdown formatting is not allowed")

    def test_original_text_mismatch(self):
        self.edit(PASSAGE, "## Glosses", "## Original text\n\n日本人之稱我中國也一則曰老大帝國\n\n## Glosses")
        self.assertError("## Original text does not contain the same characters")

    def test_original_text_match(self):
        self.edit(PASSAGE, "## Glosses",
                  "## Original text\n\n日本人之稱我中國也、一則曰老大帝國、再則曰老大帝國。\n\n## Glosses")
        self.assertEqual(validate.validate(self.root).errors, [])

    # glosses ---------------------------------------------------------------
    def test_term_not_in_text(self):
        self.edit(PASSAGE, "| 帝國 | dìguó |", "| 王國 | wángguó |")
        self.assertError("is not found in ## Text")

    def test_occurrence_out_of_range(self):
        self.edit(PASSAGE, "| 曰 | yuē |", "| 曰 #3 | yuē |")
        self.assertError("has only 2 occurrence(s)")

    def test_occurrence_in_range(self):
        self.edit(PASSAGE, "| 曰 | yuē |", "| 曰 #1 #2 | yuē |")
        self.assertEqual(validate.validate(self.root).errors, [])

    def test_split_term(self):
        self.edit(PASSAGE, "| 一則 | yīzé |", "| 一則 … 再則 | yīzé … zàizé |")
        self.assertEqual(validate.validate(self.root).errors, [])

    def test_split_term_wrong_order(self):
        self.edit(PASSAGE, "| 一則 | yīzé |", "| 再則 … 一則 | zàizé … yīzé |")
        self.assertError("is not found in ## Text")

    def test_tone_numbers(self):
        self.edit(PASSAGE, "| 稱 | chēng |", "| 稱 | cheng1 |")
        self.assertError("tone numbers")

    def test_pinyin_with_sentence_punctuation(self):
        self.edit(GRAMMAR, "| Rìběnrén zhī chēng wǒ Zhōngguó yě |", "| Rìběnrén zhī chēng wǒ Zhōngguó yě, ... |")
        self.assertError("three dots")

    def test_pinyin_comma_allowed(self):
        self.edit(GRAMMAR, "| Rìběnrén zhī chēng wǒ Zhōngguó yě |", "| Rìběnrén zhī chēng wǒ Zhōngguó yě, yīzé |")
        self.assertEqual(validate.validate(self.root).errors, [])

    def test_duplicate_general_gloss(self):
        self.edit(PASSAGE, "| 稱 | chēng | to call; to refer to as | |",
                  "| 稱 | chēng | to call; to refer to as | |\n| 稱 | chèng | steelyard | |")
        self.assertWarning("glossed more than once")

    def test_unknown_grammar_in_gloss(self):
        self.edit(PASSAGE, "| ye-topic |", "| ye-final |")
        self.assertError("unknown grammar or toolkit id 'ye-final'")

    def test_wrong_table_header(self):
        self.edit(PASSAGE, "| Term | Pinyin | Gloss | Grammar |", "| Term | Reading | Gloss | Grammar |")
        self.assertError("table header must be")

    # translation -----------------------------------------------------------
    def test_translation_paragraph_mismatch(self):
        self.edit(PASSAGE, "and again \"the old empire\".\n\n## Literal",
                  "and again \"the old empire\".\n\nAn extra paragraph.\n\n## Literal")
        self.assertError("## Translation has 2 paragraph(s)")

    # exercises -------------------------------------------------------------
    def test_choice_without_correct_option(self):
        self.edit(PASSAGE, "- [x] It makes", "- [ ] It makes")
        self.assertError("no option is marked correct")

    def test_punctuate_answer_mismatch(self):
        self.edit(PASSAGE, "**Answer:** 日本人之稱我中國也，一則曰老大帝國，再則曰老大帝國。",
                  "**Answer:** 日本人之稱我中國也，一則曰老大帝國。")
        self.assertError("does not match **Text:**")

    def test_punctuate_text_has_punctuation(self):
        self.edit(PASSAGE, "**Text:** 日本人之稱我中國也一則", "**Text:** 日本人之稱我中國也，一則")
        self.assertError("must have no punctuation")

    def test_translate_without_answer(self):
        self.edit(PASSAGE, "**Answer:** When the Japanese", "When the Japanese")
        self.assertError("needs an **Answer:**")

    def test_unknown_exercise_type(self):
        self.edit(PASSAGE, "### 3. translate", "### 3. essay")
        self.assertError("unknown exercise type 'essay'")

    # units and course ------------------------------------------------------
    def test_passage_not_listed_in_unit(self):
        self.edit(UNIT, '1. [The "old empire"](u01-p01-old-empire.md)\n', "")
        self.assertError("is not listed in ## Passages")

    def test_unit_level_mismatch_in_course(self):
        self.edit(UNIT, "level: beginner", "level: intermediate")
        self.assertError("but is listed under Beginner")

    def test_unknown_prerequisite(self):
        self.edit(UNIT, "prerequisites: []", "prerequisites: [u09]")
        self.assertError("unknown unit 'u09'")

    # grammar ---------------------------------------------------------------
    def test_grammar_example_unknown_passage(self):
        self.edit(GRAMMAR, "| u01-p01 |", "| u02-p01 |")
        self.assertError("source passage 'u02-p01' does not exist")

    def test_grammar_example_not_in_passage(self):
        self.edit(GRAMMAR, "| 日本人之稱我中國也 |", "| 吾之不遇魯侯 |")
        self.assertWarning("example is not found in the text of passage")


    # toolkit and data files ------------------------------------------------
    TOOLKIT = "toolkit/t02-dates-and-calendars.md"
    DATA = "toolkit/data/qing-reign-periods.csv"

    def test_missing_data_file(self):
        self.edit(self.TOOLKIT, "data: [qing-reign-periods.csv]", "data: [qing-reigns.csv]")
        self.assertError("data file 'qing-reigns.csv' not found")

    def test_bad_csv_row(self):
        self.edit(self.DATA, "光緒,Guāngxù,載湉,1875,1908", "光緒,Guāngxù,1875,1908")
        self.assertError("row has 4 cells, the header has 5")

    def test_bad_csv_column_name(self):
        self.edit(self.DATA, "first_year", "First Year")
        self.assertError("must be lowercase snake_case")

    def test_toolkit_not_listed(self):
        self.edit("course.md", "- [Dates and calendars](toolkit/t02-dates-and-calendars.md)\n", "")
        self.assertWarning("toolkit page t02 is not listed")

    def test_toolkit_summary_not_first(self):
        self.edit(self.TOOLKIT, "## Summary\n\nHow dates", "## Intro\n\nText.\n\n## Summary\n\nHow dates")
        self.assertError('"## Summary" must be the first section')

    def test_toolkit_practice_checked(self):
        self.edit(self.TOOLKIT, "**Answer:** 1875", "")
        self.assertError("needs an **Answer:**")

    def test_toolkit_id_in_gloss(self):
        self.edit(PASSAGE, "| 中國 | Zhōngguó | China | |", "| 中國 | Zhōngguó | China | t02 |")
        self.assertEqual(validate.validate(self.root).errors, [])

    # planned status --------------------------------------------------------
    def test_planned_grammar_may_be_empty(self):
        (self.root / "grammar" / "er-conjunction.md").write_text(
            "---\nid: er-conjunction\ntitle: 而\nforms: [而]\nlevel: beginner\nstatus: planned\n---\n\n"
            "## Summary\n\n而 links verbs and clauses.\n\n## Explanation\n\n## Examples\n",
            encoding="utf-8")
        rep = validate.validate(self.root)
        self.assertEqual([i.msg for i in rep.issues], [])

    def test_draft_grammar_may_not_be_empty(self):
        (self.root / "grammar" / "er-conjunction.md").write_text(
            "---\nid: er-conjunction\ntitle: 而\nforms: [而]\nlevel: beginner\nstatus: draft\n---\n\n"
            "## Summary\n\n而 links verbs and clauses.\n\n## Explanation\n\n## Examples\n",
            encoding="utf-8")
        self.assertError('section "## Explanation" is empty')

    def test_planned_passage_in_unit(self):
        self.edit(UNIT, '1. [The "old empire"](u01-p01-old-empire.md)\n',
                  '1. [The "old empire"](u01-p01-old-empire.md)\n2. 申報 news item (planned)\n')
        rep = validate.validate(self.root)
        self.assertEqual(rep.issues, [])
        self.assertEqual(rep.planned_passages, 1)


class CommandLine(unittest.TestCase):
    def test_exit_codes(self):
        self.assertEqual(validate.main([str(FIXTURE), "--quiet"]), 0)
        self.assertEqual(validate.main([str(ROOT / "no-such-folder"), "--quiet"]), 1)


if __name__ == "__main__":
    unittest.main()
