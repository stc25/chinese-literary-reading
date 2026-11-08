# Reading assistant — plan

Draft v0.1 · 2026-11-08

The second stage of the web app (see [app-plan.md](app-plan.md)): an assistant that helps
intermediate learners read a text of their own choosing, using the same method as the course.

## Decisions

| Area | Decision |
|---|---|
| Role | **Guided analysis** in steps that follow the course method (text and punctuation → words → grammar → names, dates and allusions → translation), then **follow-up questions** about the same text |
| Reliability | Reviewed course material first, the model second. Every item is labelled with its source: *Course glossary*, *Course grammar*, *Date converter* (all checked) or *AI suggestion* (unchecked) |
| Translation | Last, and only on request; the learner is invited to write their own first |
| Storage | **Nothing is stored**: no texts, questions or answers on the server, and none in the logs. Only a per-user request count, in memory, for usage limits. The Language Centre reports that the Ollama cloud service does not retain requests, inputs or outputs |
| Model | Local Ollama model in development: `qwen3.5:9b`. A large Chinese-capable Ollama cloud model for testing and release, chosen by the evaluation below. The browser never talks to the model: Flask calls it server-side. The API key will be supplied by the Language Centre |
| Scale and budget | At most about 20 users at a time; a budget of **£60 a year** for the model service |
| Simplified input | Converted to traditional characters (OpenCC) before analysis; the learner is told, and sees the converted text |
| Evaluation | Automatic tests against the course's own reviewed passages: punctuation, segmentation and glosses scored against our answers, comparing models and prompts |
| Teaching material | No guided walkthroughs. A help page, *Using the assistant critically*, explains the method, what the AI is good at, how it fails and how to check it |
| Access | Signed-in users only (as the rest of the site); can be switched off with a setting |

## The learner's view

One page, `/assistant`, in five steps. Each step is a separate request, so the first results appear
quickly and the learner decides how far to go.

1. **Text.** Paste up to 600 characters of literary Chinese. The app removes spaces and line breaks
   and shows the text in the course reader's style. Simplified characters are accepted, with a note
   that the course uses traditional ones. If the text has no punctuation, the learner can ask for
   *suggested punctuation*: it is shown as a proposal, with the breaks marked, which the learner can
   accept or ignore.
2. **Words.** The text is cut into words. Each word that is in the **course glossary** (about 3,000
   reviewed entries) is glossed from it, longest match first, with a link to the passage where it is
   taught. The remaining words get **AI glosses**, marked as such. A course term may have a different
   sense here, so where the model's reading of the context differs from the glossary, both are shown.
   The words use the same tap-to-gloss interface as the passages.
3. **Grammar.** Function words are found by the app from the `forms` lists of the grammar files
   (之, 者, 所, 以, 於, 而, 則 …) and linked to their grammar pages. The model adds a one-line note on
   what each does in *this* sentence (marked as AI).
4. **Names, dates and allusions.** The model flags personal and place names, official titles, dates
   and likely allusions. Reign and cyclical dates are converted by the course's **date converter**,
   not by the model. Allusions are always marked "check this", with a pointer to the reference works
   in the toolkit (T1, T6).
5. **Translation.** A box for the learner's own translation, then the model's translation (and a
   literal version on request), marked as AI.

