from __future__ import annotations

import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from wisp import search
from wisp.records import Record, tags_in, untagged

LIMIT = 3
MENTION = re.compile(r"(?<!\w)@[^\W\d_](?:[\w-]*\w)?")


@dataclass(frozen=True)
class Suggestion:
    text: str
    adds: str
    why: str


def spelled_by_key() -> defaultdict[str, Counter[str]]:
    return defaultdict(Counter)


@dataclass
class Vocabulary:
    spellings: defaultdict[str, Counter[str]] = field(default_factory=spelled_by_key)
    mentions: defaultdict[str, Counter[str]] = field(default_factory=spelled_by_key)
    with_tag: defaultdict[str, Counter[str]] = field(default_factory=spelled_by_key)
    seen: Counter[str] = field(default_factory=Counter)

    def add(self, record: Record) -> None:
        words = set(search.words(untagged(record.line)))
        self.seen.update(words)
        for tag in set(record.tags):
            key = search.tag_key(tag)
            self.spellings[key][tag.lower()] += 1
            self.with_tag[key].update(words)
        for mention in set(mentions_in(record.line)):
            self.mentions[mention_key(mention)][mention] += 1

    def count(self, key: str) -> int:
        return sum(self.spellings[key].values()) if key in self.spellings else 0


def vocabulary(records: Iterable[Record]) -> Vocabulary:
    vocab = Vocabulary()
    for record in records:
        vocab.add(record)
    return vocab


def mentions_in(line: str) -> list[str]:
    return [found for found in MENTION.findall(line) if not search.is_rule(found)]


def mention_key(mention: str) -> str:
    return search.fold(mention.lstrip("@"))


def spelling(key: str, spellings: Mapping[str, Counter[str]]) -> str:
    return spellings[key].most_common(1)[0][0]


def suggestions(text: str, vocab: Vocabulary, limit: int = LIMIT) -> list[Suggestion]:
    return completions(text, vocab)[:limit]


def completions(text: str, vocab: Vocabulary) -> list[Suggestion]:
    head, _, last = text.rstrip().rpartition(" ")
    if search.is_tag(last):
        return completed(head, search.tag_key(last), vocab.spellings, carried(text))
    if MENTION.fullmatch(last):
        return completed(head, mention_key(last), vocab.mentions, set())
    return []


def completed(
    head: str, typed: str, spellings: Mapping[str, Counter[str]], present: set[str]
) -> list[Suggestion]:
    keys = [key for key in spellings if key.startswith(typed) and key != typed]
    fresh = [key for key in keys if key not in present]
    ordered = sorted(fresh, key=lambda key: (-sum(spellings[key].values()), key))
    return [finished(head, spelling(key, spellings)) for key in ordered]


def finished(head: str, word: str) -> Suggestion:
    return Suggestion(f"{head} {word}".lstrip(), word, "completes")


def carried(text: str) -> set[str]:
    return {search.tag_key(tag) for tag in tags_in(text)}
