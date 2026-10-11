from __future__ import annotations

import json
import os
import re
import shutil
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol, runtime_checkable

from wisp import apple, records, search
from wisp.records import Record

BUDGET = 12_000
APPLE_BUDGET = 6_000
TIMEOUT = 120
PROBE_TIMEOUT = 3
MAX_TOKENS = 600
DEFAULT_DATA = "~/Library/Application Support/wisp"
THINKING = re.compile(r"<think>.*?</think>", re.DOTALL)

SYSTEM = (
    "You answer questions about a person's own one-line work log. "
    "Today is {today}. The log is below the question, newest line first, "
    "each line as `YYYY-MM-DD HH:MM  text`. Some lines carry a word before the text: "
    "TODO is a task still open, DONE is a finished task (the time after DONE is when it "
    "was finished), QUESTION is a question still open, DECIDED is a question settled or a "
    "decision made (the time after DECIDED is when; ` | ` separates a question from its "
    "resolution), NOTE is something the person flagged as important. Lines without a word are "
    "plain log entries. Answer from the log only, briefly, "
    "in the language of the question, as plain text without headings."
)

STAMP = "%Y-%m-%d %H:%M"


CHECKED = {"1", "true", "yes", "on"}
OnText = Callable[[str], None]
UNCLOSED_THINKING = re.compile(r"<think>.*\Z", re.DOTALL)


class ModelError(Exception):
    pass


@dataclass(frozen=True)
class Llama:
    url: str
    model: str = ""
    key: str = ""
    budget: int = BUDGET

    def respond(self, messages: list[dict], on_text: OnText | None) -> str:
        try:
            return visible(stream(self, payload(self, messages), on_text))
        except urllib.error.HTTPError as error:
            raise ModelError(f"Model answered {error.code} at {self.url}") from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise ModelError(f"Model not reachable at {self.url}") from None

    def check(self) -> str:
        named = f" (model {self.model})" if self.model else ""
        return f"server {self.url}{named}: {'reachable' if self.reachable() else 'not reachable'}"

    def reachable(self) -> bool:
        request = urllib.request.Request(f"{self.url}/v1/models", headers=headers(self))
        try:
            with urllib.request.urlopen(request, timeout=PROBE_TIMEOUT):
                return True
        except (urllib.error.URLError, TimeoutError, OSError):
            return False


@dataclass(frozen=True)
class Apple:
    data: Path
    budget: int = APPLE_BUDGET

    def respond(self, messages: list[dict], on_text: OnText | None) -> str:
        try:
            return apple.respond(messages, self.data)
        except apple.AppleError as error:
            raise ModelError(str(error)) from None

    def check(self) -> str:
        if apple.binary(self.data).exists():
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
    if env.get("oracle_apple", "").strip().lower() in CHECKED:
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
    return f"{record.created:{STAMP}}  {tagged(record)}"


def tagged(record: Record) -> str:
    if record.kind in records.SETTLED:
        return f"{record.kind.tag} {record.changed:{STAMP}}  {record.line}"
    if record.kind.tag:
        return f"{record.kind.tag}  {record.line}"
    return record.text


@dataclass(frozen=True)
class Evidence:
    matching: list[Record]
    filling: list[Record]

    def records(self) -> list[Record]:
        return sorted(self.matching + self.filling, key=records.newest_first)

    def lines(self) -> list[str]:
        return [line(record) for record in self.records()]

    def text(self) -> str:
        return "\n".join(self.lines())


def evidence(question: str, logs: Iterable[Record], budget: int = BUDGET) -> Evidence:
    newest = sorted(logs, key=records.newest_first)
    matching = fit(singled_out(question, newest), budget)
    left = {record.path for record in matching}
    filling = fit((r for r in newest if r.path not in left), budget - size(matching))
    if not matching and not filling:
        filling = newest[:1]
    return Evidence(matching, filling)


def singled_out(question: str, logs: list[Record]) -> list[Record]:
    return search.search(question, logs) if search.query(question).words else []


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


def prompt(
    question: str, logs: Iterable[Record], now: datetime, budget: int = BUDGET
) -> list[dict]:
    return [
        {"role": "system", "content": SYSTEM.format(today=f"{now:%A %Y-%m-%d}")},
        {
            "role": "user",
            "content": f"{question}\n\nLog:\n{evidence(question, logs, budget).text()}",
        },
    ]


def payload(server: Llama, messages: list[dict]) -> dict:
    body = {
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": MAX_TOKENS,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    if server.model:
        body["model"] = server.model
    return body


def visible(text: str) -> str:
    return UNCLOSED_THINKING.sub("", THINKING.sub("", text)).strip()


def deltas(lines: Iterable[bytes]) -> Iterator[str]:
    for raw in lines:
        line = raw.decode("utf-8", "replace").strip()
        if not line.startswith("data:") or line == "data: [DONE]":
            continue
        try:
            delta = json.loads(line[5:])["choices"][0]["delta"].get("content")
        except (ValueError, KeyError, IndexError, TypeError):
            continue
        if delta:
            yield delta


def headers(server: Llama) -> dict[str, str]:
    sent = {"Content-Type": "application/json"}
    if server.key:
        sent["Authorization"] = f"Bearer {server.key}"
    return sent


def stream(server: Llama, body: dict, on_text: OnText | None) -> str:
    streaming = dict(body, stream=True)
    request = urllib.request.Request(
        f"{server.url}/v1/chat/completions",
        json.dumps(streaming).encode(),
        headers(server),
        method="POST",
    )
    text = ""
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        for delta in deltas(response):
            text += delta
            if on_text:
                on_text(text)
    return text


def remember(folder: Path, question: str, answer: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = records.free_path(folder, records.slug(question))
    path.write_text(f"{question.strip()}\n\n{answer.strip()}\n", encoding="utf-8")
    return path
