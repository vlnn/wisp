import pytest

from wisp import search


@pytest.mark.parametrize(
    "query, text, hit",
    [
        ("making v1", "making API v1", True),
        ("api", "making API v1", True),
        ("api", "testing api manually", True),
        ("api", "autotests", False),
        ("v1", "making API v1", True),
        ("v1", "making API v10", True),
        ("v2", "making API v1", False),
        ("l", "meeting with L", True),
        ("meeting l", "meeting with L", True),
        ("docs reading", "reading docs", True),
        ("", "anything", True),
        ("   ", "anything", True),
        ("réunion", "Reunion", True),
        ("reunion", "Réunion", True),
        ("ДОКИ", "читаю доки", True),
        ("make", "making API v1", False),
    ],
)
def test_matches(query, text, hit):
    assert search.matches(query, text) is hit, (
        f"{query!r} should {'match' if hit else 'not match'} {text!r}"
    )


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Making API v1", ["making", "api", "v1"]),
        ("get -R /remote/dir", ["get", "r", "remote", "dir"]),
        ("Crème Brûlée", ["creme", "brulee"]),
    ],
)
def test_words(text, expected):
    assert search.words(text) == expected, f"words of {text!r} should be {expected}"
