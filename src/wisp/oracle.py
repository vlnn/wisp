from __future__ import annotations

import os
import shutil
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol, runtime_checkable

from hoard.alfred import apple, chat
from hoard.alfred.settings import is_on
from hoard.alfred.text import words

from wisp import records, search
from wisp.records import Kind, Record

BUDGET = 12_000
APPLE_BUDGET = 6_000
MIN_TERM = 3
FILLER = frozenset(
    "the and for with about what which when where who why how did does was were are has have "
    "this that these those from into over last any all some there here than then".split()
)
TIMEOUT = 120
MAX_TOKENS = 600
TEMPERATURE = 0.2
DEFAULT_DATA = "~/Library/Application Support/wisp"

SYSTEM = (
    "You answer questions about a person's own one-line work log. "
    "Today is {today}. The log is below the question, newest line first; its heading says when "
    "the log is from, so it is the whole answer for a question about that day. Each line is "
    "`YYYY-MM-DD HH:MM  text`. Some lines carry a word before the text: "
    "TODO is a task still open, DONE is a finished task (the time after DONE is when it "
    "was finished), QUESTION is a question still open, DECIDED is a question settled or a "
    "decision made (the time after DECIDED is when; ` | ` separates a question from its "
    "resolution), NOTE is something the person flagged as important, CHECKLIST is a reusable "
    "list of steps whose runs are the TODO and DONE lines with the same text (`4/7` after a run "
    "is steps done over steps in all). Lines without a word are "
    "plain log entries. Answer from the log only, briefly, "
    "in the language of the question, as plain text without headings."
)

STAMP = "%Y-%m-%d %H:%M"

OnText = Callable[[str], None]
ModelError = chat.ModelError


def worded(error: chat.ModelError, url: str) -> str:
    if error.reason.startswith("HTTP "):
        return f"Model answered {error.reason.split()[1]} at {url}"
    if str(error).startswith(url):
        return f"Model not reachable at {url}"
    return f"Model refused: {error.reason}"


@dataclass(frozen=True)
class Llama:
    url: str
    model: str = ""
    key: str = ""
    budget: int = BUDGET

    @property
    def server(self) -> chat.Server:
        return chat.Server(self.url, self.model, self.key)

    def respond(self, messages: list[dict], on_text: OnText | None) -> str:
        try:
            return chat.respond(
                self.server,
                messages,
                on_text,
                timeout=TIMEOUT,
                temperature=TEMPERATURE,
                max_tokens=MAX_TOKENS,
            )
        except chat.ModelError as error:
            raise ModelError(worded(error, self.url)) from None

    def check(self) -> str:
        named = f" (model {self.model})" if self.model else ""
        return f"server {self.url}{named}: {'reachable' if self.reachable() else 'not reachable'}"

    def reachable(self) -> bool:
        return chat.reachable(self.server)


@dataclass(frozen=True)
class Apple:
    data: Path
    budget: int = APPLE_BUDGET

    def respond(self, messages: list[dict], on_text: OnText | None) -> str:
        return chat.without_thinking(apple.respond(messages, str(self.data), on_text))

    def check(self) -> str:
        if apple.binary(str(self.data)).exists():
            return "Apple Intelligence: helper compiled"
        if shutil.which("swiftc"):
            return "Apple Intelligence: helper compiles on first ask"
        return f"Apple Intelligence: {apple.TOOLS_MISSING}"


@runtime_checkable
class Backend(Protocol):
    @property
    def budget(self) -> int: ...

    def respond(self, messages: list[dict], on_text: OnText | None) -> str: ...

    def check(self) -> str: ...


def backend(env: Mapping[str, str]) -> Backend | None:
    if is_on(env.get("oracle_apple", "")):
        return Apple(data_folder(env))
    url = env.get("oracle_url", "").strip().rstrip("/")
    if not url:
        return None
    return Llama(url, env.get("oracle_model", "").strip(), env.get("oracle_key", "").strip())


def data_folder(env: Mapping[str, str]) -> Path:
    return Path(env.get("alfred_workflow_data") or os.path.expanduser(DEFAULT_DATA))


def answers_folder(env: Mapping[str, str]) -> Path:
    return data_folder(env) / "answers"


def line(record: Record) -> str:
    return f"{record.created:{STAMP}}  {spoken(record)}"


def spoken(record: Record) -> str:
    if record.kind in records.SETTLED:
        return f"{record.kind.spoken} {record.changed:{STAMP}}  {record.line}{counted(record)}"
    if record.kind.spoken:
        return f"{record.kind.spoken}  {record.line}{counted(record)}"
    return record.text


