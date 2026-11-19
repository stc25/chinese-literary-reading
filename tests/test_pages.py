"""Tests for the course pages under Django (ported from tests/test_app.py, same assertions).

Run with:  python manage.py test tests.test_pages
"""
import re
import unittest

from tests.django_helpers import (CONTENT, current_course, no_network, oidc_settings, page_settings, sso_sign_in,
                                  start_test_database, stop_test_database)

from django.test import Client, SimpleTestCase, TestCase

from app.content import load

_db = None


def setUpModule():
    global _db
    _db = start_test_database()


def tearDownModule():
    stop_test_database(_db)


def oidc_mode():
    return oidc_settings()


@page_settings()
class Pages(SimpleTestCase):
    def test_course_map(self):
        html = self.client.get("/").content.decode()
        self.assertIn('href="/units/u01"', html)

    def test_unit_page(self):
        r = self.client.get("/units/u01")
        self.assertEqual(r.status_code, 200)
        self.assertIn('href="/units/u01/p01"', r.content.decode())

    def test_passage_page(self):
        r = self.client.get("/units/u01/p01")
        self.assertEqual(r.status_code, 200)
        html = r.content.decode()
        self.assertIn('lang="zh-Hant"', html)
        self.assertIn('class="translation-para"', html)
        self.assertIn('id="gloss-data"', html)

    def test_glossed_words_are_buttons(self):
        html = self.client.get("/units/u01/p01").content.decode()
        self.assertIn('<button type="button" class="g" data-occ="0-0"', html)
        # the second 曰 is the second occurrence of gloss 8
        self.assertIn('data-occ="8-1"', html)

    def test_view_parameter(self):
        html = self.client.get("/units/u01/p01?view=vertical").content.decode()
        self.assertIn('class="reader view-vertical"', html)
        html = self.client.get("/units/u01/p01?view=sideways").content.decode()
        self.assertIn('class="reader view-modern"', html)

    def test_draft_tag_is_for_reviewers_only(self):
        html = self.client.get("/units/u01/p01").content.decode()
        self.assertNotIn("badge-draft", html)
        self.assertNotIn("Development", html)
        self.assertNotIn("notice-draft", html)
        with page_settings(DEV_USER="rv1", REVIEWERS=["rv1"]):
            reviewer = Client()     # the development user is a reviewer; switch reviewer mode on
            reviewer.post("/reviewer-mode", {"on": "1", "next": "/"})
            html = reviewer.get("/units/u01/p01").content.decode()
        self.assertIn("badge-draft", html)
        self.assertNotIn("notice-draft", html)     # the notice is gone for everyone

    def test_unknown_pages(self):
        for url in ("/units/u99", "/units/u01/p09", "/grammar/nothing", "/toolkit/t99"):
            self.assertEqual(self.client.get(url).status_code, 404, url)

    def test_404_renders_the_friendly_page(self):
        r = self.client.get("/units/u99")
        self.assertEqual(r.status_code, 404)
        self.assertIn("Page not found", r.content.decode())

    def test_review_list_is_hidden_without_a_reviewer(self):
        self.assertEqual(self.client.get("/review").status_code, 404)

    @page_settings(SHOW_UNREVIEWED=False)
    def test_hide_unreviewed(self):
        self.assertEqual(self.client.get("/units/u01/p01").status_code, 404)


