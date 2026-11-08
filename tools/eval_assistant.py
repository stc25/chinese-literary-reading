#!/usr/bin/env python3
"""Evaluate the reading assistant on the course passages and write a report.

Usage:
    python3 tools/eval_assistant.py [--model qwen3.5:9b] [--host URL] [--judge-model gemma3:12b]
                                    [--passages u05-p01,u17-p02 | --sample 15] [--out reports/]

For each passage (whose glosses and translation are reviewed):

- punctuation: the passage text with its punctuation removed is the input; the model's breaks
  are scored against the original (precision, recall, F1);
- words and glosses: the glossary is rebuilt WITHOUT the passage's own entries (leave-one-out),
  so the model has to gloss the passage's new words. Its word boundaries are compared with the
  course's glossed terms, and each gloss with the course gloss: automatically where they share an
  English content word, otherwise by a second model acting as judge;
- function words: the grammar point chosen by the model against the one in the course gloss;
- translation: the judge compares the model's translation with the course translation.

Tokens and time are recorded per step, to estimate the cost of a full analysis.
Use --host https://ollama.com and OLLAMA_API_KEY for cloud models.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.assistant import steps  # noqa: E402
from app.assistant.client import ModelError, OllamaClient, Usage  # noqa: E402
from app.assistant.evaluate import (PRF, boundaries, glosses_agree, score_major_breaks,  # noqa: E402
                                    score_punctuation, score_sets)
from app.assistant.lookup import analyse, key  # noqa: E402
from app.assistant.prompts import PROMPT_VERSION, SYSTEM  # noqa: E402
from app.content import load  # noqa: E402
from app.content.glossary import build, passages_in_order  # noqa: E402

JUDGE_GLOSS = """A word in a literary Chinese text has been glossed twice. Do the two glosses give the \
same sense of the word in this text? Answer "same" (same meaning, even if worded differently), "close" \
(overlapping but one is less precise), or "different".

Text: {text}
Word: {word}
Reference gloss: {ref}
Other gloss: {ai}"""

JUDGE_TRANSLATION = """Compare a translation of a literary Chinese text with a reference translation \
made by a specialist. Judge only meaning, not style. Answer "faithful" (no errors of meaning), "minor" \
(small errors or omissions that do not change the overall sense), or "wrong" (at least one serious \
error of meaning), and name the most serious error in one sentence, or "none".

