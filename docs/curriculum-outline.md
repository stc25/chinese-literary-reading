# Curriculum Outline

Draft v0.1 · 2026-11-07 · for discussion

This document plans the course. Once agreed, it becomes `content/course.md`, one
`unit.md` per unit, and a stub file per grammar point, all following
[content-spec.md](content-spec.md).

---

## 1. Design principles

1. **Grammar first, then genre.** The beginner units build up the core grammar of
   literary Chinese, one cluster of function words at a time. The intermediate
   units are organised by **genre**, because what researchers need to read differs by genre: memorials,
   treaties, newspapers, philosophy, scholarship, letters.
2. **Real period texts from the start.** Even the shortest beginner passages are
   from 19th–20th century sources, chosen or excerpted for their grammar. No
   made-up sentences, and no reliance on pre-Qin texts except where a period writer quotes them.
3. **No modern Chinese assumed.** Explanations never say "unlike modern Chinese…".
   Vernacular elements are treated in the final unit as part of the period's own language.
4. **Three kinds of difficulty are increased separately**: passage length, glossing density, and
   layout (modern → unpunctuated → vertical original).
5. **Toolkit alongside the path.** Practical reference topics (dates,
   offices, dictionaries) sit outside the graded path, so learners can consult them at any point.

---

## 2. How difficulty is graded

| Stage | Units | Passage length | Default view | Glossing | Literal translation |
|---|---|---|---|---|---|
| Beginner A | U01–U04 | 30–100 characters | modern | almost every word | yes |
| Beginner B | U05–U10 | 100–250 | modern | new words and senses | hard sentences only |
| Intermediate A | U11–U15 | 200–500 | unpunctuated or vertical for some passages | new and specialised terms | no |
| Intermediate B | U16–U20 | 400–800 | original layout where relevant | sparse (course glossary covers the rest) | no |

Each unit has **3 passages**, plus their exercises. The modern view is available
everywhere as a toggle, and learners can switch on the unpunctuated and vertical views
from U01, but the teaching on those views starts in U11.

---

## 3. Beginner units

Grammar ids in `code` become files in `content/grammar/`.

### U01 Words and sentences
- **Skills**: characters as words; word class depends on position; topic and comment;
  nominal sentences ending in 也.
- **Grammar**: `word-classes`, `topic-comment`, `ye-final`
- **Genres**: textbook, other
- **Sources**: 澄衷蒙學堂字課圖說 (1901), compiled by 劉樹屏 (1857–1917): character
  definitions and the guide to word classes. *(Replaced the 1904 國文教科書, which
  is not available as a text and has an open rights question.)*

### U02 Naming and defining
- **Skills**: A 者 B 也 definitions; 謂之, 曰 "is called"; 爲 "is, serves as"; 非 "is not".
- **Grammar**: `zhe-ye-definition`, `weizhi`, `yue-naming`, `wei-copula`, `fei-negation`
- **Genres**: textbook, essay
- **Sources**: 澄衷蒙學堂字課圖說 (1901), definition entries; 梁啟超〈新民說〉(1902),
  section 3. *(Replaced 新爾雅 (1903), which is not available as a text.)*

### U03 Verbs, objects and negation
- **Skills**: verb–object order; 不, 未, 無, 勿/毋; existence with 有/無.
- **Grammar**: `bu-negation`, `wei-not-yet`, `you-wu`, `prohibitives`
- **Genres**: legal, letter
- **Sources**: 中華民國臨時約法 (1912), articles 5–7, 12–14, 51, 54; 曾國藩家書, two
  letters for 勿/毋 *(no regulation text with clear 勿/毋 was available)*.

### U04 People and pronouns
- **Skills**: personal pronouns (吾 我 余 予 爾 汝); 其 "his, its"; 之 "him, it";
  demonstratives (此 彼 是 斯); kinship terms.
- **Grammar**: `personal-pronouns`, `qi-pronoun`, `zhi-object`, `demonstratives`
- **Genres**: letter
- **Sources**: 曾國藩家書: letters 諭紀澤 (十月二十五日), 諭紀澤紀鴻 (二月二十五日),
  致溫弟 (六月初六日).

