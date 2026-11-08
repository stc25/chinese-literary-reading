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
than a4-2. The prompts in use are `a4-4`: a4-3 plus a line stating the JSON form, added for the
cloud models (see below).

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

The Language Centre's key is on Ollama's **free plan**. Of the 26 cloud models listed on
2026-11-08, the free plan covers only `gemma4:31b`, `gpt-oss:20b`, `gpt-oss:120b`, `beam` and the
`nemotron-3` models. The Chinese-specialist models (DeepSeek, GLM, Kimi, MiniMax, MiMo) all need paid
credits, so they were not tested.

Three free models were compared on the same 15 passages, with the same local judge:

```
OLLAMA_API_KEY=… python3 tools/eval_assistant.py --sample 15 --model gemma4:31b \
    --host https://ollama.com --judge-host http://localhost:11434 --out reports
```

Two fixes were needed first, because the cloud service ignores the requested JSON form for some
models:

- the client accepts JSON wrapped in a Markdown code fence;
- every request states the expected JSON form in the message (prompt version `a4-4`, about 50 more
  tokens a call).

`qwen3.5:9b` was measured with `a4-3`, which differs only in that line.

| | qwen3.5:9b (local, a4-3) | **gemma4:31b** | nemotron-3-ultra | gpt-oss:120b |
|---|---|---|---|---|
| Punctuation F1 | 92% | 91% | **94%** | 81% |
| Clause and sentence ends F1 | 99% | 99% | 99% | 89% |
| Word-boundary F1 | 62% | **66%** | 60% | 64% |
| Glosses: same / close | 32% / 7% | **45% / 9%** | 26% / 3% | 32% / 14% |
| Glosses: segmented differently | 58% | **44%** | 69% | 52% |
| Glosses: not glossed | 3% | 2% | 2% | 1% |
| Items longer than four characters | 42 of 268 | **0 of 201** | 85 of 326 | 1 of 239 |
| Grammar point chosen (52) | 60% | 75% | 83% | **85%** |
| Translation (faithful / minor) | 7 / 8 | 2 / 13 | 0 / 15 | 1 / 14 |
| Tokens per analysis | about 6,490 | about 6,830 | about 6,740 | about 17,050 |
| Seconds per analysis | about 230 | **about 15** | about 60 | about 31 |

**Chosen: `gemma4:31b` on the free plan.**

- It gives the best glosses by a clear margin: 54% same or close, against 39% for the local model.
- It glosses words, never whole clauses, so the phrase-note fix planned for A5 matters much less.
- Its grammar choices are better than the local model's.
- A full analysis takes about 15 seconds, and it uses about as many tokens as the local model.

`gpt-oss:120b` chooses grammar points best, but it punctuates poorly and uses two and a half times as
many tokens, most of them on hidden reasoning. `nemotron-3-ultra` punctuates best, but it glosses whole
clauses even more often than the local model.

**Translations: the judge cannot be trusted.** The translation verdicts disagree with the other
measures. Reading the judge's notes shows why: for u01-p01 it faulted the correct 填星 as wrong and
proposed a reading that does not exist. The translation figures here are not a basis for choosing a
model. The hand check below is needed.

**The free plan's limits.** Ollama does not publish its free-plan limits as a token count. The three
evaluation runs (about 300 calls) never hit them. Whether they cover 20 learners has to be seen in the
pilot. If they do not:

- lower `ASSISTANT_HOURLY_LIMIT` and `ASSISTANT_DAILY_LIMIT`; the page already says when a limit is
  reached;
- or buy pay-as-you-go credits within the £60 budget, which would also open the Chinese-specialist
  models for a second comparison.

## Still to do before the pilot

- Run the pilot on the free plan and watch for usage-limit messages.
- Hand-check a sample of 30 glosses and 5 translations against the judge's verdicts.
- Show items longer than four characters as phrase notes (A5); needed only if the local model is used.
