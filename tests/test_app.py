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

    def test_draft_tag_is_for_reviewers_only(self):
        html = self.client.get("/units/u01/p01").get_data(as_text=True)
        self.assertNotIn("badge-draft", html)
        self.assertNotIn("Development", html)
        self.assertNotIn("notice-draft", html)
        reviewer = make_app(REVIEWERS=["dev"]).test_client()
        with reviewer.session_transaction() as s:
            s["review_mode"] = True
        html = reviewer.get("/units/u01/p01").get_data(as_text=True)
        self.assertIn("badge-draft", html)
        self.assertNotIn("notice-draft", html)     # the notice is gone for everyone

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


class Exercises(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = make_app(CONTENT).test_client()
        cls.course = load(CONTENT)

    def test_choice_inputs(self):
        html = self.client.get("/units/u01/p01").get_data(as_text=True)
        self.assertIn('data-ex="u01-p01#1"', html)
        self.assertIn('type="radio" name="u01-p01-ex1"', html)
        self.assertEqual(html.count("data-correct"), sum(
            1 for ex in self.course.passages["u01-p01"].exercises if ex.type == "choice" for ok, _ in ex.options if ok))

    def test_multi_select_uses_checkboxes(self):
        for p in self.course.passages.values():
            for ex in p.exercises:
                if ex.type == "choice" and sum(ok for ok, _ in ex.options) > 1:
                    html = self.client.get(f"/units/{p.unit_id}/{p.number}").get_data(as_text=True)
                    self.assertIn(f'type="checkbox" name="{p.id}-ex{ex.number}"', html)
                    return
        self.skipTest("no multi-select exercise in the content")

    def test_punctuate_form(self):
        p = next(p for p in self.course.passages.values() if any(e.type == "punctuate" for e in p.exercises))
        ex = next(e for e in p.exercises if e.type == "punctuate")
        html = self.client.get(f"/units/{p.unit_id}/{p.number}").get_data(as_text=True)
        self.assertIn(f'data-text="{ex.text}"', html)
        self.assertIn('class="punct-answer"', html)

    def test_toolkit_practice(self):
        html = self.client.get("/toolkit/t02").get_data(as_text=True)
        self.assertIn('data-ex="t02#1"', html)
        self.assertIn("exercises.js", html)

    def test_progress_hooks(self):
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn("data-unit-passages=", html)
        self.assertIn('data-action="reset-progress"', html)
        html = self.client.get("/units/u05").get_data(as_text=True)
        self.assertIn('data-passage="u05-p01"', html)


OIDC = {
    "AUTH_MODE": "oidc",
    "OIDC_METADATA_URL": "https://login.example.test/.well-known/openid-configuration",
    "OIDC_CLIENT_ID": "client",
    "OIDC_CLIENT_SECRET": "secret",
    "SECRET_KEY": "a-long-random-test-key-0123456789",
    "REVIEWERS": ["cz201"],
}


class SignIn(unittest.TestCase):
    """OIDC sign-in, with the identity provider replaced by a stub."""

    def setUp(self):
        self.app = make_app(CONTENT, **OIDC)
        self.client = self.app.test_client()
        self.sso = self.app.extensions["oauth_sso"]

    def sign_in(self, username="cz201@cam.ac.uk", name="C. Z."):
        from unittest import mock
        token = {"userinfo": {"preferred_username": username, "name": name, "sub": "x"}}
        with mock.patch.object(self.sso, "authorize_access_token", return_value=token):
            return self.client.get("/auth/callback")

    def csrf(self, html):
        return re.search(r'name="csrf" value="([^"]+)"', html).group(1)

    def test_pages_need_sign_in(self):
        r = self.client.get("/units/u01")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login?next=/units/u01", r.location)

    def test_open_pages(self):
        self.assertEqual(self.client.get("/healthz").status_code, 200)
        self.assertEqual(self.client.get("/static/css/site.css").status_code, 200)

    def test_login_redirects_to_provider(self):
        from unittest import mock
        from flask import redirect
        with mock.patch.object(self.sso, "authorize_redirect", return_value=redirect("https://login.example.test/auth")) as m:
            r = self.client.get("/login?next=/glossary")
        self.assertEqual(r.location, "https://login.example.test/auth")
        self.assertTrue(m.call_args[0][0].endswith("/auth/callback"))

    def test_sign_in_and_return(self):
        with self.client.session_transaction() as s:
            s["next"] = "/glossary"
        r = self.sign_in()
        self.assertEqual(r.location, "/glossary")
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn("C. Z.", html)
        self.assertIn("Reviewer notes: off", html)

    def test_non_cambridge_account_refused(self):
        r = self.sign_in("someone@example.com")
        self.assertEqual(r.status_code, 403)
        self.assertEqual(self.client.get("/glossary").status_code, 302)     # still not signed in

    def test_failed_exchange(self):
        from unittest import mock
        with mock.patch.object(self.sso, "authorize_access_token", side_effect=ValueError("bad state")):
            self.assertEqual(self.client.get("/auth/callback").status_code, 400)

    def test_learner_is_not_reviewer(self):
        self.sign_in("ab123@cam.ac.uk", "A. B.")
        html = self.client.get("/").get_data(as_text=True)
        self.assertNotIn("Reviewer notes", html)
        self.assertEqual(self.client.get("/review").status_code, 404)

    def test_no_open_redirect(self):
        with self.client.session_transaction() as s:
            s["next"] = "//evil.example.com/"
        self.assertEqual(self.sign_in().location, "/")

    def test_logout_needs_token(self):
        self.sign_in()
        self.assertEqual(self.client.post("/logout").status_code, 400)
        token = self.csrf(self.client.get("/").get_data(as_text=True))
        r = self.client.post("/logout", data={"csrf": token})
        self.assertIn("/signed-out", r.location)
        self.assertEqual(self.client.get("/glossary").status_code, 302)
        self.assertIn("Sign in with", self.client.get("/").get_data(as_text=True))   # back to the landing page

    def test_session_cookie_is_secure(self):
        r = self.sign_in()
        cookie = r.headers.get("Set-Cookie", "")
        self.assertIn("Secure", cookie)
        self.assertIn("HttpOnly", cookie)

    def test_missing_settings(self):
        with self.assertRaises(RuntimeError):
            make_app(CONTENT, AUTH_MODE="oidc")
        with self.assertRaises(RuntimeError):
            make_app(CONTENT, **{**OIDC, "SECRET_KEY": ""})


class Reviewers(unittest.TestCase):
    def client_for(self, user, **config):
        return make_app(CONTENT, DEV_USER=user, REVIEWERS=["cz201"], **config).test_client()

    def turn_on(self, client):
        html = client.get("/").get_data(as_text=True)
        token = re.search(r'name="csrf" value="([^"]+)"', html).group(1)
        client.post("/reviewer-mode", data={"csrf": token, "on": "1", "next": "/"})

    def test_notes_hidden_until_switched_on(self):
        c = self.client_for("cz201")
        self.assertNotIn('class="review-note"', c.get("/units/u17/p01").get_data(as_text=True))
        self.turn_on(c)
        self.assertIn('class="review-note"', c.get("/units/u17/p01").get_data(as_text=True))

    def test_learners_never_see_notes(self):
        c = self.client_for("ab123")
        self.assertEqual(c.post("/reviewer-mode", data={"on": "1"}).status_code, 400)  # no token
        self.assertNotIn('class="review-note"', c.get("/units/u17/p01").get_data(as_text=True))

    def test_every_note_is_placed(self):
        course = load(CONTENT)
        pages = [*course.units.values(), *course.passages.values(), *course.grammar.values(), *course.toolkit.values()]
        notes = [r for pg in pages for r in pg.reviews]
        self.assertTrue(notes)
        for r in notes:
            self.assertTrue(r.body and not r.body.startswith("REVIEW"))
        c = self.client_for("cz201")
        self.turn_on(c)
        shown = 0
        for pg in pages:
            if pg.reviews:
                url = course.urls[pg.path.resolve()]
                shown += c.get(url).get_data(as_text=True).count('class="review-note"')
        self.assertEqual(shown, len(notes), "every REVIEW comment appears on its page")

    def test_review_list(self):
        c = self.client_for("cz201")
        self.assertEqual(c.get("/review").status_code, 200)
        self.assertEqual(self.client_for("ab123").get("/review").status_code, 404)

    def test_reviewers_see_unreviewed_pages_at_release(self):
        self.assertEqual(self.client_for("ab123", SHOW_UNREVIEWED=False).get("/units/u17/p01").status_code, 404)
        self.assertEqual(self.client_for("cz201", SHOW_UNREVIEWED=False).get("/units/u17/p01").status_code, 200)


class Deployment(unittest.TestCase):
    def test_accessibility_statement_is_public(self):
        client = make_app(CONTENT, **OIDC).test_client()
        r = client.get("/accessibility")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Accessibility statement", r.get_data(as_text=True))

    def test_security_headers(self):
        client = make_app(CONTENT, **OIDC).test_client()
        r = client.get("/healthz")
        self.assertIn("default-src 'self'", r.headers["Content-Security-Policy"])
        self.assertEqual(r.headers["X-Content-Type-Options"], "nosniff")
        self.assertIn("max-age", r.headers["Strict-Transport-Security"])

    def test_no_inline_scripts(self):
        """The CSP forbids inline scripts; JSON data blocks are allowed."""
        client = make_app(CONTENT).test_client()
        for url in ("/", "/units/u17/p02", "/glossary?q=qun", "/toolkit/t02"):
            html = client.get(url).get_data(as_text=True)
            for attrs in re.findall(r"<script([^>]*)>", html):
                self.assertTrue("src=" in attrs or 'type="application/json"' in attrs, f"{url}: inline script")
            self.assertNotRegex(html, r"\son(click|load|change)=", url)

    def test_text_is_one_tab_stop(self):
        html = make_app(CONTENT).test_client().get("/units/u17/p02").get_data(as_text=True)
        buttons = re.findall(r'<button type="button" class="g(?: [^"]*)?"[^>]*>', html)
        self.assertTrue(buttons)
        self.assertTrue(all('tabindex="-1"' in b for b in buttons))

    def test_wsgi_entry_point(self):
        import importlib
        import os
        old = {k: os.environ.get(k) for k in ("MLC_AUTH_MODE",)}
        os.environ["MLC_AUTH_MODE"] = "none"
        try:
            sys.modules.pop("wsgi", None)
            wsgi = importlib.import_module("wsgi")
            self.assertEqual(wsgi.application.test_client().get("/healthz").status_code, 200)
        finally:
            for k, val in old.items():
                if val is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = val


class EnvFile(unittest.TestCase):
    def write(self, text):
        d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, d)
        (d / ".env").write_text(text, encoding="utf-8")
        return d / ".env"

    def test_read(self):
        from app import read_env_file
        f = self.write('# comment\nOllama_API="abc"\nMLC_OLLAMA_HOST=https://ollama.com\n'
                       'export MLC_ASSISTANT_DAILY_LIMIT=10\nMLC_REVIEWERS=["a"]\nOTHER=x\n\n')
        self.assertEqual(read_env_file(f), {"OLLAMA_API_KEY": "abc", "OLLAMA_HOST": "https://ollama.com",
                                            "ASSISTANT_DAILY_LIMIT": 10, "REVIEWERS": ["a"]})
        self.assertEqual(read_env_file(f.parent / "missing"), {})

    def test_app_uses_file_but_environment_and_config_win(self):
        import os
        from unittest import mock
        f = self.write("MLC_ASSISTANT_MODEL=from-file\nMLC_OLLAMA_HOST=from-file\nOllama_API=k\n")
        with mock.patch.dict(os.environ, {"MLC_OLLAMA_HOST": "from-env"}):
            app = make_app(ENV_FILE=f, ASSISTANT_DAILY_LIMIT=5)
        self.assertEqual(app.config["ASSISTANT_MODEL"], "from-file")
        self.assertEqual(app.config["OLLAMA_HOST"], "from-env")
        self.assertEqual(app.config["OLLAMA_API_KEY"], "k")

    def test_tests_ignore_the_real_file(self):
        self.assertEqual(make_app().config["OLLAMA_API_KEY"], "")

    def test_env_files_are_ignored_by_git(self):
        self.assertIn(".env", (Path(__file__).resolve().parent.parent / ".gitignore").read_text().split())


