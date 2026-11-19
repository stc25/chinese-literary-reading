"""Lightweight browser check of the layout and accessibility, at several window sizes.

For every main page, in light and dark mode, at phone, tablet and desktop widths it checks that:
  * the page does not scroll sideways (WCAG 1.4.10 reflow, down to 320 px wide);
  * buttons and links are at least 24 x 24 px (WCAG 2.2 target size; links inside text, gloss buttons in
    the reading text and the browser's own checkboxes and radio buttons are exempt);
  * the page raises no JavaScript errors;
  * axe-core finds no WCAG 2.x A/AA violations (only when axe-core is available, see below).

It needs a browser, so it is skipped when Playwright or Chromium is not installed:

    pip install -r requirements-dev.txt && playwright install chromium
    python -m pytest tests/test_browser.py

Settings (environment variables, all optional):
    MLC_TEST_CHROMIUM   path to a Chromium or chrome-headless-shell binary, if Playwright's own is missing
    AXE_CORE_JS         path to axe.min.js (npm install axe-core; node_modules/axe-core/axe.min.js),
                        or put the file at tests/vendor/axe.min.js (not committed)
"""
import os
import sys
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import create_app  # noqa: E402

try:
    from playwright.sync_api import sync_playwright
except ImportError:                      # pragma: no cover
    sync_playwright = None

PAGES = ["/welcome", "/", "/units/u01", "/units/u01/p01", "/grammar", "/grammar/word-classes", "/glossary",
         "/toolkit", "/toolkit/t01", "/assistant/", "/assistant/help", "/accessibility"]
SIZES = [(320, 640), (768, 1024), (1440, 900)]
THEMES = ("light", "dark")

LAYOUT_JS = """() => {
  const de = document.documentElement, name = e => e.tagName.toLowerCase() +
    (typeof e.className === 'string' && e.className ? '.' + e.className.split(' ')[0] : '');
  const wide = [];
  for (const e of document.querySelectorAll('body *')) {
    const r = e.getBoundingClientRect();
    if (!r.width || r.right <= de.clientWidth + 1 || getComputedStyle(e).position === 'fixed') continue;
    let p = e.parentElement, clipped = false;
    while (p && p !== document.body) { if (getComputedStyle(p).overflowX !== 'visible') { clipped = true; break; } p = p.parentElement; }
    if (!clipped) wide.push(name(e) + ' +' + Math.round(r.right - de.clientWidth));
  }
  const small = [];
  for (const e of document.querySelectorAll('a, button, select, textarea, summary, input:not([type=radio]):not([type=checkbox])')) {
    const r = e.getBoundingClientRect(), cs = getComputedStyle(e);
    if (!r.width || cs.visibility === 'hidden' || e.closest('[hidden]')) continue;
    if (cs.display === 'inline' && e.tagName === 'A') continue;       // links inside running text
    if (e.matches('button.g')) continue;                              // gloss buttons inside the reading text
    if (r.width < 24 || r.height < 24) small.push(name(e) + ' ' + Math.round(r.width) + 'x' + Math.round(r.height));
  }
  return {scroll: de.scrollWidth - de.clientWidth, wide: [...new Set(wide)].slice(0, 6), small: [...new Set(small)].slice(0, 6)};
}"""

AXE_JS = """() => axe.run(document, {runOnly: {type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']}})
  .then(r => r.violations.map(v => v.id + ' [' + v.impact + '] ' + v.nodes.slice(0, 2).map(n => n.target.join(' ')).join('; ')))"""


def axe_source():
    for p in (os.environ.get("AXE_CORE_JS"), ROOT / "tests" / "vendor" / "axe.min.js"):
        if p and Path(p).is_file():
            return Path(p).read_text(encoding="utf-8")
    return None


@unittest.skipIf(sync_playwright is None, "Playwright is not installed (pip install -r requirements-dev.txt)")
class BrowserLayout(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from werkzeug.serving import make_server
        app = create_app({"TESTING": True, "CONTENT_DIR": ROOT / "content"})
        cls.server = make_server("127.0.0.1", 0, app, threaded=True)
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.pw = sync_playwright().start()
        try:
            exe = os.environ.get("MLC_TEST_CHROMIUM")
            cls.browser = cls.pw.chromium.launch(executable_path=exe) if exe else cls.pw.chromium.launch()
        except Exception as e:                                  # no browser installed
            cls.pw.stop()
            cls.server.shutdown()
            raise unittest.SkipTest(f"Chromium is not available ({str(e).splitlines()[0]})")
        cls.axe = axe_source()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.server.shutdown()

    def test_pages_at_every_size_and_theme(self):
        problems = []
        for theme in THEMES:
            for w, h in SIZES:
                ctx = self.browser.new_context(viewport={"width": w, "height": h}, color_scheme=theme,
                                               bypass_csp=True)      # only so axe can be injected
                ctx.add_init_script(f"try {{ localStorage.setItem('mlc-theme', '{theme}') }} catch (e) {{}}")
                page = ctx.new_page()
                errors = []
                page.on("pageerror", lambda e: errors.append(str(e)[:150]))
                page.on("console", lambda m: errors.append(m.text[:150]) if m.type == "error" else None)
                for path in PAGES:
                    where = f"{theme} {w}px {path}"
                    page.goto(self.base + path, wait_until="load")
                    r = page.evaluate(LAYOUT_JS)
                    if r["scroll"] > 0 or r["wide"]:
                        problems.append(f"{where}: page is {r['scroll']}px wider than the window ({', '.join(r['wide'])})")
                    if r["small"]:
                        problems.append(f"{where}: targets smaller than 24x24: {', '.join(r['small'])}")
                    if self.axe:
                        page.add_script_tag(content=self.axe)
                        problems += [f"{where}: axe {v}" for v in page.evaluate(AXE_JS)]
                if errors:
                    problems.append(f"{theme} {w}px: console errors: {sorted(set(errors))[:3]}")
                ctx.close()
        self.assertEqual(problems, [], "\n" + "\n".join(problems))


if __name__ == "__main__":
    unittest.main()
