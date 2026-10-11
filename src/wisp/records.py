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

Clock = Callable[[Path], datetime]


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
    text: str
    created: datetime
    changed: datetime

    @property
    def kind(self) -> Kind:
        return parse(self.text)[0]

    @property
    def line(self) -> str:
        return parse(self.text)[1]


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


def birth_time(path: Path) -> datetime:
    stat = path.stat()
    return datetime.fromtimestamp(getattr(stat, "st_birthtime", stat.st_mtime))


def modified_time(path: Path) -> datetime:
    return datetime.fromtimestamp(path.stat().st_mtime)


def read_folder(
    folder: Path, created: Clock = birth_time, changed: Clock = modified_time
) -> list[Record]:
    if not folder.is_dir():
        return []
    return sorted(
        (read_record(path, created, changed) for path in record_files(folder)), key=newest_first
    )


def record_files(folder: Path) -> Iterable[Path]:
    return (
        path
        for path in folder.iterdir()
        if path.is_file() and path.suffix == EXTENSION and not path.name.startswith(".")
    )


def read_record(path: Path, created: Clock, changed: Clock) -> Record:
    text = first_line(path.read_text(encoding="utf-8"))
    return Record(path, text, created(path), changed(path))


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


def mark(path: Path) -> Path:
    content = path.read_text(encoding="utf-8")
    kind, line = parse(first_line(content))
    if kind in FLIPPED:
        rewrite_first_line(path, content, compose(FLIPPED[kind], line))
    return path


def decide(path: Path, resolution: str) -> Path:
    if not resolution.strip():
        raise Blank(resolution)
    content = path.read_text(encoding="utf-8")
    kind, line = parse(first_line(content))
    if kind in (Kind.QUESTION, Kind.DECISION):
        settled = compose(Kind.DECISION, line + RESOLVED + resolution.strip())
        rewrite_first_line(path, content, settled)
    return path


def rewrite_first_line(path: Path, content: str, text: str) -> None:
    path.write_text(replace_first_line(content, text), encoding="utf-8")


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
