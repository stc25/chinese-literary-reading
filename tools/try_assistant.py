#!/usr/bin/env python3
"""Run the reading assistant's steps on a text from the command line.

Usage:
    python3 tools/try_assistant.py "日本人之稱我中國也……" [--model qwen3.5:9b] [--host URL] [--steps words,grammar]
    echo "……" | python3 tools/try_assistant.py -

Uses a local Ollama server by default (http://localhost:11434). For the cloud service,
pass --host https://ollama.com and set OLLAMA_API_KEY in the environment.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.assistant import steps  # noqa: E402
from app.assistant.client import ModelError, OllamaClient, Usage  # noqa: E402
from app.assistant.lookup import analyse  # noqa: E402
from app.assistant.prompts import PROMPT_VERSION  # noqa: E402
from app.content import load  # noqa: E402
from app.content.glossary import build  # noqa: E402

ALL = ["punctuate", "words", "grammar", "names", "translate"]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("text", help="the text, or - to read it from standard input")
    ap.add_argument("--model", default="qwen3.5:9b")
    ap.add_argument("--host", default="http://localhost:11434")
    ap.add_argument("--steps", default=",".join(ALL), help="comma-separated: " + ",".join(ALL))
    ap.add_argument("--literal", action="store_true", help="also ask for a literal translation")
    args = ap.parse_args(argv)

    text = sys.stdin.read() if args.text == "-" else args.text
    course = load(ROOT / "content")
    a = analyse(text, course, build(course), max_chars=5000)
    p = a.prepared
    print(f"Text{' (converted from simplified)' if p.converted else ''}: {p.text}")
    print(f"Course glossary covers {a.coverage:.0%}; not covered: {'、'.join(p.text[x:y] for x, y in a.gaps) or '-'}")
    for d in a.dates:
        print(f"Date: {d.text} → {'; '.join(d.lines)}")
    print(f"Model: {args.model} at {args.host}; prompts {PROMPT_VERSION}\n")

    client = OllamaClient(args.host, args.model, api_key=os.environ.get("OLLAMA_API_KEY", ""), timeout=120)
    total = Usage()
    for step in [s.strip() for s in args.steps.split(",") if s.strip()]:
        try:
            if step == "punctuate":
                r = steps.punctuate(client, p.text)
                print("PUNCTUATION:", r.data["punctuated"])
            elif step == "words":
                r = steps.gloss_gaps(client, a)
                print("WORDS (AI):")
                for w in r.data["words"]:
                    print(f"  {w['word']}  {w['pinyin']}  {w['gloss']}")
            elif step == "grammar":
                r = steps.grammar_notes(client, a, course)
                print("FUNCTION WORDS (AI notes):")
                for n in r.data["notes"]:
                    print(f"  {n['form']} in 「{n['clause']}」 [{n['grammar_id'] or '-'}]: {n['note']}")
            elif step == "names":
                r = steps.names(client, a)
                print("NAMES AND ALLUSIONS (AI):")
                for it in r.data["items"]:
                    print(f"  {it['text']} ({it['kind']}): {it['note']}")
            elif step == "translate":
                r = steps.translate(client, p.text, literal=args.literal)
                print("TRANSLATION (AI):", r.data["translation"])
                if "literal" in r.data:
                    print("LITERAL (AI):", r.data["literal"])
            else:
                print(f"unknown step {step}")
                continue
        except ModelError as e:
            print(f"{step.upper()}: failed: {e}")
            continue
        u = r.usage
        total.add(u)
        print(f"  [{u.calls} call(s), {u.prompt_tokens} + {u.output_tokens} tokens, {u.seconds:.1f} s]\n")
    print(f"Total: {total.calls} calls, {total.prompt_tokens} prompt + {total.output_tokens} output tokens, {total.seconds:.1f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