### U05 The noun phrase: 之 and 其
- **Skills**: 之 joining a modifier to a noun; 之 between subject and verb; 其 as subject of a clause.
- **Grammar**: `zhi-attributive`, `zhi-nominaliser`, `ye-topic`
- **Genres**: essay
- **Candidate sources**: 梁啟超〈少年中國說〉(1900), opening (the example passage);
  short 論說 editorials from 申報.

### U06 Prepositions
- **Skills**: 以 "by means of, with"; 於/于 "at, in, to, than"; 爲 "for"; 與 "with";
  自/由 "from"; 至 "to"; 及 "and, up to".
- **Grammar**: `yi-preposition`, `yu-preposition`, `wei-preposition`, `yu-with`, `zi-you-from`
- **Genres**: diplomatic
- **Sources**: 南京條約 (1842), articles 1–5 and 7 *(no 申報 notices are available as text)*.

### U07 Time, aspect and modality
- **Skills**: 已, 既, 嘗, 將, 方; final 矣; modal verbs 可 能 得 足 宜 當 須 必.
- **Grammar**: `aspect-markers`, `yi-final`, `modal-verbs`
- **Genres**: diary, letter
- **Sources**: 薛福成《出使英法義比四國日記》(1890), first entry; 曾國藩家書, two letters on study.
  *(No 申報 reports are available as text.)*

### U08 所, 者 and the passive
- **Skills**: 所 + verb "that which"; 所以; 者 "the one who"; passives with 爲…所, 見, 被, 於.
- **Grammar**: `suo`, `suoyi`, `zhe-nominaliser`, `passives`
- **Genres**: legal, essay, letter
- **Sources**: 暫行新刑律 (1912), articles 48, 271, 276, 311; 梁啟超〈新民說〉, four 所以 sentences;
  曾國藩家書 (1870) and 薛福成's diary for passives. *(No 申報 reports are available as text.)*

### U09 Linking clauses
- **Skills**: 而; 則; 且, 乃, 遂; cause (故, 是以, 因); condition (若, 如, 苟, 使, 倘);
  concession (雖, 縱).
- **Grammar**: `er-conjunction`, `ze`, `causal`, `conditionals`, `concessives`
- **Genres**: essay
- **Sources**: 梁啟超〈變法通議·自序〉(時務報, 1896); 嚴復〈原強〉(1895).

### U10 Questions and rhetoric
- **Skills**: final particles 乎 歟 耶 哉; question words 何 安 孰 誰 奚 焉;
  rhetorical questions (豈…哉, 不亦…乎); exclamation.
- **Grammar**: `question-particles`, `question-words`, `rhetorical-questions`, `qi-modal` (added after the U05 pilot)
- **Genres**: essay
- **Sources**: 梁啟超〈少年中國說〉(1900), paragraphs 3–5; 〈新民說·論自由〉(1902).

---

## 4. Intermediate units

### U11 Reading the original page
- **Skills**: dividing unpunctuated text (句讀) using particles, parallelism and
  four-character rhythm; vertical right-to-left layout; elevation of honorific
  words (抬頭); period punctuation marks; how newspapers and string-bound books lay out the page.
- **Grammar/skills**: `judou`, `boundary-particles`, `elevation`
- **Genres**: newspaper, official
- **Sources**: 張之洞《勸學篇·序》(1898); 南京條約 articles 9–10 (elevation spaces); 臨時約法,
  promulgation and articles 1–4. *(No 京報 or 申報 pages are available as text; page images could be added later.)*
- **Default view**: unpunctuated and vertical.

### U12 Parallelism, allusion and rhythm
- **Skills**: parallel couplets (對偶); four- and six-character prose (四六);
  allusion (典故) and quotation of the Classics; how to trace an allusion.
- **Grammar/skills**: `parallelism`, `allusion`, `four-character-phrases`
- **Genres**: essay, literary
- **Sources**: 嚴復《天演論·譯例言》(1898), items 1 and 3; 林紓《黑奴籲天錄·序》(1901);
  王國維《人間詞話》(1908), entries 1, 26 and 17 (unpublished). *(No 祭文 used: a parallel-prose
  祭文 could be added as an optional extra passage.)*

