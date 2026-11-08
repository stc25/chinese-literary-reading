#!/usr/bin/env python3
"""Generate content/glossary.md from the gloss tables of all passages.

Usage:
    python3 tools/build_glossary.py [--check]

With --check, exit with status 1 if content/glossary.md is out of date
instead of writing it. The web app builds the same glossary in memory.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.content import load  # noqa: E402
from app.content.glossary import build, to_markdown  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("content", nargs="?", type=Path, default=ROOT / "content")
    ap.add_argument("--check", action="store_true", help="only check that glossary.md is up to date")
    args = ap.parse_args(argv)

    course = load(args.content)
    entries = build(course)
    text = to_markdown(course, entries)
    out = args.content / "glossary.md"
    if args.check:
        current = out.read_text(encoding="utf-8") if out.exists() else ""
        if current != text:
            print(f"{out} is out of date; run python3 tools/build_glossary.py")
            return 1
        print(f"{out} is up to date ({len(entries)} entries).")
        return 0
    out.write_text(text, encoding="utf-8")
    print(f"Wrote {out} ({len(entries)} entries).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
