"""Small tools built from the toolkit data files (content/toolkit/data/)."""
from __future__ import annotations

from dataclasses import dataclass

STEMS = "甲乙丙丁戊己庚辛壬癸"
BRANCHES = "子丑寅卯辰巳午未申酉戌亥"
DIGITS = "〇一二三四五六七八九"


def cyclical(year: int) -> str:
    """The sexagenary (干支) name of a Western year; 1864 and 1924 were 甲子."""
    return STEMS[(year - 4) % 10] + BRANCHES[(year - 4) % 12]


def chinese_number(n: int) -> str:
    """1 → 一, 10 → 十, 24 → 二十四, 38 → 三十八 (for reign years, n < 100)."""
    if n < 10:
        return DIGITS[n]
    tens, units = divmod(n, 10)
    return ("" if tens == 1 else DIGITS[tens]) + "十" + (DIGITS[units] if units else "")


def year_name(n: int) -> str:
    """The way a reign or Republican year is written: 元年, 二年 … 二十四年."""
    return "元年" if n == 1 else chinese_number(n) + "年"


@dataclass
class Reign:
    reign: str
    pinyin: str
    emperor_name: str
    first_year: int
    last_year: int
    note: str = ""

    @property
    def length(self) -> int:
        return self.last_year - self.first_year + 1


def reigns_from_rows(rows: list[dict]) -> list[Reign]:
    return [Reign(r["reign"], r["pinyin"], r["emperor_name"], int(r["first_year"]), int(r["last_year"]),
                  r.get("note", "")) for r in rows]


@dataclass
class Conversion:
    ok: bool
    lines: list[str]          # results, plain text with Chinese
    message: str = ""         # an explanation when ok is False


def reign_to_western(reigns: list[Reign], reign: str, n: int) -> Conversion:
    r = next((x for x in reigns if x.reign == reign), None)
    if r is None:
        return Conversion(False, [], "Choose a reign title.")
    if not 1 <= n <= r.length:
        return Conversion(False, [], f"The {r.pinyin} reign has years 1 to {r.length} ({r.first_year}–{r.last_year}).")
    y = r.first_year + n - 1
    lines = [f"{r.reign}{year_name(n)} = {y} ({cyclical(y)})"]
    if r.note:
        lines.append(r.note)
    return Conversion(True, lines)


def western_to_chinese(reigns: list[Reign], y: int) -> Conversion:
    lines = []
    for r in reigns:
        if r.first_year <= y <= r.last_year:
            lines.append(f"{y} = {r.reign}{year_name(y - r.first_year + 1)} ({cyclical(y)})")
    if y >= 1912:
        lines.append(f"{y} = 民國{year_name(y - 1911)} ({cyclical(y)})")
    if not lines:
        first, last = min(r.first_year for r in reigns), max(r.last_year for r in reigns)
        return Conversion(False, [f"{y}: cyclical year {cyclical(y)}"],
                          f"The reign table covers {first}–{last}; from 1912 the Republic's years are given.")
    return Conversion(True, lines)


def republic_to_western(n: int) -> Conversion:
    if n < 1:
        return Conversion(False, [], "Republican years start at 1 (民國元年 = 1912).")
    y = 1911 + n
    return Conversion(True, [f"民國{year_name(n)} = {y} ({cyclical(y)})"])
