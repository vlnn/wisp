from datetime import datetime

import pytest

from conftest import NOW
from wisp import present


@pytest.mark.parametrize(
    "created, expected",
    [
        (datetime(2026, 10, 10, 14, 2), "14:02 today"),
        (datetime(2026, 10, 10, 0, 0), "00:00 today"),
        (datetime(2026, 10, 9, 16, 0), "yesterday 16:00"),
        (datetime(2026, 10, 8, 9, 5), "Thu 8 Oct 09:05"),
        (datetime(2026, 1, 1, 9, 5), "Thu 1 Jan 09:05"),
        (datetime(2025, 12, 31, 23, 59), "31 Dec 2025 23:59"),
        (datetime(2026, 10, 11, 1, 0), "11 Oct 2026 01:00"),
    ],
)
def test_when(created, expected):
    assert present.when(created, NOW) == expected, (
        f"{created} seen at {NOW} should read {expected!r}"
    )