Below the steps, the learner can **ask questions** about the text ("Why is 之 used here?", "What is
the subject of the second sentence?"). The model answers in English, about this text only, and in the
course's terms. A conversation is limited to about ten questions.

The page states plainly, before the first step: the text is sent to an external AI service; do not
paste personal or confidential material; AI suggestions can be wrong and must be checked.

Without JavaScript, a single form submits the text and returns steps 1–4 as one page (no questions).

## Architecture

```
app/assistant/
  __init__.py      # blueprint /assistant; enabled by ASSISTANT_ENABLED
  client.py        # Ollama client: /api/chat with JSON-schema structured output, timeouts, retries
  lookup.py        # deterministic layer: glossary longest-match, grammar forms, date detection
  steps.py         # one function per step: build prompt, call model, validate the JSON, merge with lookup
  prompts.py       # system prompts and JSON schemas, versioned
  limits.py        # per-user request counts in memory
app/templates/assistant.html, assistant_help.html
app/static/js/assistant.js
tools/eval_assistant.py   # evaluation harness (below)
```

- **Deterministic layer first.** Glossary matching, grammar-form detection and date conversion run in
  Python, need no model and are covered by tests. The model fills gaps and explains.
- **Structured output.** Every model call asks for JSON matching a schema (Ollama's `format`
  parameter). Replies that fail validation are retried once, then reported as "no AI suggestion".
- **Safety.** The pasted text is placed in the prompt as quoted data, and the system prompt tells the
  model to ignore instructions inside it. Model output is shown as text, never as HTML.
- **Limits.** For example 30 analyses and 100 questions per user per day, and a global cap per hour,
  all configurable. Counts are kept in each server process's memory, so with several workers the
  limits are approximate; nothing is written to disk.
- **Timeouts.** 60 seconds per model call, shown to the learner as a clear message, not an error page.
  Gunicorn's timeout is raised to 90 seconds for the assistant.

**Settings** (environment variables `MLC_…`): `ASSISTANT_ENABLED`, `OLLAMA_HOST`
(e.g. `http://localhost:11434` or the cloud endpoint), `OLLAMA_API_KEY` (cloud only, server-side),
`ASSISTANT_MODEL`, `ASSISTANT_MAX_CHARS`, and the limits.

## Evaluation

`tools/eval_assistant.py` runs the assistant on the course passages, whose answers are reviewed, and
writes a report comparing models and prompt versions.

| What | How it is scored |
|---|---|
| Suggested punctuation | The passage's `## Text` with punctuation removed is the input; breaks are scored against the original (precision, recall, F1), with the same gap-by-gap comparison as the punctuation exercises |
| Segmentation | Word boundaries compared with the boundaries of the passage's glossed terms |
| Glosses | **Leave-one-out**: the glossary is rebuilt *without* the passage being tested, so the model has to gloss the passage's own new words. Each AI gloss is compared with the course gloss: automatically where they share key English words, otherwise by a second model acting as judge, with a sample checked by hand |
| Function words | Recall of the grammar forms glossed in the passage |
| Translation | Judge model rates the AI translation against the course translation (faithful / minor errors / wrong), with a sample checked by hand |
| Speed and failures | Time per step; invalid JSON; timeouts |

The report shows the scores per model and prompt version, and the worst cases. The worst cases also
supply the examples for the help page.

## Milestones

| | Milestone | Result to review |
|---|---|---|
| A1 ✓ | Deterministic layer | glossary lookup, grammar forms and date detection on any pasted text, with tests; a page that shows them without any model |
| A2 ✓ | Model steps | Ollama client, prompts and schemas for punctuation, words, grammar notes, names and translation; works with the local model |
| A3 | Assistant page | the five steps, source labels, follow-up questions, limits, notices; help page; accessibility tests |
| A4 | Evaluation | harness and report; local model compared with two or three cloud models; choice of model and prompt |
| A5 | Hardening | timeouts, error messages, limits under load, deployment settings and documentation |

## Budget

£60 a year is about £5 a month. Reports of Ollama's cloud plans in 2026 disagree, but none puts a
paid plan within that budget: Pro is reported at about $20 a month (or $200 a year), with a small free
allowance below it. The plan therefore assumes the **free allowance, or a usage-based allowance of
about £5 a month**, and keeps model use low:

- the deterministic layer (course glossary, grammar forms, date converter) does as much as possible,
  so the model only glosses the words the course does not cover;
- each step is requested separately, so steps the learner does not open cost nothing;
- per-user and global limits are set from the allowance once it is known, and the page says when the
  limit is reached and that the course glossary and grammar steps still work;
- the evaluation (A4) records tokens per step, so the cost per analysis can be estimated.

If the allowance proves too small, the alternative is to run the local model (`qwen3.5:9b`) on the
Language Centre server: no usage cost, but slower answers and a server with enough memory (about 8 GB
free) is needed.

## Open points

- **Ollama plan.** Check the current plans on ollama.com/pricing against the £60 budget before the
  pilot. The Language Centre holds the account and API key.
- **Data protection.** The service is reported not to retain requests; record this, with the date and
  source, in case a data protection assessment asks for it.
- **Cloud model.** Chosen in A4 from the Chinese-capable models Ollama offers at the time (for example
  the Qwen, DeepSeek or Kimi families), weighing quality against cost.
