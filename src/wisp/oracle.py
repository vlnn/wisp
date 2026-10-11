from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Union

from wisp import apple, records
from wisp.records import Kind, Record

BUDGET = 12_000
APPLE_BUDGET = 6_000
TIMEOUT = 120
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

TAGS = {Kind.TASK: "TODO", Kind.NOTE: "NOTE", Kind.QUESTION: "QUESTION"}
SETTLED = {Kind.DONE: "DONE", Kind.DECISION: "DECIDED"}
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


@dataclass(frozen=True)
class Apple:
    data: Path
    budget: int = APPLE_BUDGET

    def respond(self, messages: list[dict], on_text: OnText | None) -> str:
        try:
            return apple.respond(messages, self.data)
        except apple.AppleError as error:
            raise ModelError(str(error)) from None


Backend = Union[Llama, Apple]


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
    if record.kind in SETTLED:
        return f"{SETTLED[record.kind]} {record.changed:{STAMP}}  {record.line}"
    if record.kind in TAGS:
        return f"{TAGS[record.kind]}  {record.line}"
    return record.text


def evidence_lines(logs: Iterable[Record], budget: int = BUDGET) -> list[str]:
    kept: list[str] = []
    size = 0
    for text in map(line, sorted(logs, key=records.newest_first)):
        size += len(text) + 1
        if size > budget and kept:
            break
        kept.append(text)
    return kept


def evidence(logs: Iterable[Record], budget: int = BUDGET) -> str:
    return "\n".join(evidence_lines(logs, budget))


def prompt(
    question: str, logs: Iterable[Record], now: datetime, budget: int = BUDGET
) -> list[dict]:
    return [
        {"role": "system", "content": SYSTEM.format(today=f"{now:%A %Y-%m-%d}")},
        {"role": "user", "content": f"{question}\n\nLog:\n{evidence(logs, budget)}"},
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


def stream(server: Llama, body: dict, on_text: OnText | None) -> str:
    headers = {"Content-Type": "application/json"}
    if server.key:
        headers["Authorization"] = f"Bearer {server.key}"
    streaming = dict(body, stream=True)
    request = urllib.request.Request(
        f"{server.url}/v1/chat/completions", json.dumps(streaming).encode(), headers, method="POST"
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
