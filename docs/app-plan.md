# Web app — plan

> Historical plan: the backend is now Django, not Flask (see `docs/superpowers/` for the Django port plan). The decisions about content, links and pages below still hold.

Draft v0.1 · 2026-11-07

This plan covers Phase 4 of [PLAN.md](../PLAN.md): the Flask app that renders the course. The
Markdown in `content/` stays the single source of truth; the app only reads it.

## Decisions

| Area | Decision |
|---|---|
| Access | Cambridge sign-in (University SSO, Microsoft Entra ID via OpenID Connect). No personal data stored on the server beyond the session cookie. A development setting bypasses sign-in locally |
| Progress | Kept in the learner's own browser (`localStorage`): display preferences, completed exercises, last passage read. Nothing on the server |
| Server | Not yet known. Build a standard deployment (Gunicorn behind nginx or Apache, Python 3.11+), with an optional Dockerfile, and document it |
| Scope of v1 | The course reader. The AI reading assistant comes in a second stage, once it has been specified |
| Unreviewed content | Shown, with a visible "draft, not yet reviewed" label. A release setting can hide anything below `reviewed` |
| Reviewer mode | REVIEW comments shown inline to reviewers only (a list of CRSids in the configuration). Learners never see them |
| Front end | Server-rendered Flask/Jinja pages that work without JavaScript, with small vanilla JavaScript for glosses, toggles and exercises. No build step |
| Design | Clean, neutral academic design, easy to restyle later; careful Chinese typography |
| Accessibility | WCAG 2.2 AA; keyboard use throughout; `lang="zh-Hant"` on Chinese text |
| Devices | Desktop, tablet, phone; responsive layout |

## Architecture

```
app/
  __init__.py            # create_app(); configuration
  content/               # loading and indexing the Markdown
    loader.py            # validator's parsed files → Python objects
    model.py             # Course, Unit, Passage, Grammar, Toolkit, Gloss, Exercise …
    render.py            # Markdown → HTML for prose sections; links rewritten to app URLs
  views.py               # page routes: course, units, passages, grammar, toolkit (glossary in M3)
  auth.py                # SSO (OIDC), reviewer list, development bypass
  templates/             # Jinja templates
  static/
    css/  js/  fonts/
tests/test_app.py        # unittest + Flask test client
```

**Content loading.** At start-up the app parses all of `content/` into an in-memory index (about 150
files; about 0.2 seconds). It does this by calling the validator itself (`tools/validate.py`,
`build()`), which returns the parsed files as well as the report, so the validator and the app read the
files in exactly the same way. In development the index reloads when a file changes; if an edit
introduces validation errors, the app keeps serving the last valid version and shows the errors. The
app refuses to start if the validator reports errors.

**Links.** Links between Markdown files (`../../grammar/suo.md`) are rewritten to app URLs
(`/grammar/suo`). Grammar and toolkit links get a tooltip with the target's `## Summary`.

**Libraries.** Flask, PyYAML, `markdown-it-py` (CommonMark with tables), Authlib (OIDC). Fonts are
served from the app (no third-party font or script requests).

## Pages

| Page | URL | Contents |
|---|---|---|
| Course map | `/` | Introduction, beginner and intermediate units, toolkit; progress ticks from the browser |
| Unit | `/units/u05` | Introduction, objectives, passages, grammar |
| Passage | `/units/u05/p01` | The reader (below) |
| Grammar | `/grammar/zhi-object` | Explanation, examples (each linked to its passage), passages that use it |
| Toolkit | `/toolkit/t02` | The page; practice items; small tools built from the CSV data (v1: reign-year converter) |
| Glossary | `/glossary` | Generated from all glosses: term, pinyin, gloss, first passage; searchable |
| About | `/about` | Sources, rights, review status, credits |

## The passage reader

- **Text** in a large serif traditional-character font. Each glossed term is a focusable element;
  tapping, clicking or pressing Enter shows its gloss (term, pinyin, gloss, grammar link) in a popover
  on desktop and a bottom sheet on phones. Overlapping glosses are shown longest first; split terms
  (`A … B`) highlight both parts.
- **Pinyin** hidden by default; a toggle shows it in glosses (not above the text).
- **Views**: modern (punctuated, horizontal), unpunctuated, vertical, vertical unpunctuated, using
  `## Original text` when the passage has one. Vertical text uses CSS `writing-mode: vertical-rl`.
  The passage's `default_view` is the starting view.
- **Translation** hidden by default, revealed per paragraph or all at once; literal translation if present.
- **Notes**, introduction and source details (edition, location, punctuation, rights).
- **Exercises**:
  - `choice`: checked in the browser;
  - `short-answer` and `translate`: the learner writes, then reveals the model answer;
  - `punctuate`: the learner types punctuation into the text; the app compares it with the answer and
    marks matches and differences.
- **Status**: draft label; in reviewer mode, REVIEW notes appear in a marked box where they occur.

## Milestones

| | Milestone | Result to review |
|---|---|---|
| M1 ✓ | Skeleton and content index | `flask run` shows the course map, units and plain passage pages; the shared parser; tests |
| M2 ✓ | Passage reader | glosses, pinyin toggle, view toggles, translation reveal, notes; works on phone |
| M3 ✓ | Grammar, toolkit, glossary | all pages linked, tooltips, glossary search, reign-year converter |
| M4 ✓ | Exercises and progress | interactive exercises; progress and preferences in `localStorage` |
| M5 ✓ | Sign-in and reviewer mode | OIDC sign-in, development bypass, reviewer view of REVIEW notes, draft labels and release setting |
| M6 ✓ | Accessibility and deployment | WCAG 2.2 AA check, device testing, Gunicorn/nginx and Docker setup, deployment guide |
| — | Reading assistant (second stage) | planned in [assistant-plan.md](assistant-plan.md), milestones A1–A5 |

## Open points

- **SSO registration**: the app must be registered with University Information Services (Entra ID
  application) by someone with authority in the Language Centre. Until then, sign-in is bypassed
  locally.
- **Server details**: OS, web server, Python version and who maintains it.
- **Reading assistant**: planned in [assistant-plan.md](assistant-plan.md); Ollama cloud account, terms and budget still open.
