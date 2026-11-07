"""Markdown to HTML, with links between content files rewritten to app URLs."""
from __future__ import annotations

from pathlib import Path

from markdown_it import MarkdownIt
from markupsafe import Markup

from .loader import resolve_href


def _make_md() -> MarkdownIt:
    md = MarkdownIt("commonmark", {"html": False, "typographer": False}).enable("table")
    default_link = md.renderer.rules.get("link_open")

    def link_open(tokens, idx, options, env):
        token = tokens[idx]
        href = token.attrGet("href") or ""
        base: Path | None = env.get("base")
        urls = env.get("urls") or {}
        if base is not None:
            url = resolve_href(base, href, urls)
            if url is not None:
                token.attrSet("href", url)
                kind = url.split("/")[1] if url.count("/") >= 1 else ""
                if kind in ("grammar", "toolkit"):
                    token.attrSet("class", f"xref xref-{kind}")
                    token.attrSet("data-ref", url)
            elif href.startswith(("http://", "https://")):
                token.attrSet("rel", "noopener")
        if default_link:
            return default_link(tokens, idx, options, env)
        return md.renderer.renderToken(tokens, idx, options, env)

    md.renderer.rules["link_open"] = link_open

    default_table = md.renderer.rules.get("table_open")

    def table_open(tokens, idx, options, env):
        # wrap tables so they scroll sideways on narrow screens instead of the page
        html = default_table(tokens, idx, options, env) if default_table else md.renderer.renderToken(tokens, idx, options, env)
        return '<div class="table-wrap">' + html

    def table_close(tokens, idx, options, env):
        return md.renderer.renderToken(tokens, idx, options, env) + "</div>"

    md.renderer.rules["table_open"] = table_open
    md.renderer.rules["table_close"] = table_close
    return md


_MD = _make_md()


def render(text: str, base: Path | None = None, urls: dict | None = None) -> Markup:
    """Render a block of Markdown."""
    return Markup(_MD.render(text or "", {"base": base, "urls": urls or {}}))


def render_inline(text: str, base: Path | None = None, urls: dict | None = None) -> Markup:
    """Render Markdown without wrapping it in a paragraph."""
    return Markup(_MD.renderInline(text or "", {"base": base, "urls": urls or {}}))
