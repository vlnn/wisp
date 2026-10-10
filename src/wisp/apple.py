from __future__ import annotations

import subprocess
from pathlib import Path

SOURCE = Path(__file__).with_name("apple.swift")
NAME = "wisp-apple"
TIMEOUT = 180
TOOLS_MISSING = "Compiling the Apple helper needs the Command Line Tools: xcode-select --install"


class AppleError(Exception):
    pass


def is_apple(url: str) -> bool:
    return url.strip().lower() == "apple"


def binary(data: Path | str) -> Path:
    return Path(data) / "bin" / NAME


def compile_command(target: Path) -> list[str]:
    return ["swiftc", "-O", "-parse-as-library", "-o", str(target), str(SOURCE)]


def stale(target: Path) -> bool:
    return not target.exists() or target.stat().st_mtime < SOURCE.stat().st_mtime


def respond(messages: list[dict], data: Path | str) -> str:
    target = binary(data)
    if stale(target):
        build(target)
    instructions = "\n".join(m["content"] for m in messages if m["role"] == "system")
    prompt = "\n".join(m["content"] for m in messages if m["role"] != "system")
    return run([str(target), instructions], prompt).strip()


def build(target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    run(compile_command(target), "")


def run(argv: list[str], stdin: str) -> str:
    try:
        done = subprocess.run(
            argv, input=stdin, capture_output=True, text=True, check=True, timeout=TIMEOUT
        )
    except FileNotFoundError:
        raise AppleError(TOOLS_MISSING) from None
    except subprocess.CalledProcessError as error:
        raise AppleError(error.stderr.strip() or f"{argv[0]} failed") from None
    except subprocess.TimeoutExpired:
        raise AppleError("The Apple model did not answer in time") from None
    return done.stdout
