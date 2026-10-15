from __future__ import annotations

import calendar
import re
import unicodedata
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

from wisp.records import TAG, Kind, Record, compose, parse

Span = tuple[date, date]
Rule = Callable[[date], Span]
Recognise = Callable[[str, date], Optional[Span]]

DAY_NAMES = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
WEEKDAYS = {name[:cut]: n for n, name in enumerate(DAY_NAMES) for cut in (3, len(name))}
DATED = re.compile(r"(\d{4})-(\d{2})(?:-(\d{2}))?")
EXCLUDED = re.compile(r"-\w.*")
RULE = "@"


@dataclass(frozen=True)
class Query:
    kind: Kind | None
    words: str
    span: Span | None = None
    without: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    without_tags: tuple[str, ...] = ()


def fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def words(text: str) -> list[str]:
    return re.findall(r"\w+", fold(text))


def matches(query: str, text: str) -> bool:
    have = words(text)
    return all(any(word.startswith(wanted) for word in have) for wanted in words(query))


def query(text: str, today: date | None = None, recognise: Recognise | None = None) -> Query:
    kind, rest = parse(text.strip())
    tokens = rest.split()
    span, tokens = windowed(tokens, today, recognise or rule) if today else (None, tokens)
    without_tags, tokens = picked(is_excluded_tag, tokens)
    tags, tokens = picked(is_tag, tokens)
    without, remaining = picked(is_exclusion, tokens)
    return Query(
        None if kind is Kind.LOG else kind,
        " ".join(remaining),
        span,
        tuple(token[1:] for token in without),
        tuple(tag_key(token) for token in tags),
        tuple(tag_key(token[1:]) for token in without_tags),
    )


def picked(wanted: Callable[[str], bool], tokens: list[str]) -> tuple[list[str], list[str]]:
    return [t for t in tokens if wanted(t)], [t for t in tokens if not wanted(t)]


def is_exclusion(token: str) -> bool:
    return EXCLUDED.fullmatch(token) is not None


def is_tag(token: str) -> bool:
    return TAG.fullmatch(token) is not None


def is_excluded_tag(token: str) -> bool:
    return token.startswith("-") and is_tag(token[1:])


def logged(text: str) -> str:
    kind, rest = parse(text.strip())
    kept = " ".join(token for token in rest.split() if not only_searches(token))
    return compose(kind, kept).strip()


def only_searches(token: str) -> bool:
    return is_rule(token) or is_exclusion(token) or is_excluded_tag(token)


def tag_key(tag: str) -> str:
    return fold(tag.lstrip("#"))


def windowed(tokens: list[str], today: date, recognise: Recognise) -> tuple[Span | None, list[str]]:
    for n, token in enumerate(tokens):
        span = recognise(token, today)
        if span:
            return span, tokens[:n] + tokens[n + 1 :]
    return None, tokens


def rule(token: str, today: date) -> Span | None:
    return day(token[1:], today) if token.startswith(RULE) else None


def spoken(token: str, today: date) -> Span | None:
    return rule(token, today) or day(token, today)


def is_rule(token: str) -> bool:
    name = token[1:]
    return token.startswith(RULE) and (fold(name) in RULES or calendar_span(name) is not None)


def day(word: str, today: date) -> Span | None:
    named = RULES.get(fold(word))
    return named(today) if named else calendar_span(word)


def this_day(today: date) -> Span:
    return today, today


def the_day_before(today: date) -> Span:
    return (today - timedelta(days=1),) * 2


def last_weekday(weekday: int) -> Rule:
    def back(today: date) -> Span:
        return (today - timedelta(days=(today.weekday() - weekday) % 7),) * 2

    return back


def this_week(today: date) -> Span:
    monday = today - timedelta(days=today.weekday())
    return monday, monday + timedelta(days=6)


def this_month(today: date) -> Span:
    return whole_month(today.year, today.month)


def this_year(today: date) -> Span:
    return date(today.year, 1, 1), date(today.year, 12, 31)


RULES: dict[str, Rule] = {
    "today": this_day,
    "yesterday": the_day_before,
    "week": this_week,
    "month": this_month,
    "year": this_year,
    **{name: last_weekday(n) for name, n in WEEKDAYS.items()},
}


def whole_month(year: int, month: int) -> Span:
    return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])


def calendar_span(token: str) -> Span | None:
    found = DATED.fullmatch(token)
    if not found:
        return None
    year, month = int(found[1]), int(found[2])
    try:
        if found[3]:
            return (date(year, month, int(found[3])),) * 2
        return whole_month(year, month)
    except ValueError:
        return None


def in_scope(query: Query, record: Record) -> bool:
    return (
        query.kind in (None, record.kind)
        and within(query.span, record)
        and not left_out(query.without, record)
        and tagged_with(query.tags, record)
        and not tagged_any(query.without_tags, record)
    )


def within(span: Span | None, record: Record) -> bool:
    return span is None or span[0] <= record.created.date() <= span[1]


def left_out(without: Iterable[str], record: Record) -> bool:
    return any(matches(word, record.line) for word in without)


def tag_keys(record: Record) -> list[str]:
    return [tag_key(tag) for tag in record.tags]


def carries(key: str, keys: list[str]) -> bool:
    return any(have.startswith(key) for have in keys)


def tagged_with(wanted: Iterable[str], record: Record) -> bool:
    keys = tag_keys(record)
    return all(carries(key, keys) for key in wanted)


def tagged_any(unwanted: Iterable[str], record: Record) -> bool:
    keys = tag_keys(record)
    return any(carries(key, keys) for key in unwanted)


def wanted(query: Query, record: Record) -> bool:
    return in_scope(query, record) and matches(query.words, record.line)


def search(
    text: str,
    records: Iterable[Record],
    today: date | None = None,
    recognise: Recognise | None = None,
) -> list[Record]:
    asked = query(text, today, recognise)
    return [record for record in records if wanted(asked, record)]
