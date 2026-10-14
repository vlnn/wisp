from __future__ import annotations

import calendar
import re
import unicodedata
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, timedelta

from wisp.records import Kind, Record, parse

Span = tuple[date, date]

DAY_NAMES = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
WEEKDAYS = {name[:cut]: n for n, name in enumerate(DAY_NAMES) for cut in (3, len(name))}
DATED = re.compile(r"(\d{4})-(\d{2})(?:-(\d{2}))?")
EXCLUDED = re.compile(r"-\w.*")


@dataclass(frozen=True)
class Query:
    kind: Kind | None
    words: str
    span: Span | None = None
    without: tuple[str, ...] = ()


def fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def words(text: str) -> list[str]:
    return re.findall(r"\w+", fold(text))


def matches(query: str, text: str) -> bool:
    have = words(text)
    return all(any(word.startswith(wanted) for word in have) for wanted in words(query))


def query(text: str, today: date | None = None) -> Query:
    kind, rest = parse(text.strip())
    span, tokens = windowed(rest.split(), today) if today else (None, rest.split())
    without, remaining = exclusions(tokens)
    return Query(None if kind is Kind.LOG else kind, " ".join(remaining), span, without)


def exclusions(tokens: list[str]) -> tuple[tuple[str, ...], list[str]]:
    excluded = tuple(token[1:] for token in tokens if is_exclusion(token))
    return excluded, [token for token in tokens if not is_exclusion(token)]


def is_exclusion(token: str) -> bool:
    return EXCLUDED.fullmatch(token) is not None


def windowed(tokens: list[str], today: date) -> tuple[Span | None, list[str]]:
    for n, token in enumerate(tokens):
        span = days(token, today)
        if span:
            return span, tokens[:n] + tokens[n + 1 :]
    return None, tokens


def days(token: str, today: date) -> Span | None:
    word = fold(token)
    if word == "today":
        return today, today
    if word == "yesterday":
        return (today - timedelta(days=1),) * 2
    if word in WEEKDAYS:
        back = (today.weekday() - WEEKDAYS[word]) % 7
        return (today - timedelta(days=back),) * 2
    if word in RANGES:
        return RANGES[word](today)
    return calendar_span(token)


def this_day(today: date) -> Span:
    return today, today


def this_week(today: date) -> Span:
    monday = today - timedelta(days=today.weekday())
    return monday, monday + timedelta(days=6)


def this_month(today: date) -> Span:
    return whole_month(today.year, today.month)


def this_year(today: date) -> Span:
    return date(today.year, 1, 1), date(today.year, 12, 31)


RANGES: dict[str, Callable[[date], Span]] = {
    "#today": this_day,
    "#week": this_week,
    "#month": this_month,
    "#year": this_year,
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
    )


def within(span: Span | None, record: Record) -> bool:
    return span is None or span[0] <= record.created.date() <= span[1]


def left_out(without: Iterable[str], record: Record) -> bool:
    return any(matches(word, record.line) for word in without)


def wanted(query: Query, record: Record) -> bool:
    return in_scope(query, record) and matches(query.words, record.line)


def search(text: str, records: Iterable[Record], today: date | None = None) -> list[Record]:
    asked = query(text, today)
    return [record for record in records if wanted(asked, record)]