### U13 The Qing state: memorials and edicts
- **Skills**: the structure of a memorial (奏爲…事、竊…、伏乞…、謹奏) and of an edict
  (上諭, 著…, 欽此); a minister's humble language (臣, 竊, 伏, 謹); the vermilion rescript (知道了).
- **Grammar/skills**: `memorial-formulas`, `edict-formulas`
- **Genres**: official
- **Sources**: the 明定國是詔 edict (1898); the 1905 joint memorial asking to end the
  examination system (袁世凱 等) with the edict 停罷科舉詔; 民政部奏啓用印信日期摺 (1907), a complete
  memorial with rescript from the 北洋官報. *(No 京報 text is available; the gazette memorial stands in for it.)*

### U14 The Republican state: orders, petitions and regulations
- **Skills**: document types (令, 呈, 咨, 批, 訓令, 布告); directive language
  (仰, 應, 須, 著即); how a document cites earlier documents (準…咨開, 等因).
- **Grammar/skills**: `document-types`, `directive-language`, `embedded-citation`
- **Genres**: official
- **Sources**: 臨時政府公報 no. 15 (14 February 1912): the President's order to protect the
  schools of Nanjing (with the Ministry of Education's petition quoted inside it); the 內務部
  petition on the police school and the 實業部 ruling on Lake Shaobo; the telegrams of Yuan Shikai and
  Sun Wen on the abdication. *(The footbinding order is not on Wikisource as a separate text; it could
  replace or supplement the first passage later.)*

### U15 Law and treaties
- **Skills**: legal drafting (凡, 均, 得, 不得, 但, 其…者); treaty articles and how parallel texts in two languages relate.
- **Grammar/skills**: `legal-language`, `treaty-language`
- **Genres**: legal, diplomatic
- **Sources**: 臨時約法 (1912), articles 15, 30–36 and 40; 馬關條約 (1895), articles 1 and 5 and the
  separate article on the English text; 中英天津條約 (1858), articles 1, 50 and 51. *(南京條約 and the
  penal code were already used in U06, U08 and U11.)*

### U16 The press and the new vocabulary
- **Skills**: new terms, many borrowed from Japanese (經濟, 社會, 革命, 自由, 權利);
  transliteration of foreign names and places; the essay style of the reform-era periodicals (新民體).
- **Grammar/skills**: `neologisms`, `transliteration`
- **Genres**: essay, diary
- **Sources**: 梁啟超《新史學》(新民叢報, 1902), opening of 中國之舊史; 王國維《論新學語之輸入》(1905);
  薛福成《出使英法義比四國日記》, entries for 光緒十六年五月初二日 and 六月初四日. *(A 東方雜誌 article has not yet
  been found as text by an author who died in 1956 or earlier; one could be added later.)*

### U17 Thought and translation
- **Skills**: philosophical vocabulary (性, 理, 氣, 道, 群, 公/私); how translators
  rendered Western concepts; argument and refutation.
- **Grammar/skills**: `philosophical-terms`, `argument-structure`
- **Genres**: essay, scholarly
- **Sources**: 嚴復《天演論》(1898), 導言一〈察變〉 and 導言十三〈制私〉 with Yan's 復案 (the 〈譯例言〉
  is already read in U12); 章炳麟〈俱分進化論〉(民報, 1906), opening. *(康有為《大同書》 was a candidate; it
  could replace or follow the Zhang passage.)*

### U18 Scholarship and history writing
- **Skills**: biographical conventions (字, 號, 籍貫, career summaries);
  commentary and citation (卷, 按/案, 云, 注); prefaces and colophons; local gazetteers (方志).
- **Grammar/skills**: `biography-conventions`, `citation-conventions`
- **Genres**: scholarly
- **Candidate sources**: 《清史稿》(1927) biographies; 梁啟超《清代學術概論》(1920);
  王國維〈殷周制度論〉(1917), opening; a county gazetteer entry.

