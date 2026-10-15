from __future__ import annotations

import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime

from wisp import search
from wisp.records import Record, tags_in, untagged

LIMIT = 3
MIN_STEM = 4
MIN_ROOT = 3
SUFFIXES = (("ies", "y"), ("ing", ""), ("ed", ""), ("s", ""))
MIN_TOGETHER = 2
MIN_SHARE = 0.5
COMPLETES = "completes what you typed"
NAMES = "the line names it"
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
    last: dict[str, datetime] = field(default_factory=dict)

    def add(self, record: Record) -> None:
        words = set(search.words(untagged(record.line)))
        self.seen.update(words)
        for tag in set(record.tags):
            key = search.tag_key(tag)
            self.spellings[key][tag.lower()] += 1
            self.with_tag[key].update(words)
            self.last[key] = max(self.last.get(key, record.created), record.created)
        for mention in set(mentions_in(record.line)):
            self.mentions[mention_key(mention)][mention] += 1

    def count(self, key: str) -> int:
        return sum(self.spellings[key].values()) if key in self.spellings else 0


def vocabulary(records: Iterable[Record]) -> Vocabulary:
    vocab = Vocabulary()
    for record in records:
        vocab.add(record)
    return vocab


def tags_starting(prefix: str, vocab: Vocabulary) -> list[str]:
    return [key for key in by_use(vocab.spellings) if key.startswith(prefix)]


def mentions_in(line: str) -> list[str]:
    return [found for found in MENTION.findall(line) if not search.is_rule(found)]


def mention_key(mention: str) -> str:
    return search.fold(mention.lstrip("@"))


def spelling(key: str, spellings: Mapping[str, Counter[str]]) -> str:
    return spellings[key].most_common(1)[0][0]


def suggestions(text: str, vocab: Vocabulary, limit: int = LIMIT) -> list[Suggestion]:
    found = completions(text, vocab) if typing(text) else ranked(text, vocab)
    return found[:limit]


def typing(text: str) -> bool:
    last = last_word(text)
    return search.is_tag(last) or (MENTION.fullmatch(last) is not None and not search.is_rule(last))


def last_word(text: str) -> str:
    return text.rstrip().rpartition(" ")[2]


def completions(text: str, vocab: Vocabulary) -> list[Suggestion]:
    head, _, last = text.rstrip().rpartition(" ")
    if search.is_tag(last):
        return completed(head, search.tag_key(last), vocab.spellings, carried(text))
    return completed(head, mention_key(last), vocab.mentions, set())


def completed(
    head: str, typed: str, spellings: Mapping[str, Counter[str]], present: set[str]
) -> list[Suggestion]:
    keys = [key for key in by_use(spellings) if key.startswith(typed) and key != typed]
    return [finished(head, spelling(key, spellings)) for key in keys if key not in present]


def by_use(spellings: Mapping[str, Counter[str]]) -> list[str]:
    return sorted(spellings, key=lambda key: (-sum(spellings[key].values()), key))


def finished(head: str, word: str) -> Suggestion:
    return Suggestion(f"{head} {word}".lstrip(), word, COMPLETES)


def ranked(text: str, vocab: Vocabulary) -> list[Suggestion]:
    words = line_words(text)
    present = carried(text)
    named = [key for key in by_use(vocab.spellings) if key not in present and names(words, key)]
    seen = [key for key in strongest(words, vocab) if key not in present and key not in named]
    return [added(text, spelling(key, vocab.spellings), NAMES) for key in named] + [
        added(text, spelling(key, vocab.spellings), seen_with(shares(key, words, vocab)))
        for key in seen
    ]


def strongest(words: list[str], vocab: Vocabulary) -> list[str]:
    scored = {key: sum(shares(key, words, vocab).values()) for key in vocab.with_tag}
    going = [key for key, score in scored.items() if score > 0]
    return sorted(going, key=lambda key: (-scored[key], -vocab.count(key), key))


def shares(key: str, words: Iterable[str], vocab: Vocabulary) -> dict[str, float]:
    together = vocab.with_tag[key]
    found = {word: together[word] / vocab.seen[word] for word in set(words) if together[word]}
    return {
        word: share
        for word, share in found.items()
        if together[word] >= MIN_TOGETHER and share > MIN_SHARE
    }


def seen_with(counted: Mapping[str, float]) -> str:
    return f"seen with {', '.join(sorted(counted))}"


def line_words(text: str) -> list[str]:
    return search.words(untagged(search.logged(text)))


def names(words: Iterable[str], key: str) -> bool:
    return any(related(word, part) for word in words for part in key.split("-"))


def related(word: str, part: str) -> bool:
    shorter, longer = sorted((stem(word), stem(part)), key=len)
    return len(shorter) >= MIN_STEM and longer.startswith(shorter)


def stem(word: str) -> str:
    for suffix, replacement in SUFFIXES:
        root = word[: -len(suffix)]
        if word.endswith(suffix) and len(root) >= MIN_ROOT:
            return root + replacement
    return word


def added(text: str, tag: str, why: str) -> Suggestion:
    return Suggestion(f"{text.rstrip()} {tag}", tag, why)


def carried(text: str) -> set[str]:
    return {search.tag_key(tag) for tag in tags_in(text)}