def counted(record: Record) -> str:
    ticked, total = records.progress(record)
    return f"  {ticked}/{total}" if records.is_run(record) else ""


@dataclass(frozen=True)
class Evidence:
    matching: list[Record]
    filling: list[Record]
    terms: list[str]
    without: tuple[str, ...] = ()

    def records(self) -> list[Record]:
        return sorted(self.matching + self.filling, key=records.newest_first)

    def lines(self) -> list[str]:
        return [line(record) for record in self.records()]

    def text(self) -> str:
        return "\n".join(self.lines())


def evidence(
    question: str, logs: Iterable[Record], budget: int = BUDGET, now: datetime | None = None
) -> Evidence:
    asked = search.query(question, now.date() if now else None, search.spoken)
    pool = [r for r in sorted(logs, key=records.newest_first) if search.in_scope(asked, r)]
    singled, terms = single_out(asked.words, pool)
    if singled:
        return Evidence(fit(singled, budget), [], terms, asked.without)
    return Evidence([], fit(pool, budget) or pool[:1], [], asked.without)


def single_out(typed: str, pool: list[Record]) -> tuple[list[Record], list[str]]:
    exact = [r for r in pool if search.matches(typed, r.line)] if typed else []
    if exact:
        return exact, words(typed)
    terms = [w for w in words(typed) if len(w) >= MIN_TERM and w not in FILLER]
    hits = [w for w in terms if any(search.matches(w, r.line) for r in pool)]
    loose = [r for r in pool if any(search.matches(w, r.line) for w in hits)]
    return loose, hits


def fit(logs: Iterable[Record], budget: int) -> list[Record]:
    kept: list[Record] = []
    used = 0
    for record in logs:
        used += len(line(record)) + 1
        if used > budget:
            break
        kept.append(record)
    return kept


def size(logs: list[Record]) -> int:
    return sum(len(line(record)) + 1 for record in logs)


Turn = tuple[str, str]


def prompt(
    question: str,
    logs: Iterable[Record],
    now: datetime,
    budget: int = BUDGET,
    turns: Iterable[Turn] = (),
) -> list[dict]:
    earlier = list(turns)
    first = earlier[0][0] if earlier else question
    room = budget - sum(len(q) + len(a) for q, a in earlier)
    return [
        {"role": "system", "content": SYSTEM.format(today=f"{now:%A %Y-%m-%d}")},
        {"role": "user", "content": asking(first, logs, now, max(room, 0))},
        *replayed(earlier),
        *([{"role": "user", "content": question}] if earlier else []),
    ]


def replayed(turns: list[Turn]) -> list[dict]:
    messages = []
    for n, (question, answer) in enumerate(turns):
        if n:
            messages.append({"role": "user", "content": question})
        messages.append({"role": "assistant", "content": answer})
    return messages


def asking(question: str, logs: Iterable[Record], now: datetime, budget: int) -> str:
    found = evidence(question, logs, budget, now)
    return f"{question}\n\n{heading(question, now, found.terms)}\n{found.text()}"


SCOPED = {
    Kind.TASK: "open tasks",
    Kind.DONE: "finished tasks",
    Kind.NOTE: "notes",
    Kind.QUESTION: "open questions",
    Kind.DECISION: "decisions",
    Kind.CHECKLIST: "checklists",
}


def heading(question: str, now: datetime, terms: Iterable[str] = ()) -> str:
    asked = search.query(question, now.date(), search.spoken)
    bounds = []
    if asked.kind:
        bounds.append(f"{SCOPED[asked.kind]} only")
    if asked.span:
        first, last = asked.span
        bounds.append(f"{first} only" if first == last else f"{first} to {last} only")
    if asked.tags:
        bounds.append(f"tagged {hashed(asked.tags)} only")
    if terms:
        bounds.append(f"lines matching {', '.join(terms)} only")
    if asked.without:
        bounds.append(f"leaving out lines matching {', '.join(asked.without)}")
    if asked.without_tags:
        bounds.append(f"leaving out lines tagged {hashed(asked.without_tags)}")
    return f"Log, {', '.join(bounds)}:" if bounds else "Log:"


def hashed(keys: Iterable[str]) -> str:
    return ", ".join(f"#{key}" for key in keys)


def remember(folder: Path, question: str, answer: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    return records.create(folder, records.slug(question), f"{question.strip()}\n\n{answer.strip()}")
