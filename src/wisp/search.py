from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

from wisp.records import Record


def fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def words(text: str) -> list[str]:
    return re.findall(r"\w+", fold(text))


def matches(query: str, text: str) -> bool:
    have = words(text)
    return all(any(word.startswith(wanted) for word in have) for wanted in words(query))


def search(query: str, records: Iterable[Record]) -> list[Record]:
    return [record for record in records if matches(query, record.text)]
