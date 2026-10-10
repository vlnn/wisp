from datetime import datetime, timedelta
from pathlib import Path

import pytest

from wisp import records

NOW = datetime(2026, 10, 10, 15, 0)

LINES = (
    "making API v1",
    "testing api manually",
    "autotests",
    "reading docs",
    "meeting with L",
)


@pytest.fixture
def folder(tmp_path):
    return tmp_path / "log"


@pytest.fixture
def stamps():
    return {}


@pytest.fixture
def created(stamps):
    return lambda path: stamps[path.name]


@pytest.fixture
def touched():
    return {}


@pytest.fixture
def changed(stamps, touched):
    return lambda path: touched.get(path.name, stamps[path.name])


@pytest.fixture
def logged(folder, stamps):
    def log(text, minutes_ago):
        path = records.keep(folder, text)
        stamps[path.name] = NOW - timedelta(minutes=minutes_ago)
        return path

    return log


@pytest.fixture
def sample(logged):
    return [logged(text, minutes_ago) for minutes_ago, text in zip((50, 40, 30, 20, 10), LINES)]


def names(folder: Path):
    return sorted(p.name for p in folder.iterdir())
