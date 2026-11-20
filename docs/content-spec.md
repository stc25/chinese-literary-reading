# Content Format Specification

Draft v0.1 · 2026-11-06

All course content is written as Markdown files that follow this spec. The rules are
strict so that (a) a validation script can check every file, and (b) the Django app
can render the files without anyone converting them. Files must still read well
in any Markdown viewer, for reviewers who never see the app.

General rules:

- UTF-8, Unicode NFC, LF line endings.
- Each file starts with YAML frontmatter between `---` lines.
- Section headings (`## …`) must use the exact names given below, in the given order.
  Unknown `##` sections are errors. Optional sections may be left out.
- English prose uses British spelling.
- Reviewer comments go in HTML comments: `<!-- REVIEW(initials): … -->`. The app
  never shows them, and the validator lists them.

---

## 1. Folder layout

```
content/
  course.md                      # course overview and unit order
  units/
    u01-<slug>/
      unit.md                    # unit introduction
      u01-p01-<slug>.md          # reading passage (includes its exercises)
      u01-p02-<slug>.md
  grammar/
    <grammar-id>.md              # one grammar or style point per file
  toolkit/
    t01-<slug>.md                # reference page, outside the graded path
    data/
      <name>.csv                 # data tables used by toolkit pages and app tools
  glossary.md                    # GENERATED from passage glosses, do not edit
  assistant/                     # reading-assistant unit (to be specified later)
```

### IDs

- Lowercase ASCII, digits and hyphens only.
- Unit: `u01`, `u02`, … Passage: `u01-p01`, `u01-p02`, …
- Grammar point: a descriptive slug, e.g. `zhi-attributive`, `zhi-nominaliser`, `ye-final`.
- Toolkit page: `t01`, `t02`, …
- Each file states its `id` in the frontmatter, and the filename must begin with that id.
  IDs never change once assigned, even if a unit is renamed or moved; only `order` changes.

---

## 2. Controlled values

| Field | Allowed values |
|---|---|
| `level` | `beginner`, `intermediate` |
| `status` | `planned`, `draft`, `reviewed`, `expert-reviewed`, `needs-revision` |
| `genre` | `official`, `newspaper`, `essay`, `letter`, `scholarly`, `legal`, `diplomatic`, `literary`, `textbook`, `diary`, `other` |
| `rights` | `public-domain`, `fair-dealing` |
| `default_view` | `modern`, `unpunctuated`, `vertical`, `vertical-unpunctuated` |
| `punctuation` | `original`, `edition`, `course` |
| `gloss_label` | `n.`, `v.`, `adj.`, `adv.`, `pron.`, `part.`, `prep.`, `conj.`, `interj.`, `num.`, `mw.` |
| `neutral_tone` | `de`, `le`, `zhe`, `guo`, `ma`, `ne`, `ba`, `a`, `ya`, `me`, `men`, `zi`, `tou` |

New values may be added to this table. The validator reads its lists from here.

**`planned`** marks a placeholder created from the curriculum outline. In a planned
file the validator checks the frontmatter and the section names, but required
sections may be missing or empty. The one exception: planned grammar and toolkit
files must still have a `## Summary`, because the app shows it whenever another page links to them.
The app lists planned units and pages as "in preparation".

**Review tracking.** Every file except `course.md` may have two optional frontmatter fields,
`reviewed_by` and `expert_reviewed_by`, holding the reviewers' initials (e.g. `reviewed_by: AB`).
A file with status `reviewed` or `expert-reviewed` must not contain any
`<!-- REVIEW … -->` comments: resolve or remove them before changing the status.

---

## 3. Course file — `content/course.md`

```yaml
---
title: Reading Modern Literary Chinese
version: 0.1
---
```

Sections:

| Section | Required | Content |
|---|---|---|
| `## Introduction` | yes | What the course is for, who it is for |
| `## How to use this course` | yes | Recommended path; skipping units |
| `## Units` | yes | `### Beginner` and `### Intermediate` subheadings, each an ordered list of links to `unit.md` files. This list defines the recommended order |
| `## Toolkit` | yes | A bullet list of links to the toolkit pages |

