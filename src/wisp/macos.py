from __future__ import annotations

import subprocess
from pathlib import Path

TITLE = "Wisp"


def trash(path: Path) -> None:
    script = f'tell application "Finder" to delete POSIX file "{applescript_string(str(path))}"'
    subprocess.run(["osascript", "-e", script], check=True, capture_output=True)


def copy(text: str) -> None:
    subprocess.run(["pbcopy"], input=text, text=True, check=True)


def open(path: Path) -> None:
    subprocess.run(["open", str(path)], check=True)


def notify(text: str) -> None:
    script = f'display notification "{applescript_string(text)}" with title "{TITLE}"'
    try:
        subprocess.run(["osascript", "-e", script], check=False, capture_output=True)
    except FileNotFoundError:
        pass


def applescript_string(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')
