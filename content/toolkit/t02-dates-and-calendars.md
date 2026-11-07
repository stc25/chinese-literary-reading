---
id: t02
title: Dates and calendars
data: [qing-reign-periods.csv]
status: draft
---

<!-- REVIEW(claude): Check the telegraph day-code table (some codes have variants in different sources), and confirm that the conversion tools named are still available. -->

## Summary

Reign titles, the sexagenary cycle, lunar months and Republican years, and how to convert them to Western dates.

## Reign titles

Qing documents date by the emperor's **reign title** (年號) and the year of the reign: 光緒二十四年
"the 24th year of Guangxu" (1898). The first year is 元年, not 一年. A reign began in the lunar
new year after the previous emperor died.

| Reign | Pinyin | Emperor's personal name | First year | Last year |
|---|---|---|---|---|
| 嘉慶 | Jiāqìng | 顒琰 | 1796 | 1820 |
| 道光 | Dàoguāng | 旻寧 | 1821 | 1850 |
| 咸豐 | Xiánfēng | 奕詝 | 1851 | 1861 |
| 同治 | Tóngzhì | 載淳 | 1862 | 1874 |
| 光緒 | Guāngxù | 載湉 | 1875 | 1908 |
| 宣統 | Xuāntǒng | 溥儀 | 1909 | 1911 |

To convert, add the year of the reign to the year before the first year: 光緒二十四年 = 1874 + 24 =
1898. The table is also in the data file `qing-reign-periods.csv`.

Emperors are also referred to by their temple names: 德宗 (Guangxu), 文宗 (Xianfeng). In 1912 Qing
loyalists went on using 宣統 years, or cyclical years alone, to avoid the Republican calendar (see
[The biography of Yan Fu](../units/u18-scholarship-and-history/u18-p01-the-biography-of-yan-fu.md)).

## The sexagenary cycle

Years and days are also counted in a cycle of sixty, formed by combining the ten **heavenly stems**
(天干) with the twelve **earthly branches** (地支):

| Stems | 甲 乙 丙 丁 戊 己 庚 辛 壬 癸 |
|---|---|
| Branches | 子 丑 寅 卯 辰 巳 午 未 申 酉 戌 亥 |

The cycle runs 甲子, 乙丑, 丙寅 … 癸亥, then starts again. 1864 and 1924 were 甲子 years. To find the
cyclical name of a year: subtract 3, divide by 10, and the remainder gives the stem (1 = 甲 … 0 = 癸);
divide the same number by 12 and the remainder gives the branch (1 = 子 … 0 = 亥). For 1898: 1895 → stem
5 = 戊, branch 11 = 戌: 戊戌, the year of the Hundred Days' Reform.

Many events are named by their cyclical year: 戊戌變法 (1898), 庚子拳亂 (1900), 辛亥革命 (1911). Because
the cycle repeats, a cyclical year alone is ambiguous; context fixes the sixty-year period.

The stems are also used as ordinal labels, "(a), (b), (c)": 甲, 乙, 丙.

## Months, days and hours

Before 1912 dates are **lunar**. A year has twelve months of 29 or 30 days, with an intercalary month
(閏月) added about every three years. The first month is 正月, the twelfth often 臘月. The lunar new year
falls between late January and late February, so the last month of a Chinese year can fall in the next
Western year.

| Term | Meaning |
|---|---|
| 初一 … 初十 | 1st to 10th of the month |
| 十一 … 三十 | 11th to 30th |
| 朔 | the 1st (new moon) |
| 望 | the 15th (full moon); 旣望 the 16th |
| 晦 | the last day of the month |
| 旬 | a ten-day period: 上旬, 中旬, 下旬 |

**Hours.** The day had twelve double hours (時辰), named by the branches: 子 = 11 p.m.–1 a.m., 丑 = 1–3
a.m., 寅 = 3–5 a.m., 卯 = 5–7 a.m., and so on to 亥 = 9–11 p.m. Each was divided into 初 "beginning" and 正
"middle", and into 刻 "quarters". 午正 is noon. With Western clocks, 點鐘 "o'clock" and 刻 "quarter hour"
came into use (see [Paris to London](../units/u16-the-press-and-new-vocabulary/u16-p03-paris-to-london.md)).

**Telegraph day codes (韻目代日).** Telegrams gave the day of the month as one character taken from the
rhyme categories of the rhyme books. The month is not stated.

| Day | Code | Day | Code | Day | Code |
|---|---|---|---|---|---|
| 1 | 東 | 11 | 眞 | 21 | 馬 |
| 2 | 冬 | 12 | 文 | 22 | 養 |
| 3 | 江 | 13 | 元 | 23 | 漾 |
| 4 | 支 | 14 | 寒 | 24 | 敬 |
| 5 | 微 | 15 | 刪 | 25 | 有 |
| 6 | 魚 | 16 | 銑 | 26 | 宥 |
| 7 | 虞 | 17 | 篠 | 27 | 沁 (感) |
| 8 | 齊 | 18 | 巧 | 28 | 勘 (儉) |
| 9 | 佳 | 19 | 皓 | 29 | 艷 |
| 10 | 灰 | 20 | 號 (哿) | 30 | 卅 |
| | | | | 31 | 世 or 引 |

Events are often named by their telegram code: the 馬日事變 (21 May 1927).

## Republican years

From 1 January 1912 the Republic used the Western (Gregorian) calendar, counted from 1912 as 民國元年.
To convert, add 1911: 民國八年 = 1919. Dates are given by month and day as in the West: 八年三月十八日 =
18 March 1919. The lunar calendar went on being used in private life, in almanacs and in many letters
and diaries, so check which calendar a private document uses.

Japanese dates appear in texts printed or written in Japan: 明治 (1868–1912), 大正 (1912–1926), 昭和
(1926–1989). 明治三十八年 = 1905.

## Converting dates

- **Year**: use the reign table above, or add 1911 to a Republican year.
- **Month and day (lunar)**: there is no simple formula. Use a conversion table or tool:
  - 中央研究院〈兩千年中西曆轉換〉 (online, Academia Sinica);
  - 鄭鶴聲《近世中西史日對照表》 (1936; tables for 1516–1941);
  - 薛仲三、歐陽頤《兩千年中西曆對照表》 (1940).
- **Undated letters**: work out the year from people, events and offices mentioned, as editors of
  Zeng Guofan's letters did (see [To my parents, to my sons](../units/u19-letters-and-diaries/u19-p02-to-my-parents-to-my-sons.md)).

## Practice

### 1. short-answer

Convert 咸豐十年 and 民國十六年 to Western years.

**Answer:** 咸豐十年 = 1850 + 10 = 1860. 民國十六年 = 1911 + 16 = 1927.

### 2. short-answer

What Western year was the 庚子 year of the Boxer rising? Check it with the method above.

**Answer:** 1900. 1900 − 3 = 1897: remainder 7 on division by 10 gives 庚; remainder 1 on division by 12 gives 子.

### 3. choice

A telegram is dated 元. On which day of the month was it sent?

- [ ] the 1st
- [x] the 13th
- [ ] the 31st
