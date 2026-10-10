from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass

from wisp.records import Kind, Record, parse


@dataclass(frozen=True)
class Query:
    kind: Kind | None
    words: str


def fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def words(text: str) -> list[str]:
    return re.findall(r"\w+", fold(text))


def matches(query: str, text: str) -> bool:
    have = words(text)
    return all(any(word.startswith(wanted) for word in have) for wanted in words(query))


def query(text: str) -> Query:
    kind, rest = parse(text.strip())
    return Query(None if kind is Kind.LOG else kind, rest)


def wanted(query: Query, record: Record) -> bool:
    return query.kind in (None, record.kind) and matches(query.words, record.line)


def search(text: str, records: Iterable[Record]) -> list[Record]:
    asked = query(text)
    return [record for record in records if wanted(asked, record)]
