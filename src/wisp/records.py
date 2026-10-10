from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from itertools import count
from pathlib import Path
from typing import Callable

EXTENSION = ".md"
SLUG_LIMIT = 60
FALLBACK_SLUG = "note"

Created = Callable[[Path], datetime]
Changed = Callable[[Path], datetime]


class Kind(Enum):
    LOG = ""
    TASK = "."
    DONE = "*"
    NOTE = "!"


SIGILS = {kind.value: kind for kind in Kind if kind.value}
FLIPPED = {Kind.TASK: Kind.DONE, Kind.DONE: Kind.TASK}


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
    if text[:1] in SIGILS and (len(text) == 1 or text[1].isspace()):
        return SIGILS[text[0]], text[1:].strip()
    return Kind.LOG, text


def compose(kind: Kind, line: str) -> str:
    return f"{kind.value} {line}" if kind.value else line


def normalise(text: str) -> str:
    return compose(*parse(text.strip()))


def birth_time(path: Path) -> datetime:
    stat = path.stat()
    return datetime.fromtimestamp(getattr(stat, "st_birthtime", stat.st_mtime))


def modified_time(path: Path) -> datetime:
    return datetime.fromtimestamp(path.stat().st_mtime)


def read_folder(
    folder: Path, created: Created = birth_time, changed: Changed = modified_time
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


def read_record(path: Path, created: Created, changed: Changed) -> Record:
    text = first_line(path.read_text(encoding="utf-8"))
    return Record(path, text, created(path), changed(path))


def first_line(content: str) -> str:
    return next((line.strip() for line in content.splitlines() if line.strip()), "")


def body(content: str) -> str:
    lines = content.splitlines()
    first = next((n for n, line in enumerate(lines) if line.strip()), len(lines))
    return "\n".join(lines[first + 1 :]).strip()


def newest_first(record: Record):
    return (-record.created.timestamp(), record.path.name)


def keep(folder: Path, text: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = free_path(folder, slug(text))
    write_text(path, normalise(text))
    return path


def rename(path: Path, text: str) -> Path:
    old = first_line(path.read_text(encoding="utf-8"))
    write_text(path, normalise(text))
    if slug(text) == slug(old):
        return path
    target = free_path(path.parent, slug(text))
    path.rename(target)
    return target


def mark(path: Path) -> Path:
    content = path.read_text(encoding="utf-8")
    kind, line = parse(first_line(content))
    if kind in FLIPPED:
        flipped = compose(FLIPPED[kind], line)
        path.write_text(replace_first_line(content, flipped), encoding="utf-8")
    return path


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
