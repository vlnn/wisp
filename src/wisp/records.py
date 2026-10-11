from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from itertools import count
from pathlib import Path

EXTENSION = ".md"
SLUG_LIMIT = 60
FALLBACK_SLUG = "note"

Stamps = Callable[[Path], tuple[datetime, datetime]]


class Kind(Enum):
    LOG = ""
    TASK = "."
    DONE = "*"
    NOTE = "!"
    QUESTION = "?"
    DECISION = "="


SIGILS = {kind.value: kind for kind in Kind if kind.value}
TIGHT = {Kind.QUESTION, Kind.NOTE, Kind.DECISION}
FLIPPED = {Kind.TASK: Kind.DONE, Kind.DONE: Kind.TASK, Kind.DECISION: Kind.QUESTION}
RESOLVED = " | "


class Blank(ValueError):
    pass


@dataclass(frozen=True)
class Record:
    path: Path
    kind: Kind
    line: str
    created: datetime
    changed: datetime

    @classmethod
    def parsed(cls, path: Path, text: str, created: datetime, changed: datetime) -> Record:
        kind, line = parse(text)
        return cls(path, kind, line, created, changed)

    @property
    def text(self) -> str:
        return compose(self.kind, self.line)


def parse(text: str) -> tuple[Kind, str]:
    kind = SIGILS.get(text[:1])
    if kind and (kind in TIGHT or len(text) == 1 or text[1].isspace()):
        return kind, text[1:].strip()
    return Kind.LOG, text


def compose(kind: Kind, line: str) -> str:
    return f"{kind.value} {line}" if kind.value else line


def normalise(text: str) -> str:
    kind, line = parse(text.strip())
    if not line:
        raise Blank(text)
    return compose(kind, line)


def file_stamps(path: Path) -> tuple[datetime, datetime]:
    stat = path.stat()
    born = getattr(stat, "st_birthtime", stat.st_mtime)
    return datetime.fromtimestamp(born), datetime.fromtimestamp(stat.st_mtime)


def read_folder(folder: Path, stamps: Stamps = file_stamps) -> list[Record]:
    if not folder.is_dir():
        return []
    return sorted((read_record(path, stamps) for path in record_files(folder)), key=newest_first)


def record_files(folder: Path) -> Iterable[Path]:
    return (
        path
        for path in folder.iterdir()
        if path.is_file() and path.suffix == EXTENSION and not path.name.startswith(".")
    )


def read_record(path: Path, stamps: Stamps = file_stamps) -> Record:
    text = first_line(path.read_text(encoding="utf-8"))
    return Record.parsed(path, text, *stamps(path))


def first_line(content: str) -> str:
    return next((line.strip() for line in content.splitlines() if line.strip()), "")


def newest_first(record: Record):
    return (-record.created.timestamp(), record.path.name)


def keep(folder: Path, text: str) -> Path:
    line = normalise(text)
    folder.mkdir(parents=True, exist_ok=True)
    path = free_path(folder, slug(text))
    write_text(path, line)
    return path


def rename(path: Path, text: str) -> Path:
    line = normalise(text)
    old = first_line(path.read_text(encoding="utf-8"))
    write_text(path, line)
    if slug(text) == slug(old):
        return path
    target = free_path(path.parent, slug(text))
    path.rename(target)
    return target


def mark(path: Path) -> str:
    content = path.read_text(encoding="utf-8")
    kind, line = parse(first_line(content))
    if kind not in FLIPPED:
        return first_line(content)
    return rewrite_first_line(path, content, compose(FLIPPED[kind], line))


def decide(path: Path, resolution: str) -> str:
    if not resolution.strip():
        raise Blank(resolution)
    content = path.read_text(encoding="utf-8")
    kind, line = parse(first_line(content))
    if kind not in (Kind.QUESTION, Kind.DECISION):
        return first_line(content)
    settled = compose(Kind.DECISION, line + RESOLVED + resolution.strip())
    return rewrite_first_line(path, content, settled)


def rewrite_first_line(path: Path, content: str, text: str) -> str:
    path.write_text(replace_first_line(content, text), encoding="utf-8")
    return text


def replace_first_line(content: str, text: str) -> str:
    lines = content.splitlines(keepends=True)
    first = next((n for n, line in enumerate(lines) if line.strip()), None)
    if first is None:
        return text + "\n"
    lines[first] = text + "\n"
    return "".join(lines)


def write_text(path: Path, text: str) -> None:
    path.write_text(text.strip() + "\n", encoding="utf-8")


def slug(text: str) -> str:
    joined = "-".join(re.findall(r"\w+", text.casefold()))
    return joined[:SLUG_LIMIT].strip("-") or FALLBACK_SLUG


def free_path(folder: Path, name: str) -> Path:
    candidates = (folder / f"{name}{suffix}{EXTENSION}" for suffix in suffixes())
    return next(path for path in candidates if not path.exists())


def suffixes() -> Iterator[str]:
    yield ""
    for n in count(2):
        yield f"-{n}"
