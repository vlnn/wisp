from __future__ import annotations

import calendar
import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta

from wisp.records import Kind, Record, parse

Span = tuple[date, date]

DAY_NAMES = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
WEEKDAYS = {name[:cut]: n for n, name in enumerate(DAY_NAMES) for cut in (3, len(name))}
DATED = re.compile(r"(\d{4})-(\d{2})(?:-(\d{2}))?")


@dataclass(frozen=True)
class Query:
    kind: Kind | None
    words: str
    span: Span | None = None


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
    span, remaining = windowed(rest.split(), today) if today else (None, rest.split())
    return Query(None if kind is Kind.LOG else kind, " ".join(remaining), span)


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
    return calendar_span(token)


def calendar_span(token: str) -> Span | None:
    found = DATED.fullmatch(token)
    if not found:
        return None
    year, month = int(found[1]), int(found[2])
    try:
        if found[3]:
            return (date(year, month, int(found[3])),) * 2
        return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])
    except ValueError:
        return None


def in_scope(query: Query, record: Record) -> bool:
    return query.kind in (None, record.kind) and within(query.span, record)


def within(span: Span | None, record: Record) -> bool:
    return span is None or span[0] <= record.created.date() <= span[1]


def wanted(query: Query, record: Record) -> bool:
    return in_scope(query, record) and matches(query.words, record.line)


def search(text: str, records: Iterable[Record], today: date | None = None) -> list[Record]:
    asked = query(text, today)
    return [record for record in records if wanted(asked, record)]
