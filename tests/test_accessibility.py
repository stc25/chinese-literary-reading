"""Automated accessibility checks (part of WCAG 2.2 AA) over every page of the course.

These cover what can be checked from the HTML and CSS alone: document language,
headings, labels, accessible names, ids, ARIA references and colour contrast.
They do not replace testing with a screen reader and a keyboard.
"""
import re
import sys
import unittest
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import create_app  # noqa: E402

CSS = ROOT / "app" / "static" / "css" / "site.css"
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}


class Node:
    def __init__(self, tag, attrs, parent):
        self.tag, self.attrs, self.parent = tag, dict(attrs), parent
        self.children, self.text = [], []

    def all_text(self):
        out = "".join(self.text)
        for c in self.children:
            out += c.all_text()
        return out

    def iter(self):
        yield self
        for c in self.children:
            yield from c.iter()


class Tree(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("#root", [], None)
        self.cur = self.root

    def handle_starttag(self, tag, attrs):
        n = Node(tag, attrs, self.cur)
        self.cur.children.append(n)
        if tag not in VOID:
            self.cur = n

    def handle_startendtag(self, tag, attrs):
        self.cur.children.append(Node(tag, attrs, self.cur))

    def handle_endtag(self, tag):
        n = self.cur
        while n is not self.root and n.tag != tag:
            n = n.parent
        if n is not self.root:
            self.cur = n.parent

    def handle_data(self, data):
        self.cur.text.append(data)


def parse(html):
    t = Tree()
    t.feed(html)
    return t.root


def accessible_name(node, ids):
    a = node.attrs
    if a.get("aria-label"):
        return a["aria-label"]
    if a.get("aria-labelledby"):
        return " ".join(ids[i].all_text() for i in a["aria-labelledby"].split() if i in ids)
    return node.all_text().strip()


class Pages(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app = create_app({"TESTING": True, "REVIEWERS": ["rv1"], "DEV_USER": "rv1"})
        cls.client = app.test_client()
        c = app.extensions["course_store"].course
        cls.urls = (["/", "/grammar", "/toolkit", "/glossary?q=qun", "/review", "/signed-out", "/accessibility", "/assistant/",
                     "/toolkit/t02?mode=reign&reign=光緒&year=24"]
                    + [f"/units/{u}" for u in c.units]
                    + [f"/units/{p.unit_id}/{p.number}" for p in c.passages.values()]
                    + [f"/units/{p.unit_id}/{p.number}?view=vertical" for p in list(c.passages.values())[:5]]
                    + [f"/grammar/{g}" for g in c.grammar]
                    + [f"/toolkit/{t}" for t in c.toolkit])

    def pages(self):
        for url in self.urls:
            html = self.client.get(url).get_data(as_text=True)
            yield url, parse(html)

    def test_structure(self):
        for url, root in self.pages():
            with self.subTest(url=url):
                nodes = list(root.iter())
                ids = {}
                for n in nodes:
                    if "id" in n.attrs:
                        self.assertNotIn(n.attrs["id"], ids, f"duplicate id {n.attrs['id']}")
                        ids[n.attrs["id"]] = n
                html = next(n for n in nodes if n.tag == "html")
                self.assertEqual(html.attrs.get("lang"), "en")
                title = next(n for n in nodes if n.tag == "title")
                self.assertTrue(title.all_text().strip())
                self.assertEqual(sum(n.tag == "h1" for n in nodes), 1, "exactly one h1")
                self.assertTrue(any(n.tag == "main" for n in nodes))

                # headings do not skip levels (outside the gloss dialog, which has its own heading)
                last = 0
                for n in nodes:
                    if re.fullmatch(r"h[1-6]", n.tag):
                        level = int(n.tag[1])
                        self.assertLessEqual(level, last + 1, f"heading {n.tag} '{n.all_text().strip()[:30]}' skips a level")
                        last = level
                        self.assertTrue(n.all_text().strip(), "empty heading")

                for n in nodes:
                    a = n.attrs
                    for ref in ("aria-labelledby", "aria-describedby", "aria-controls"):
                        for i in (a.get(ref) or "").split():
                            self.assertIn(i, ids, f"{ref} points to missing id {i}")
                    if n.tag == "img":
                        self.assertIn("alt", a)
                    if n.tag == "a" and "href" in a:
                        self.assertTrue(accessible_name(n, ids), f"link without text: {a['href']}")
                    if n.tag == "button":
                        self.assertTrue(accessible_name(n, ids), "button without a name")
                    if n.tag in ("input", "select", "textarea") and a.get("type") != "hidden":
                        labelled = a.get("aria-label") or a.get("aria-labelledby") or any(
                            m.tag == "label" and m.attrs.get("for") == a.get("id") for m in nodes)
                        self.assertTrue(labelled, f"{n.tag} #{a.get('id')} has no label")
                    if a.get("lang") is not None:
                        self.assertIn(a["lang"], ("en", "zh-Hant", "zh-Latn-pinyin"))

    def test_chinese_text_is_marked(self):
        """Runs of Chinese text in the main content carry lang="zh-Hant" on an ancestor."""
        han = re.compile(r"[一-鿿]{4,}")
        for url, root in self.pages():
            if not url.startswith("/units/") or url.count("/") != 3:
                continue
            with self.subTest(url=url):
                for n in root.iter():
                    if n.tag == "p" and "zh-text" in (n.parent.attrs.get("class") or ""):
                        p, lang = n, None
                        while p is not None and lang is None:
                            lang = p.attrs.get("lang")
                            p = p.parent
                        if han.search(n.all_text()):
                            self.assertEqual(lang, "zh-Hant")


def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def luminance(rgb):
    def ch(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    la, lb = sorted((luminance(hex_to_rgb(a)), luminance(hex_to_rgb(b))), reverse=True)
    return (la + 0.05) / (lb + 0.05)


class Contrast(unittest.TestCase):
    """Text colour pairs from the design tokens meet 4.5:1 (normal text) in light and dark mode."""

    PAIRS = [
        ("text", "bg"), ("text", "surface"), ("muted", "bg"), ("muted", "surface"), ("link", "bg"),
        ("link", "surface"), ("accent", "bg"), ("draft-text", "draft-bg"), ("error-text", "error-bg"),
        ("surface", "accent"),   # current layout button
        ("muted", "rule"),       # badges
        ("text", "accent-soft"),  # highlighted words
    ]

    def tokens(self):
        css = CSS.read_text(encoding="utf-8")
        light = dict(re.findall(r"--([\w-]+):\s*(#[0-9a-fA-F]{6})", css.split("@media (prefers-color-scheme: dark)")[0]))
        dark_block = re.search(r"@media \(prefers-color-scheme: dark\)\s*\{\s*:root\s*\{(.*?)\}", css, re.S).group(1)
        dark = {**light, **dict(re.findall(r"--([\w-]+):\s*(#[0-9a-fA-F]{6})", dark_block))}
        return {"light": light, "dark": dark}

    def test_pairs(self):
        for mode, t in self.tokens().items():
            for fg, bg in self.PAIRS:
                with self.subTest(mode=mode, pair=(fg, bg)):
                    self.assertGreaterEqual(contrast(t[fg], t[bg]), 4.5, f"{fg} on {bg}: {contrast(t[fg], t[bg]):.2f}")


if __name__ == "__main__":
    unittest.main()


class Font(unittest.TestCase):
    def test_subset_covers_the_course(self):
        try:
            from fontTools.ttLib import TTFont
            import brotli  # noqa: F401  (needed to read woff2)
        except ImportError:
            self.skipTest("fontTools and brotli are not installed")
        sys.path.insert(0, str(ROOT / "tools"))
        import build_font
        have = set(chr(c) for c in TTFont(build_font.OUT).getBestCmap())
        missing = sorted(c for c in build_font.course_characters() if c not in have)
        self.assertEqual(missing, [], "run python3 tools/build_font.py --source … to add these characters: " + "".join(missing))
