#!/usr/bin/env python3
"""Build the web font: Noto Serif TC, cut down to the characters the course uses.

The full font is about 24 MB; the subset is about 1 MB, served by
the app itself (no third-party font requests).

Usage:
    python3 tools/build_font.py --source path/to/NotoSerifCJKtc-Regular.otf [--check]

Get the source font (SIL Open Font License) from
https://github.com/notofonts/noto-cjk/tree/main/Serif/OTF/TraditionalChinese
(the full CJK font: the smaller "SubsetOTF/TC" version lacks old forms such as 爲, 敎, 緖).

Run it again after adding passages, so that new characters are included; a
test reports characters that the subset is missing. With --check, only report.
Requires fontTools and brotli (pip install fonttools brotli).
"""
from __future__ import annotations

import argparse
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "app" / "static" / "fonts" / "noto-serif-tc-subset.woff2"
SOURCES = [ROOT / "content", ROOT / "app" / "templates"]

# Always include full-width punctuation and the CJK symbols block, so that any
# punctuation typed in exercises looks the same as the text.
EXTRA = "".join(chr(c) for c in range(0x3000, 0x3040)) + "".join(chr(c) for c in range(0xFF01, 0xFF5F)) + "…—·・"


def wanted(c: str) -> bool:
    """Characters that should be drawn with the Chinese font: CJK and its punctuation."""
    o = ord(c)
    if o < 0x2E80:
        return c in "…—·"
    name = unicodedata.category(c)
    return name[0] in "LNPS" or o in range(0x3000, 0x3040)


def course_characters() -> set[str]:
    chars: set[str] = set(EXTRA)
    for src in SOURCES:
        for p in src.rglob("*"):
            if p.suffix in (".md", ".html", ".csv"):
                chars.update(c for c in p.read_text(encoding="utf-8") if wanted(c))
    return chars


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--source", type=Path, help="NotoSerifTC-Regular.otf (or another OpenType font)")
    ap.add_argument("--check", action="store_true", help="only report characters missing from the built subset")
    args = ap.parse_args(argv)

    from fontTools import subset
    from fontTools.ttLib import TTFont

    chars = course_characters()
    if args.check:
        have = set(chr(c) for c in TTFont(OUT).getBestCmap())
        missing = sorted(c for c in chars if c not in have and c not in EXTRA)
        print(f"{OUT.name}: {len(have)} characters; {len(missing)} used in the course are missing"
              + (": " + "".join(missing) if missing else "."))
        return 1 if missing else 0
    if not args.source:
        ap.error("--source is required to build the font")

    font = TTFont(args.source)
    cmap = font.getBestCmap()
    available = {c for c in chars if ord(c) in cmap}
    not_in_font = sorted(chars - available - set(EXTRA))

    options = subset.Options()
    options.flavor = "woff2"
    options.layout_features = ["vert", "vrt2", "vkrn", "vpal", "locl", "kern", "palt", "halt"]  # vertical forms for vertical text
    options.name_IDs = ["*"]
    options.notdef_outline = True
    options.hinting = False
    sub = subset.Subsetter(options)
    sub.populate(unicodes=[ord(c) for c in available])
    sub.subset(font)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    font.flavor = "woff2"
    font.save(OUT)
    print(f"Wrote {OUT.relative_to(ROOT)}: {len(available)} characters, {OUT.stat().st_size // 1024} KB.")
    if not_in_font:
        print(f"{len(not_in_font)} characters are not in the source font and will use a system font: {''.join(not_in_font)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
