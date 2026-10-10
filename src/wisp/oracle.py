from __future__ import annotations

import json
import os
import re
import urllib.request
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from wisp import apple, records
from wisp.records import Created, Record

BUDGET = 12_000
APPLE_BUDGET = 6_000
TIMEOUT = 120
MAX_TOKENS = 600
DEFAULT_DATA = "~/Library/Application Support/wisp"
THINKING = re.compile(r"<think>.*?</think>", re.DOTALL)

SYSTEM = (
    "You answer questions about a person's own one-line work log. "
    "Today is {today}. The log is below the question, newest line first, "
    "each line as `YYYY-MM-DD HH:MM  text`. Answer from the log only, briefly, "
    "in the language of the question, as plain text without headings."
)


@dataclass(frozen=True)
class Server:
    url: str = ""
    model: str = ""
    key: str = ""
    apple: bool = False


APPLE = Server(apple=True)
CHECKED = {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Answer:
    path: Path
    question: str
    answer: str
    created: datetime


Post = Callable[[Server, dict], dict]
OnText = Callable[[str], None]
UNCLOSED_THINKING = re.compile(r"<think>.*\Z", re.DOTALL)


def server(env: Mapping[str, str]) -> Server | None:
    if env.get("oracle_apple", "").strip().lower() in CHECKED:
        return APPLE
    url = env.get("oracle_url", "").strip().rstrip("/")
    if not url:
        return None
    return Server(url, env.get("oracle_model", "").strip(), env.get("oracle_key", "").strip())


def answers_folder(env: Mapping[str, str]) -> Path:
    data = env.get("alfred_workflow_data") or os.path.expanduser(DEFAULT_DATA)
    return Path(data) / "answers"


def line(record: Record) -> str:
    return f"{record.created:%Y-%m-%d %H:%M}  {record.text}"


def evidence(logs: Iterable[Record], budget: int = BUDGET) -> str:
    kept: list[str] = []
    size = 0
    for text in map(line, sorted(logs, key=records.newest_first)):
        size += len(text) + 1
        if size > budget and kept:
            break
        kept.append(text)
    return "\n".join(kept)


def prompt(
    question: str, logs: Iterable[Record], now: datetime, budget: int = BUDGET
) -> list[dict]:
    return [
        {"role": "system", "content": SYSTEM.format(today=f"{now:%A %Y-%m-%d}")},
        {"role": "user", "content": f"{question}\n\nLog:\n{evidence(logs, budget)}"},
    ]


def payload(server: Server, messages: list[dict]) -> dict:
    body = {
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": MAX_TOKENS,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    if server.model:
        body["model"] = server.model
    return body


def post(server: Server, body: dict) -> dict:
    headers = {"Content-Type": "application/json"}
    if server.key:
        headers["Authorization"] = f"Bearer {server.key}"
    request = urllib.request.Request(
        f"{server.url}/v1/chat/completions", json.dumps(body).encode(), headers, method="POST"
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return json.loads(response.read())


def answer_text(response: dict) -> str:
    return visible(response["choices"][0]["message"]["content"])


def visible(text: str) -> str:
    return UNCLOSED_THINKING.sub("", THINKING.sub("", text)).strip()


def budget_for(server: Server) -> int:
    return APPLE_BUDGET if server.apple else BUDGET


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


def stream(server: Server, body: dict, on_text: OnText | None) -> str:
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


def answer(server: Server, messages: list[dict], on_text: OnText | None, data: str) -> str:
    if server.apple:
        return apple.respond(messages, data)
    return visible(stream(server, payload(server, messages), on_text))


def ask(question: str, logs: Iterable[Record], now: datetime, server: Server, post: Post) -> str:
    return answer_text(post(server, payload(server, prompt(question, logs, now))))


def remember(folder: Path, question: str, answer: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = records.free_path(folder, records.slug(question))
    path.write_text(f"{question.strip()}\n\n{answer.strip()}\n", encoding="utf-8")
    return path


def read_answers(folder: Path, created: Created) -> list[Answer]:
    return [as_answer(record) for record in records.read_folder(folder, created)]


def as_answer(record: Record) -> Answer:
    content = record.path.read_text(encoding="utf-8")
    return Answer(record.path, record.text, records.body(content), record.created)
