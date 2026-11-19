"""The accessibility checks of tests/test_accessibility.py, run against the Django views.

Automated accessibility checks (part of WCAG 2.2 AA) over every page of the course.

These cover what can be checked from the HTML and CSS alone: document language,
headings, labels, accessible names, ids, ARIA references and colour contrast.
They do not replace testing with a screen reader and a keyboard.
"""
import re
import sys
import unittest
from html.parser import HTMLParser
from pathlib import Path

from tests.django_helpers import ROOT, current_course, page_settings  # noqa: E402  (sets up Django first)

from django.test import SimpleTestCase  # noqa: E402

CSS = ROOT / "app" / "static" / "css" / "site.css"
TOKENS = ROOT / "app" / "static" / "css" / "tokens.css"
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


@page_settings(ROOT / "content", REVIEWERS=["rv1"], DEV_USER="rv1")
class Pages(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        c = current_course()
        # The development user rv1 is a reviewer and pages() switches reviewer mode on, so the
        # reviewer-only markup (notes, Draft tags, the review list) is checked too.
        cls.urls = (["/", "/grammar", "/toolkit", "/glossary?q=qun", "/accessibility", "/review", "/signed-out", "/assistant/", "/assistant/help",
                     "/toolkit/t02?mode=reign&reign=光緒&year=24"]
                    + [f"/units/{u}" for u in c.units]
                    + [f"/units/{p.unit_id}/{p.number}" for p in c.passages.values()]
                    + [f"/units/{p.unit_id}/{p.number}?view=vertical" for p in list(c.passages.values())[:5]]
                    + [f"/grammar/{g}" for g in c.grammar]
                    + [f"/toolkit/{t}" for t in c.toolkit])

    def pages(self):
        r = self.client.post("/reviewer-mode", {"on": "1", "next": "/"})
        self.assertEqual(r.status_code, 302)
        self.assertIn('class="review-note"', self.client.get("/units/u17/p01").content.decode())
        for url in self.urls:
            html = self.client.get(url).content.decode()
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


def parse_colour(value, tokens, backdrop=(1, 1, 1)):
    """A CSS colour from tokens.css/site.css as 0-1 RGB: #hex, rgba() (composited on `backdrop`),
    var(--x) and color-mix(in srgb, A p%, B)."""
    v = value.strip()
    m = re.fullmatch(r"var\(--([\w-]+)\)", v)
    if m:
        return parse_colour(tokens[m.group(1)], tokens, backdrop)
    m = re.fullmatch(r"color-mix\(in srgb,\s*(.+?)\s+(\d+)%,\s*(.+)\)", v)
    if m:
        x, y = parse_colour(m.group(1), tokens, backdrop), parse_colour(m.group(3), tokens, backdrop)
        k = int(m.group(2)) / 100
        return tuple(k * i + (1 - k) * j for i, j in zip(x, y))
    if v.startswith("#"):
        h = v[1:]
        h = "".join(c * 2 for c in h) if len(h) == 3 else h
        return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    m = re.fullmatch(r"rgba?\(([^)]*)\)", v)
    p = [float(x) for x in m.group(1).split(",")]
    a = p[3] if len(p) > 3 else 1.0
    return tuple(a * p[i] / 255 + (1 - a) * backdrop[i] for i in range(3))


def luminance(rgb):
    def ch(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


class Contrast(SimpleTestCase):
    """Text colour pairs from the design tokens meet 4.5:1 (normal text) in light and dark mode."""

    PAIRS = [
        ("text", "bg"), ("text", "surface"), ("muted", "bg"), ("muted", "surface"), ("link", "bg"),
        ("link", "surface"), ("accent", "bg"), ("draft-text", "draft-bg"), ("error-text", "error-bg"),
        ("surface", "accent"),   # current layout button
        ("muted", "rule"),       # badges
        ("text", "accent-soft"),  # highlighted words
    ]

    def tokens(self):
        """Light and dark token values: tokens.css, then the course aliases in site.css (:root)."""
        def decls(text):
            return dict(re.findall(r"--([\w-]+)\s*:\s*([^;]+);", text))

        def block(css, selector):
            m = re.search(re.escape(selector) + r"\s*\{(.*?)\n?\}", css, re.S)
            return decls(m.group(1)) if m else {}

        tk, site = TOKENS.read_text(encoding="utf-8"), CSS.read_text(encoding="utf-8")
        light = {**block(tk, ":root"), **block(site, ":root")}
        dark = {**light, **block(tk, ':root[data-theme="dark"]'), **block(site, ':root[data-theme="dark"]')}
        return {"light": light, "dark": dark}

    def test_pairs(self):
        for mode, t in self.tokens().items():
            for fg, bg in self.PAIRS:
                with self.subTest(mode=mode, pair=(fg, bg)):
                    page = parse_colour("var(--bg)", t)      # translucent colours (the rule) sit on the page
                    c = contrast(parse_colour(f"var(--{fg})", t, page), parse_colour(f"var(--{bg})", t, page))
                    self.assertGreaterEqual(c, 4.5, f"{fg} on {bg}: {c:.2f}")


if __name__ == "__main__":
    unittest.main()


class Font(SimpleTestCase):
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