---

## 4. Unit file — `content/units/uNN-<slug>/unit.md`

```yaml
---
id: u01
title: Nouns, verbs and the sentence
level: beginner
prerequisites: []          # advisory only — learners may skip
grammar: [ye-final, zhi-possessive]   # grammar points introduced in this unit
genres: [essay]
status: draft
---
```

Sections:

| Section | Required | Content |
|---|---|---|
| `## Introduction` | yes | A short orientation |
| `## Objectives` | yes | A bullet list: "By the end of this unit you will be able to…" |
| `## Passages` | yes | An ordered list of links to the unit's passage files. This list defines their order. An item **without** a link is a planned passage not yet written, e.g. `2. 申報 news item on a fire (planned)` |
| `## Grammar` | yes | A bullet list of links to the grammar files introduced in this unit |

---

## 5. Passage file — `content/units/uNN-<slug>/uNN-pNN-<slug>.md`

### Frontmatter

```yaml
---
id: u01-p01
title: The "old empire"             # English title
title_zh: 少年中國說（節選）          # Chinese title of the passage or excerpt
unit: u01
level: beginner
genre: essay
author: Liang Qichao 梁啟超 (1873–1929)   # or "anonymous" / "unknown"
date: "1900"                        # year or range as a string, e.g. "1898–1899"
source:
  work: 少年中國說
  edition: 飲冰室合集                  # edition the text was taken from
  location: opening sentence        # page, juan, section, etc.
  punctuation: edition              # optional: who punctuated ## Text (see 5.1)
rights: public-domain
rights_note: Author died 1929.
grammar: [zhi-nominaliser, ye-topic]   # grammar points this passage practises
default_view: modern
status: draft
---
```

### Sections

| Section | Required | Content |
|---|---|---|
| `## Introduction` | no | Context for the reader: who wrote it, when, why |
| `## Text` | yes | The canonical text (see 5.1) |
| `## Original text` | no | The text exactly as in the source, when its own punctuation or layout matters (see 5.2) |
| `## Glosses` | yes | The gloss table (see 5.3) |
| `## Translation` | yes | An idiomatic English translation, **one paragraph per Text paragraph** |
| `## Literal translation` | no | A word-by-word rendering, mainly for beginner units; same paragraph rule |
| `## Notes` | no | Free Markdown: grammar, style, historical context. Link to grammar files with ordinary relative links |
| `## Exercises` | no | See section 8 |

### 5.1 Text

- Traditional characters, horizontal, modern full-width punctuation:
  `，。、；：？！「」『』《》〈〉（）——……`
  - 《》 for book titles, 〈〉 for article or chapter titles; 「」 for quotations, 『』 nested.
- Keep the character forms of the source edition (e.g. 爲, 眞, 衞), and do not normalise them to 為, 真, 衛.
  Note the common equivalent in the gloss where it would help.
- Apart from punctuation, reproduce the source edition **exactly**. Mark any omission
  inside the passage with …… and mention it in the Introduction or Notes.
- `source.punctuation` records who punctuated the text: `original` (the source's own
  punctuation, modernised), `edition` (punctuation added by the modern edition or
  transcription used), or `course` (added by us). Researchers need to know whether a
  sentence division is the author's or an editor's.
- When a unit uses several excerpts from one work, number them in `title_zh`:
  少年中國說（節選一）, 少年中國說（節選二）. A single excerpt is （節選）.
- Paragraphs are separated by a blank line. Line breaks inside a paragraph are ignored.
- No Markdown formatting inside the text (no bold, links or notes).
- The app produces the **unpunctuated** view by removing punctuation and the
  **vertical** view with CSS. Neither is written by hand.

### 5.2 Original text (optional)