class ThemeAndFooter(unittest.TestCase):
    """The light/dark switch, its pre-paint script and the Language Centre footer (UI refresh)."""

    def setUp(self):
        self.client = make_app().test_client()

    def test_page_has_theme_switch_and_scripts(self):
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn('id="theme-switch"', html)
        self.assertIn('role="switch"', html)
        # theme-init.js sets data-theme before first paint, so it must come before the stylesheets
        self.assertLess(html.index("js/theme-init.js"), html.index("css/tokens.css"))
        self.assertIn("js/theme.js", html)
        self.assertNotRegex(html, r"<script>")      # the CSP allows no inline scripts

    def test_footer(self):
        html = self.client.get("/").get_data(as_text=True)
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


class Landing(unittest.TestCase):
    """The landing page: public, with the sign-in button, and no course content."""

    def oidc(self):
        return make_app(AUTH_MODE="oidc", SECRET_KEY="x" * 40, OIDC_METADATA_URL="https://example.invalid/.well-known",
                        OIDC_CLIENT_ID="id", OIDC_CLIENT_SECRET="secret").test_client()

    def test_signed_out_visitor_sees_landing_at_root(self):
        r = self.oidc().get("/")
        self.assertEqual(r.status_code, 200)
        html = r.get_data(as_text=True)
        self.assertIn("Sign in with your University of Cambridge account", html)
        self.assertIn('href="/login"', html)
        self.assertIn('id="theme-switch"', html)
        self.assertNotIn("/grammar", html.split('<footer')[0])      # no course navigation or links before sign-in

    def test_other_pages_still_require_sign_in(self):
        for path in ("/grammar", "/glossary", "/units/u01", "/assistant/", "/summaries.json"):
            r = self.oidc().get(path)
            self.assertEqual(r.status_code, 302, path)
            self.assertIn("/login", r.headers["Location"], path)

    def test_welcome_page_in_development_links_to_course(self):
        r = make_app().test_client().get("/welcome")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Open the course", r.get_data(as_text=True))

    def test_signed_in_user_gets_course_map_at_root(self):
        c = self.oidc()
        with c.session_transaction() as s:
            s["user"] = {"id": "abc1", "name": "A B", "reviewer": False}
        html = c.get("/").get_data(as_text=True)
        self.assertIn('id="units"', html)
        self.assertNotIn("landing-hero", html)
