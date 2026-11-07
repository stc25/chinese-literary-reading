#!/usr/bin/env python3
"""List the numbered occurrences of a term in a passage's ## Text.

Use this to find the right #n for an occurrence-specific gloss.

Usage:
    python3 tools/occurrences.py PASSAGE_FILE TERM

TERM may be a split construction such as "非 … 不". Occurrences inside
longer words are counted, exactly as the validator and the app count them.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import validate  # noqa: E402

CONTEXT = 6


def occurrences(path: Path, term: str) -> list[str]:
    rep = validate.Report()
    doc = validate.parse_doc(path, "passage", rep)
    if doc is None:
        raise SystemExit(f"{path}: cannot read the file ({'; '.join(i.msg for i in rep.issues)})")
    validate.check_sections(doc, rep)
    sec = doc.sections.get("Text")
    if sec is None:
        raise SystemExit(f"{path}: no ## Text section")
    text = "\n".join("".join(p.split()) for _, p in sec.paragraphs())
    parts = [p.strip() for p in term.replace("...", "…").split("…")]
    lines = []
    for k, i in enumerate(validate.find_term(text, parts), 1):
        end = i + len(parts[0])
        before = text[max(0, i - CONTEXT):i].replace("\n", " ¶ ")
        after = text[end:end + CONTEXT].replace("\n", " ¶ ")
        lines.append(f"#{k}: …{before}【{text[i:end]}】{after}…")
    return lines


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 2:
        print(__doc__.strip().split("\n\n")[1])
        return 2
    path, term = Path(args[0]), args[1]
    found = occurrences(path, term)
    if not found:
        print(f"“{term}” does not occur in ## Text")
        return 1
    print("\n".join(found))
    return 0


if __name__ == "__main__":
    sys.exit(main())