Use this when the source's own punctuation (e.g. 句讀 marks 、。◎, or none at all) is
itself the teaching point. Write it exactly as in the source. If it is present, the app
uses it for the unpunctuated and vertical views instead of deriving them.
With punctuation removed, it must contain the same characters as `## Text`, and
the validator checks this.

### 5.3 Glosses

The glosses are a single Markdown table with these four columns, in this order:

```markdown
| Term | Pinyin | Gloss | Grammar |
|---|---|---|---|
| 學者 | xuézhě | scholar; one who studies | |
| 之 #2 | zhī | possessive marker: 's, of | zhi-possessive |
| 所以 | suǒyǐ | that by which; the means of | suoyi |
| 非 … 不 | fēi … bù | not … unless; only if | fei-bu |
```

**Term**

- An exact string from `## Text`.
- On its own, the gloss applies to **every** occurrence.
- `#n` (e.g. `之 #2`) limits it to the nth occurrence, counting from 1 through the whole
  text. Several occurrences can be listed: `之 #1 #3`. Use this when one character
  has different functions in the same passage. Each occurrence then has its own row.
- **Counting includes occurrences inside longer words.** If 老年人 appears nine times
  and 老年 once more on its own, the lone 老年 is `老年 #10`, not `老年 #1`. To list the
  numbered occurrences of a term, run `python3 tools/occurrences.py FILE TERM`.
- `A … B` glosses a split construction (e.g. 非…不, 既…又). The app highlights both
  parts. B is matched to the nearest occurrence after A.
- Terms may overlap (e.g. `帝國` and `老大帝國`). When a character is tapped, the app
  shows every gloss that covers it, longest first.

**Pinyin**

- Hanyu Pinyin with tone marks and ü, written as words (`xuézhě`, not `xué zhě`); use an apostrophe where a syllable boundary would be ambiguous (`Xi'an`).
- Give the reading **in context**, including classical readings: 說 shuì "to persuade",
  見 xiàn "to appear", 惡 wù "to hate".
- Separate the parts of split constructions with ` … `.
- Write neutral-tone syllables without a tone mark (的 de, 了 le, 們 men). A pinyin entry with no tone marks
  at all is accepted only if every word in it is in the `neutral_tone` list (section 2); otherwise the validator
  warns.
- The app hides pinyin by default.

**Gloss**

- A short English meaning *in this context*. Separate alternatives with `;`.
- It may start with one grammatical label in italics, taken from the `gloss_label` list
  in section 2: `*part.* final particle`, `*pron.* it, this`. Labels are defined in toolkit page T7.

**Grammar**

- Optional. The `id` of a grammar file, or of a toolkit page (e.g. `t02` for a
  reign title). The app turns it into a link.

**What to gloss**

- Gloss words that are new to the course or used here in a new sense.
- The app falls back to the course glossary for words glossed earlier, so
  intermediate passages need fewer glosses.

---

## 6. Grammar file — `content/grammar/<grammar-id>.md`

Grammar files also cover **style and genre points** (e.g. `parallelism`,
`memorial-formulas`) taught in the intermediate units.

```yaml
---
id: zhi-nominaliser
title: 之 between subject and verb
forms: [之]                 # characters or patterns covered; may be [] for e.g. topic-comment
level: beginner
status: draft
---
```

Sections:

| Section | Required | Content |
|---|---|---|
| `## Summary` | yes | One or two sentences. The app shows this in tooltips |
| `## Explanation` | yes | Free Markdown. Define technical terms on first use |
| `## Examples` | yes | A table: `\| Chinese \| Pinyin \| Translation \| Source \|`. Source is a passage id (e.g. `u01-p01`) or a short citation |
| `## See also` | no | A bullet list of links to related grammar files |

---

## 7. Toolkit page — `content/toolkit/tNN-<slug>.md`

Reference pages (dates, offices, romanisation, …), not graded and with no passages.

```yaml
---
id: t02
title: Dates and calendars
data: [qing-reign-periods.csv]   # files in content/toolkit/data/ used by this page; may be []
status: draft
---
```