@page_settings(CONTENT)
class RealContent(SimpleTestCase):
    """Every page of the real course renders, and no link points at a Markdown file."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.course = current_course()

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
                hrefs = re.findall(r'href="([^"]+)"', r.content.decode())
                self.assertFalse([h for h in hrefs if re.search(r"\.md($|#)", h)], "unresolved .md link")

    def test_internal_links_resolve(self):
        seen = set()
        for url in self.urls():
            html = self.client.get(url).content.decode()
            for h in re.findall(r'href="(/[^"#]*)', html):
                if h.startswith("/static/") or h in seen:
                    continue
                seen.add(h)
                with self.subTest(link=h, page=url):
                    self.assertEqual(self.client.get(h).status_code, 200)



@page_settings(CONTENT)
class M3Pages(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.course = load(CONTENT)

    def test_converter_form(self):
        html = self.client.get("/toolkit/t02?mode=reign&reign=光緒&year=24").content.decode()
        self.assertIn("光緒二十四年 = 1898 (戊戌)", html)

    def test_glossary_search(self):
        all_html = self.client.get("/glossary").content.decode()
        html = self.client.get("/glossary?q=qun").content.decode()
        self.assertIn(">群<", html)
        self.assertLess(len(html), len(all_html))
        self.assertIn(">群<", self.client.get("/glossary?q=society").content.decode())

    def test_index_pages(self):
        for url in ("/grammar", "/toolkit", "/glossary"):
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_summaries(self):
        data = self.client.get("/summaries.json").json()
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
        html = self.client.get("/units/u17/p02").content.decode()
        self.assertIn("g-earlier", html)
        self.assertIn('"from"', html)


@page_settings(CONTENT)
class Exercises(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.course = load(CONTENT)

    def test_choice_inputs(self):
        html = self.client.get("/units/u01/p01").content.decode()
        self.assertIn('data-ex="u01-p01#1"', html)
        self.assertIn('type="radio" name="u01-p01-ex1"', html)
        self.assertEqual(html.count("data-correct"), sum(
            1 for ex in self.course.passages["u01-p01"].exercises if ex.type == "choice" for ok, _ in ex.options if ok))

    def test_multi_select_uses_checkboxes(self):
        for p in self.course.passages.values():
            for ex in p.exercises:
                if ex.type == "choice" and sum(ok for ok, _ in ex.options) > 1:
                    html = self.client.get(f"/units/{p.unit_id}/{p.number}").content.decode()
                    self.assertIn(f'type="checkbox" name="{p.id}-ex{ex.number}"', html)
                    return
        self.skipTest("no multi-select exercise in the content")

    def test_punctuate_form(self):
        p = next(p for p in self.course.passages.values() if any(e.type == "punctuate" for e in p.exercises))
        ex = next(e for e in p.exercises if e.type == "punctuate")
        html = self.client.get(f"/units/{p.unit_id}/{p.number}").content.decode()
        self.assertIn(f'data-text="{ex.text}"', html)
        self.assertIn('class="punct-answer"', html)

    def test_toolkit_practice(self):
        html = self.client.get("/toolkit/t02").content.decode()
        self.assertIn('data-ex="t02#1"', html)
        self.assertIn("exercises.js", html)

    def test_progress_hooks(self):
        html = self.client.get("/").content.decode()
        self.assertIn("data-unit-passages=", html)
        self.assertIn('data-action="reset-progress"', html)
        html = self.client.get("/units/u05").content.decode()
        self.assertIn('data-passage="u05-p01"', html)



@page_settings(CONTENT)
class Deployment(SimpleTestCase):
    def test_accessibility_statement_is_public(self):
        with oidc_mode():
            r = self.client.get("/accessibility")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Accessibility statement", r.content.decode())

    def test_no_inline_scripts(self):
        """The CSP forbids inline scripts; JSON data blocks are allowed."""
        for url in ("/", "/units/u17/p02", "/glossary?q=qun", "/toolkit/t02"):
            html = self.client.get(url).content.decode()
            for attrs in re.findall(r"<script([^>]*)>", html):
                self.assertTrue("src=" in attrs or 'type="application/json"' in attrs, f"{url}: inline script")
            self.assertNotRegex(html, r"\son(click|load|change)=", url)

    def test_text_is_one_tab_stop(self):
        html = self.client.get("/units/u17/p02").content.decode()
        buttons = re.findall(r'<button type="button" class="g(?: [^"]*)?"[^>]*>', html)
        self.assertTrue(buttons)
        self.assertTrue(all('tabindex="-1"' in b for b in buttons))


@page_settings()
class ThemeAndFooter(SimpleTestCase):
    """The light/dark switch, its pre-paint script and the Language Centre footer (UI refresh)."""

    def test_page_has_theme_switch_and_scripts(self):
        html = self.client.get("/").content.decode()
        self.assertIn('id="theme-switch"', html)
        self.assertIn('role="switch"', html)
        # theme-init.js sets data-theme before first paint, so it must come before the stylesheets
        self.assertLess(html.index("js/theme-init.js"), html.index("css/tokens.css"))
        self.assertIn("js/theme.js", html)
        self.assertNotRegex(html, r"<script>")      # the CSP allows no inline scripts

    def test_footer(self):
        html = self.client.get("/").content.decode()
        self.assertIn('class="footer"', html)
        self.assertIn("Creative Commons Attribution-NonCommercial 4.0", html)
        self.assertIn("/accessibility", html)
        self.assertEqual(html.count("footer-img-light"), html.count("footer-img-dark"))

    def test_theme_and_footer_assets_are_served(self):
        for path in ("css/tokens.css", "css/footer.css", "js/theme-init.js", "js/theme.js", "js/back-to-top.js",
                     "img/icons.svg", "img/footer/ucam-lockup-light.png", "img/footer/ucam-lockup-dark.png"):
            r = self.client.get("/static/" + path)
            self.assertEqual(r.status_code, 200, path)
            r.close()


@page_settings()
class Landing(TestCase):
    """The landing page: public, with the sign-in button, and no course content."""

    def oidc(self):
        return self.client      # use inside `with oidc_mode():`

    def test_signed_out_visitor_sees_landing_at_root(self):
        with oidc_mode():
            r = self.oidc().get("/")
        self.assertEqual(r.status_code, 200)
        html = r.content.decode()
        self.assertIn("Sign in with your University of Cambridge account", html)
        self.assertIn('href="/login"', html)
        self.assertIn('id="theme-switch"', html)
        self.assertNotIn("/grammar", html.split('<footer')[0])      # no course navigation or links before sign-in
        # what sign-in keeps (accounts.pipeline.finish_login): the user name and the display name, no address
        self.assertIn("the site stores only your user name and display name", " ".join(html.split()))

    def test_sign_in_link_starts_the_sso(self):
        with oidc_mode(), no_network():
            r = self.oidc().get("/login")
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r["Location"].startswith("https://login.microsoftonline.com/"), r["Location"])

    def test_other_pages_still_require_sign_in(self):
        for path in ("/grammar", "/glossary", "/units/u01", "/assistant/"):
            with oidc_mode():
                r = self.oidc().get(path)
            self.assertEqual(r.status_code, 302, path)
            self.assertIn("/login", r.headers["Location"], path)
        with oidc_mode():      # data for scripts: a JSON answer, not a redirect (plan Review Focus)
            r = self.oidc().get("/summaries.json")
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.json(), {"error": "sign-in required"})

    def test_welcome_page_in_development_links_to_course(self):
        r = self.client.get("/welcome")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Open the course", r.content.decode())

    def test_signed_in_user_gets_course_map_at_root(self):
        from accounts.models import AllowedLogin
        AllowedLogin(entry="cz201").save()
        with oidc_mode():
            sso_sign_in(self.oidc())
            html = self.oidc().get("/").content.decode()
        self.assertIn('id="units"', html)
        self.assertNotIn("landing-hero", html)


@page_settings()
class Routing(SimpleTestCase):
    def test_handler404_is_ours(self):
        from django.urls import get_resolver

        from app.views import not_found
        self.assertIs(get_resolver().resolve_error_handler(404), not_found)

    def test_assistant_without_slash_redirects(self):
        r = self.client.get("/assistant")
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r["Location"], "/assistant/")

    def test_pages_are_get_only(self):
        for url in ("/", "/welcome", "/units/u01", "/units/u01/p01", "/grammar", "/grammar/ye-topic",
                    "/summaries.json", "/toolkit", "/glossary", "/accessibility", "/review"):
            with self.subTest(url=url):
                self.assertEqual(self.client.post(url).status_code, 405)
                self.assertEqual(self.client.head(url).status_code in (200, 404), True)