### U19 Letters, diaries and polite language
- **Skills**: letter formulas (敬啟者, 台鑒, 專此, 順頌時祺, 頓首); honorific and humble
  forms (令尊, 家父, 貴, 敝, 拙); diary conventions.
- **Grammar/skills**: `epistolary-formulas`, `honorific-humble`
- **Genres**: letter
- **Candidate sources**: formal letters from 曾國藩 and others; 翁同龢日記; letter-writing manuals (尺牘) of the period.

### U20 Between literary and vernacular
- **Skills**: recognising vernacular elements (的, 了, 這, 們, 是 as copula) inside
  literary prose; mixed registers in 1910s–20s writing; the language debates themselves.
- **Grammar/skills**: `vernacular-elements`, `mixed-register`
- **Genres**: essay, newspaper
- **Candidate sources**: 陳獨秀〈文學革命論〉(1917); 胡適〈文學改良芻議〉(1917),
  which argues for the vernacular but is itself written in literary Chinese; magazine
  editorials from the 1920s.

### Reading assistant (intermediate)
- **Skills**: a method for tackling an unfamiliar text: segmenting, identifying
  function words, finding terms and allusions, checking against reference works; using
  the AI assistant critically (what it is good at, how it fails).
- **Content**: guided walkthroughs with 2–3 passages, then the learner's own text in the assistant.
- To be specified in detail later (`content/assistant/`).

---

## 5. Toolkit (outside the path)

Reference pages that any unit can link to. They are not graded and have no passages.

| ID | Topic | Contents |
|---|---|---|
| T1 | Script and dictionaries | Traditional characters, radicals, variant forms (異體字: 爲/為, 眞/真); print and online dictionaries; looking up an unknown character |
| T2 | Dates and calendars | Reign titles, the sexagenary cycle (干支), lunar months, Republican years, conversion tools |
| T3 | Names, titles and offices | Personal names (名, 字, 號); Qing and Republican offices and ranks; forms of address |
| T4 | Money, weights and measures | 兩, 錢, 元, 角; 里, 畝, 斤, 石 and their period values |
| T5 | Romanisation | Wade–Giles, postal and other period spellings ↔ pinyin, for using older scholarship |
| T6 | Research resources | Full-text databases, digitised newspapers and gazetteers, biographical databases, Cambridge library resources |
| T7 | Grammatical terms | Plain-English definitions of every grammatical term the course uses |

Tables such as reign periods or the Wade–Giles chart are kept as separate CSV files
in `content/toolkit/data/`, so the app can build tools such as date and romanisation converters from them.

---

## 6. Rights

The course will be used from 2027. Under UK law (author's life + 70 years), work by an
author who died in **1956 or earlier** is in the public domain from 1 January 2027.
Official and anonymous texts (edicts, laws, treaties, newspaper reports) are safe.

Candidates that need care:

| Source | Issue |
|---|---|
| 胡適 (d. 1962) | In copyright until 2032. Short excerpts under fair dealing for instruction |

All candidate sources above still have to be checked against an actual edition before
any passage is written.

---

## 7. Scope and schedule

- **Full course**: 20 units × 3 passages = **60 passages**, about 90 grammar/skill files, 5 toolkit pages, plus the assistant unit.
- **Pilot core** (needed for spring 2027 testing): **U01–U06**, **U11**, **U13**,
  **U16**, and toolkit **T1–T2**: 27 passages. These show every display mode, both
  levels and three genres.
- The rest is written after the pilot, informed by the feedback, in time for expert review in summer 2027.

---

## 8. Decisions (2026-11-07)

1. **Toolkit**: agreed, T1–T7, with data in separate CSV files. Added to the spec (section 7).
2. **Three passages per unit**, at the lengths in section 2: agreed.
3. **Pilot core** as in section 7: agreed.
4. **Grammar sequence**: agreed as it stands.
5. **Genre `textbook`**: added to the spec.

The outline has been turned into a `content/` skeleton: `course.md`, 20 unit files,
62 grammar stubs and 7 toolkit stubs, all with `status: planned`. The 60 passages
are listed in their units as planned items.