Text: {text}
Reference translation: {ref}
Translation to judge: {ai}"""

GLOSS_SCHEMA = {"type": "object", "properties": {"verdict": {"type": "string", "enum": ["same", "close", "different"]}},
                "required": ["verdict"]}
TRANS_SCHEMA = {"type": "object", "properties": {"verdict": {"type": "string", "enum": ["faithful", "minor", "wrong"]},
                                                 "error": {"type": "string"}}, "required": ["verdict", "error"]}


def leave_one_out(entries, passage):
    """The glossary without the entries that only this passage provides."""
    return [e for e in entries if not (len(e.passages) == 1 and e.passages[0] is passage)]


def evaluate_passage(p, course, entries, client, judge, usage_by_step):
    rec = {"id": p.id, "title": p.title, "steps": {}}
    text = "".join(p.paragraphs)                   # one block; paragraph breaks are not tested

    def run(name, fn):
        t = time.monotonic()
        try:
            r = fn()
        except ModelError as e:
            rec["steps"][name] = {"error": str(e), "seconds": time.monotonic() - t}
            return None
        usage_by_step[name].append(r.usage)
        rec["steps"][name] = {"seconds": r.usage.seconds, "prompt_tokens": r.usage.prompt_tokens,
                              "output_tokens": r.usage.output_tokens}
        return r

    # 1. punctuation
    r = run("punctuate", lambda: steps.punctuate(client, text))    # the step removes the punctuation
    if r:
        s = score_punctuation(r.data["punctuated"], text)
        m = score_major_breaks(r.data["punctuated"], text)
        rec["steps"]["punctuate"].update(tp=s.tp, fp=s.fp, fn=s.fn, major_tp=m.tp, major_fp=m.fp, major_fn=m.fn,
                                         output=r.data["punctuated"], gold=text)

    # 2. words and glosses, with the passage's own glossary entries left out
    loo = leave_one_out(entries, p)
    a = analyse(text, course, loo, max_chars=10000)
    gold_terms = []
    for gl in p.glosses:
        if len(gl.parts) != 1:
            continue
        for start in [i for i in range(len(text)) if text.startswith(gl.term, i)][:1]:
            end = start + len(gl.term)
            if any(start < y and x < end for x, y in a.gaps):
                gold_terms.append({"term": gl.term, "gloss": gl.gloss, "span": (start, end)})
    rec["gaps"] = len(a.gaps)
    r = run("words", lambda: steps.gloss_gaps(client, a))
    if r:
        ai_words = r.data["words"]
        ai_spans = {s for w in ai_words for s in w["spans"]}
        gold_spans = {t["span"] for t in gold_terms}
        seg = score_sets(boundaries(ai_spans), boundaries(gold_spans))
        by_word = {key(w["word"]): w for w in ai_words}
        verdicts = []
        for t in gold_terms:
            w = by_word.get(key(t["term"]))
            if not w:
                a0, b0 = t["span"]
                other = [x for x in ai_words if any(a < b0 and a0 < b for a, b in x["spans"])]
                if other:   # the characters were glossed, as part of a longer or shorter word
                    verdicts.append({"term": t["term"], "course": t["gloss"], "ai": f"{other[0]['word']}: {other[0]['gloss']}",
                                     "verdict": "segmented differently"})
                else:
                    verdicts.append({"term": t["term"], "course": t["gloss"], "ai": None, "verdict": "missing"})
                continue
            agree = glosses_agree(w["gloss"], t["gloss"])
            verdict = "same (auto)" if agree else None
            if verdict is None and judge:
                try:
                    j = judge.chat_json(SYSTEM, JUDGE_GLOSS.format(text=text, word=t["term"], ref=t["gloss"], ai=w["gloss"]),
                                        GLOSS_SCHEMA)
                    usage_by_step["judge"].append(j.usage)
                    verdict = j.data["verdict"]
                except ModelError:
                    verdict = "unjudged"
            verdicts.append({"term": t["term"], "course": t["gloss"], "ai": w["gloss"], "verdict": verdict or "unjudged"})
        rec["steps"]["words"].update(seg_tp=seg.tp, seg_fp=seg.fp, seg_fn=seg.fn, glosses=verdicts,
                                     ai_words=[{"word": w["word"], "gloss": w["gloss"]} for w in ai_words])

    # 3. function words: compare with the grammar id in the course gloss at the same place
    full = analyse(text, course, entries, max_chars=10000)
    gold_grammar = {}
    for gl in p.glosses:
        if gl.grammar and gl.grammar in course.grammar:
            for spans in gl.spans:
                for x, y in spans:
                    # p.text has "\n" between paragraphs; the joined text does not
                    shift = p.text.count("\n", 0, x)
                    gold_grammar[(x - shift, y - shift)] = gl.grammar
    r = run("grammar", lambda: steps.grammar_notes(client, full, course))
    if r:
        checks = []
        for n in r.data["notes"]:
            gold = gold_grammar.get((n["start"], n["end"]))
            if gold and gold in n["candidates"] and len(n["candidates"]) > 1:
                checks.append({"form": n["form"], "clause": n["clause"], "gold": gold, "ai": n["grammar_id"],
                               "ok": n["grammar_id"] == gold})
        rec["steps"]["grammar"].update(checks=checks)

    # 4. translation
    r = run("translate", lambda: steps.translate(client, text))
    if r:
        ref = " ".join(p.translation)
        tr = {"output": r.data["translation"], "gold": ref}
        if judge:
            try:
                j = judge.chat_json(SYSTEM, JUDGE_TRANSLATION.format(text=text, ref=ref, ai=r.data["translation"]),
                                    TRANS_SCHEMA)
                usage_by_step["judge"].append(j.usage)
                tr.update(verdict=j.data["verdict"], judge_note=j.data.get("error", ""))
            except ModelError:
                tr["verdict"] = "unjudged"
        rec["steps"]["translate"].update(tr)
    return rec


def summarise(records, usage_by_step, args):
    punct = PRF(0, 0, 0)
    major = PRF(0, 0, 0)
    major_seen = False
    seg = PRF(0, 0, 0)
    gloss_counts = defaultdict(int)
    grammar_ok = grammar_n = 0
    trans_counts = defaultdict(int)
    failures = defaultdict(int)
    for rec in records:
        st = rec["steps"]
        for name, d in st.items():
            if "error" in d and "output" not in d:      # a failed call has an error and no output
                failures[name] += 1
        if "tp" in st.get("punctuate", {}):
            punct = punct + PRF(st["punctuate"]["tp"], st["punctuate"]["fp"], st["punctuate"]["fn"])
            if "major_tp" in st["punctuate"]:
                major_seen = True
                major = major + PRF(st["punctuate"]["major_tp"], st["punctuate"]["major_fp"], st["punctuate"]["major_fn"])
        w = st.get("words", {})
        if "seg_tp" in w:
            seg = seg + PRF(w["seg_tp"], w["seg_fp"], w["seg_fn"])
            for v in w["glosses"]:
                gloss_counts[v["verdict"].replace(" (auto)", "")] += 1
        for c in st.get("grammar", {}).get("checks", []):
            grammar_n += 1
            grammar_ok += c["ok"]
        if "verdict" in st.get("translate", {}):
            trans_counts[st["translate"]["verdict"]] += 1

    per_step = {}
    for name, us in usage_by_step.items():
        per_step[name] = {
            "calls": sum(u.calls for u in us),
            "prompt_tokens_avg": statistics.mean(u.prompt_tokens for u in us) if us else 0,
            "output_tokens_avg": statistics.mean(u.output_tokens for u in us) if us else 0,
            "seconds_avg": statistics.mean(u.seconds for u in us) if us else 0,
        }
    analysis_steps = ["punctuate", "words", "grammar", "translate"]
    tokens_per_analysis = sum(per_step.get(s, {}).get("prompt_tokens_avg", 0) + per_step.get(s, {}).get("output_tokens_avg", 0)
                              for s in analysis_steps)
    return {
        "model": args.model, "host": args.host, "judge": args.judge_model, "prompts": PROMPT_VERSION,
        "date": date.today().isoformat(), "passages": len(records),
        "punctuation": {"precision": punct.precision, "recall": punct.recall, "f1": punct.f1},
        "major_breaks": {"precision": major.precision, "recall": major.recall, "f1": major.f1} if major_seen else None,
        "segmentation": {"precision": seg.precision, "recall": seg.recall, "f1": seg.f1},
        "glosses": dict(gloss_counts),
        "grammar": {"checked": grammar_n, "correct": grammar_ok},
        "translation": dict(trans_counts),
        "failures": dict(failures),
        "per_step": per_step,
        "tokens_per_analysis": tokens_per_analysis,
    }


def pct(x):
    return f"{x:.0%}"


def write_report(summary, records, out: Path):
    s = summary
    g = s["glosses"]
    gtotal = sum(g.values()) or 1
    lines = [
        f"# Assistant evaluation: {s['model']}",
        "",
        f"{s['date']} · prompts `{s['prompts']}` · {s['passages']} passages · model at {s['host']} · "
        f"judge: {s['judge'] or 'none'}",
        "",
        "Generated by `tools/eval_assistant.py`. The reference is the course's own reviewed passages.",
        "",
        "## Summary",
        "",
        "| Step | Result |",
        "|---|---|",
        f"| Punctuation (breaks) | precision {pct(s['punctuation']['precision'])}, recall {pct(s['punctuation']['recall'])}, "
        f"F1 {pct(s['punctuation']['f1'])} |",
        (f"| Clause and sentence ends (。；：？！, extra commas forgiven) | precision {pct(s['major_breaks']['precision'])}, "
         f"recall {pct(s['major_breaks']['recall'])}, F1 {pct(s['major_breaks']['f1'])} |") if s.get("major_breaks")
        else "| Clause and sentence ends | not measured in this run |",
        f"| Word boundaries (new words) | precision {pct(s['segmentation']['precision'])}, recall "
        f"{pct(s['segmentation']['recall'])}, F1 {pct(s['segmentation']['f1'])} |",
        f"| Glosses of new words ({gtotal}) | same {pct(g.get('same', 0) / gtotal)}, close {pct(g.get('close', 0) / gtotal)}, "
        f"different {pct(g.get('different', 0) / gtotal)}, "
        f"segmented differently {pct(g.get('segmented differently', 0) / gtotal)}, not glossed {pct(g.get('missing', 0) / gtotal)}, "
        f"unjudged {pct(g.get('unjudged', 0) / gtotal)} |",
        f"| Grammar point chosen ({s['grammar']['checked']}) | "
        f"{pct(s['grammar']['correct'] / s['grammar']['checked']) if s['grammar']['checked'] else '-'} correct |",
        f"| Translation ({sum(s['translation'].values())}) | "
        + ", ".join(f"{k} {v}" for k, v in sorted(s["translation"].items())) + " |",
        f"| Failed calls | {', '.join(f'{k} {v}' for k, v in s['failures'].items()) or 'none'} |",
        "",
        "## Cost and speed per step",
        "",
        "Averages are per passage (the words step may make several calls for one passage).",
        "",
        "| Step | Calls | Prompt tokens (avg) | Output tokens (avg) | Seconds (avg) |",
        "|---|---|---|---|---|",
    ]
    for name, d in s["per_step"].items():
        lines.append(f"| {name} | {d['calls']} | {d['prompt_tokens_avg']:.0f} | {d['output_tokens_avg']:.0f} | {d['seconds_avg']:.1f} |")
    lines += ["", f"A full analysis (punctuation, words, grammar, translation) uses about "
              f"**{s['tokens_per_analysis']:.0f} tokens** on these passages; the names step and questions add to this.", ""]

    lines += ["## Worst punctuation", "", "| Passage | F1 | Model |", "|---|---|---|"]
    punct_rows = []
    for rec in records:
        d = rec["steps"].get("punctuate", {})
        if "tp" in d:
            punct_rows.append((PRF(d["tp"], d["fp"], d["fn"]).f1, rec["id"], d["output"]))
    for f1, pid, out_text in sorted(punct_rows)[:5]:
        lines.append(f"| {pid} | {pct(f1)} | {out_text[:80]}… |")

    lines += ["", "## Glosses judged different", "", "| Passage | Word | Course | AI |", "|---|---|---|---|"]
    n = 0
    for rec in records:
        for v in rec["steps"].get("words", {}).get("glosses", []):
            if v["verdict"] == "different" and n < 25:
                n += 1
                lines.append(f"| {rec['id']} | {v['term']} | {v['course']} | {v['ai']} |")

    lines += ["", "## Wrong grammar points", "", "| Passage | Word in clause | Course | AI |", "|---|---|---|---|"]
    for rec in records:
        for c in rec["steps"].get("grammar", {}).get("checks", []):
            if not c["ok"]:
                lines.append(f"| {rec['id']} | {c['form']} in 「{c['clause']}」 | {c['gold']} | {c['ai'] or '-'} |")

    lines += ["", "## Translations judged wrong", ""]
    for rec in records:
        t = rec["steps"].get("translate", {})
        if t.get("verdict") == "wrong":
            note = t.get("judge_note", t.get("error", ""))
            lines += [f"**{rec['id']}**: {note}", "", f"> AI: {t['output']}", ">", f"> Course: {t['gold']}", ""]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--model", default="qwen3.5:9b")
    ap.add_argument("--host", default="http://localhost:11434")
    ap.add_argument("--judge-model", default="gemma3:12b", help="model that judges glosses and translations; '' for none")
    ap.add_argument("--judge-host", default=None)
    ap.add_argument("--passages", help="comma-separated passage ids")
    ap.add_argument("--sample", type=int, default=0, help="evaluate N passages spread across the course")
    ap.add_argument("--out", type=Path, default=ROOT / "reports")
    ap.add_argument("--resummarise", type=Path, help="rebuild the report from a saved .json without calling the model")
    args = ap.parse_args(argv)

    if args.resummarise:
        saved = json.loads(args.resummarise.read_text(encoding="utf-8"))
        records, old = saved["records"], saved["summary"]
        usage_by_step = defaultdict(list)
        for rec in records:
            for name, d in rec["steps"].items():
                if "seconds" in d and "prompt_tokens" in d:
                    usage_by_step[name].append(Usage(d["prompt_tokens"], d["output_tokens"], d["seconds"], 1))
        if "judge" in old.get("per_step", {}):
            j = old["per_step"]["judge"]
            usage_by_step["judge"] = [Usage(round(j["prompt_tokens_avg"]), round(j["output_tokens_avg"]), j["seconds_avg"], 1)
                                      for _ in range(j["calls"])]
        args.model, args.host, args.judge_model = old["model"], old["host"], old["judge"]
        summary = summarise(records, usage_by_step, args)
        summary.update(date=old["date"], prompts=old["prompts"])
        args.resummarise.write_text(json.dumps({"summary": summary, "records": records}, ensure_ascii=False, indent=1),
                                    encoding="utf-8")
        write_report(summary, records, args.resummarise.with_suffix(".md"))
        print(f"Report: {args.resummarise.with_suffix('.md')}")
        return 0

    course = load(ROOT / "content")
    entries = build(course)
    order = passages_in_order(course)
    if args.passages:
        chosen = [course.passages[x] for x in args.passages.split(",")]
    elif args.sample:
        step = max(1, len(order) // args.sample)
        chosen = order[::step][: args.sample]
    else:
        chosen = order

    key_env = os.environ.get("OLLAMA_API_KEY", "")
    client = OllamaClient(args.host, args.model, api_key=key_env, timeout=180)
    judge = OllamaClient(args.judge_host or args.host, args.judge_model, api_key=key_env, timeout=180) if args.judge_model else None
    usage_by_step: dict[str, list[Usage]] = defaultdict(list)
    records = []
    for i, p in enumerate(chosen, 1):
        t = time.monotonic()
        records.append(evaluate_passage(p, course, entries, client, judge, usage_by_step))
        print(f"[{i}/{len(chosen)}] {p.id} {time.monotonic() - t:.0f} s", flush=True)

    summary = summarise(records, usage_by_step, args)
    args.out.mkdir(parents=True, exist_ok=True)
    stem = f"assistant-eval-{args.model.replace(':', '-').replace('/', '-')}-{summary['date']}-{PROMPT_VERSION}"
    (args.out / f"{stem}.json").write_text(json.dumps({"summary": summary, "records": records}, ensure_ascii=False, indent=1),
                                           encoding="utf-8")
    write_report(summary, records, args.out / f"{stem}.md")
    print(json.dumps({k: summary[k] for k in ("punctuation", "major_breaks", "segmentation", "glosses", "grammar", "translation",
                                               "tokens_per_analysis")}, ensure_ascii=False, indent=1))
    print(f"Report: {args.out / (stem + '.md')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