Sections:

| Section | Required | Content |
|---|---|---|
| `## Summary` | yes, first | One or two sentences, shown in the course map and in tooltips |
| *any* `## …` | — | Free Markdown sections, chosen to suit the topic |
| `## Practice` | no, last | Optional practice items, written in the exercise format (section 8) |

### Data files — `content/toolkit/data/<name>.csv`

- UTF-8 CSV with a header row; lowercase `snake_case` column names; every row has
  as many cells as the header.
- File names are lowercase with hyphens, e.g. `qing-reign-periods.csv`.
- Each data file must be listed in the `data` field of at least one toolkit page.
- The app can use these tables for small tools (e.g. converting a reign year to a Western year).
  Toolkit pages show them as tables or quote from them.

---

## 8. Exercises

Exercises sit in a passage file under `## Exercises`, or in a toolkit page under `## Practice`. Each exercise is a `###` heading
of the form `### <number>. <type>`, followed by these parts:

1. **Prompt**: the paragraph(s) up to the first labelled part. Highlight the target
   word in a Chinese quotation with bold: `日本人**之**稱我中國也`.
2. Fields that depend on the type (below).
3. `**Answer:**` (required), then `**Explanation:**` (optional), each beginning a paragraph.

| Type | Additional parts | App behaviour |
|---|---|---|
| `choice` | A task list. `- [x]` marks correct options, `- [ ]` wrong ones. One `[x]` = single choice, more than one = multi-select. `**Answer:**` may be left out for this type | Checked automatically |
| `short-answer` | — | Learner types an answer, then compares it with the model answer |
| `translate` | — | Learner translates, then compares it with the model translation |
| `punctuate` | `**Text:**` followed by an unpunctuated passage | Learner inserts punctuation. With punctuation removed, `**Answer:**` must match `**Text:**` exactly, and the validator checks this |

Example:

```markdown
### 1. choice

In 日本人**之**稱我中國也, what does 之 do?

- [ ] It marks possession: "the Japanese people's China"
- [x] It makes 日本人稱我中國 into a noun phrase: "the Japanese calling our China"
- [ ] It is an object pronoun: "it"

**Explanation:** Placed between a subject and its verb, 之 turns the clause into a noun phrase, which here becomes the topic of the sentence.

### 2. punctuate

Punctuate the sentence.

**Text:** 日本人之稱我中國也一則曰老大帝國再則曰老大帝國

**Answer:** 日本人之稱我中國也，一則曰老大帝國，再則曰老大帝國。
```

---

## 9. Glossary — `content/glossary.md`

This file is **generated** by a script from all passage gloss tables. Do not edit it
by hand. Columns: `| Term | Pinyin | Gloss | First seen | Grammar |`. A term with several
meanings gets one row per distinct gloss.

---

## 10. Style conventions

- **Names**: pinyin followed by characters at first mention in each file, e.g. Liang Qichao 梁啟超. If a period
  romanisation is well known, add it in brackets at first mention: Sun Yat-sen (Sun Zhongshan 孫中山).
- **Dates**: reign or Republican year first, Western year in brackets: 光緒二十六年 (1900), 民國八年 (1919).
  Early dates use BCE/CE and "c." for traditional or approximate dates: Shang (c. 1600–1046 BCE).
- **Pinyin of proper names** is capitalised: Rèngōng, Xībólìyà.
- **Cross-references**: refer to other material with a link to the grammar file or
  unit, not by number ("see [也 after a topic](…)", not "see unit 5"), because unit order may change.
- **Chinese in English prose**: characters, with pinyin in italics where helpful: 之 *zhī*.
- **Terminology**: use a small, consistent set of grammatical terms. Every term is
  defined in toolkit page T7 (Grammatical terms).

---

## 11. Not yet specified

- The reading-assistant unit (`content/assistant/`)
- Unit-level review exercises that span several passages
- Proper-name and place-name underlining (專名號 / 書名號 as wavy lines) in the original text
- Audio
