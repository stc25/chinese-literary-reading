# Assistant evaluation (A4)

2026-11-08. Model `qwen3.5:9b` (local, through Ollama), judge `gemma3:12b`. Each run used the same 15
sampled passages from across the units (`tools/eval_assistant.py --sample 15`). The full reports are
in `reports/`, one Markdown and one JSON file per prompt version.

The method is described in [assistant-plan.md](assistant-plan.md#evaluation). Glosses are scored
**leave-one-out**: the glossary is rebuilt without the passage being tested, so the model has to
gloss the passage's own new words (458 words across the 15 passages).

## Results

| | a3-1 | a4-1 | a4-2 | **a4-3** |
|---|---|---|---|---|
| Change | A3 prompts | gap extension for partly covered words | words step in chunks of 150 characters | "gloss words, not phrases" (1–4 characters) |
| Punctuation F1 | 90% | 89% | 91% | **92%** |
| Clause and sentence ends F1 | not measured | 99% | 98% | **99%** |
| Word-boundary F1 | 61% | 63% | 63% | 62% |
| Glosses: same / close | 31% / 8% | 30% / 6% | 31% / 7% | 32% / 7% |
| Glosses: segmented differently | 53% | 55% | 57% | 58% |
| Glosses: not glossed | 8% | 9% | 6% | **3%** |
| Glosses: judged different | 0% | 0% | 0% | 0% |
| Grammar point chosen (52) | 63% | 62% | 48% | 60% |
| Translation (faithful / minor / wrong) | 2 / 13 / 0 | 4 / 11 / 0 | 5 / 10 / 0 | 7 / 8 / 0 |
| Failed calls (invalid JSON) | | | punctuate 4 | punctuate 2 |
| Tokens per analysis | about 5,500 | about 5,650 | about 6,245 | about 6,490 |

The figures for "segmented differently" and "not glossed" in a3-1 and a4-1 were rescored after that
category was added; nothing else in those runs changed.

**Chosen prompt: `a4-3`.** It is the best or equal best on everything except word boundaries, where
the differences are within noise, and it halves the words left unglossed. It costs about 4% more tokens
than a4-2.

## What the numbers mean

**Punctuation is good.** Clause and sentence ends are almost always right (99%). Most remaining
differences are commas: the model often adds a comma after a topic or a short phrase where the course
text has none, which a reader can ignore. The weakest passages are lists (u01-p01) and long treaty
sentences (u06-p02, u15-p03).

**Glosses are usually right when the units match.** The judge marked no gloss as different, and
about four in five glosses that cover the same word as the course are the same or close. Two caveats
apply:

- *The judge is probably lenient.* It never chose "different" in any run. A hand check of a sample is
  still needed before the pilot.
- *"Segmented differently" mixes two cases.* A sample of 20 of the 265 such glosses in a4-3 shows:
  - about half are harmless: the course glosses a phrase (所定和約, 呈請鑒核施行, 地土久荒) and the
    model glosses the word inside it (定, 鑒核), or the reverse (積氣 for 積);
  - about half are a real fault: the model glosses a whole clause as one item (天空諸曜,
    據稟邵伯湖西岸地土久荒), so the learner gets a paraphrase rather than word glosses.

  The a4-3 instruction did not stop this. 15% of the model's items are still five characters or
  longer. A5 should handle these items in the page rather than in the prompt: show an item longer than
  four characters as a phrase note, not as a word gloss.

**Grammar choices are noisy.** The grammar step's prompt and code were the same in all four runs,
but its score ranged from 48% to 63% on 52 items. A single run cannot measure differences smaller
than about 15 points. The usual errors are:

- confusing the uses of 之 (attributive 之 taken as nominalising 之) and of 也 (topic 也 taken as
  sentence-final 也);
- giving no choice at all for common words (者, 為, 其).

The course grammar links shown beside each form are therefore more reliable than the model's choice.
The page already labels the model's choice as a suggestion.

**Translations are usable but imperfect.** None was judged wrong. Half or more have minor errors.
This matches the plan's intent that the translation step comes last and is labelled as a draft.

## Speed

On the development machine (a Mac with 16 GB of memory, which also had to hold the judge model):

| Step | Seconds per passage (a4-3) |
|---|---|
| Punctuation | about 20 |
| Words (1.8 calls per passage, in chunks of 150 characters) | about 98 |
| Grammar | about 89 |
| Translation | about 20 |

A full analysis of one passage took about four minutes. Without the judge it would be faster, but
still minutes, not seconds. This rules out running the local model for learners on a server without a
GPU. The choices are a cloud model or a server with a suitable GPU (see the budget below).

## Tokens and budget

A full analysis (punctuation, words, grammar, translation) of a course passage of about 200 characters
uses about **6,500 tokens**: about 3,200 prompt and 3,300 output. About two thirds of this goes on the
words and grammar steps, where `qwen3.5` writes long JSON. The names step and a few follow-up questions bring
this to about **8,000 tokens**.

Estimated use for the pilot:

| Assumption | Tokens a year |
|---|---|
| 20 learners, 3 analyses a week each, 30 teaching weeks (1,800 analyses) | about 15 million |
| Upper bound set by the limits: 150 calls an hour at about 1,350 tokens a call | at most about 200,000 an hour |

Whether 15 million tokens a year fits within £60 depends on the Ollama plan, which is still to be
checked (see the open points in the plan). If the plan cannot cover this:

- the hourly limit (`ASSISTANT_HOURLY_LIMIT`) and the daily limit per user (`ASSISTANT_DAILY_LIMIT`)
  can be lowered;
- the grammar step, the most expensive and least reliable step, could be left to the course's grammar
  links alone.

## Cloud models

**Not yet compared.** The comparison needs the Ollama API key. When it is available, run:

```
OLLAMA_HOST=https://ollama.com OLLAMA_API_KEY=… python3 tools/eval_assistant.py --sample 15 \
    --model <cloud model> --judge-model gemma3:12b --out reports
```

Run this for two or three Chinese-capable models, then add a column for each to the results table.
The judge stays local, so the judging is the same for every model. Choose the cloud model on gloss
quality ("same" plus "close"), translation, and tokens per analysis.

## Still to do before the pilot

- Compare the cloud models (needs the key).
- Hand-check a sample of 30 glosses and 5 translations against the judge's verdicts.
- Show items longer than four characters as phrase notes (A5).
- Check the Ollama plan against the token estimate above.
