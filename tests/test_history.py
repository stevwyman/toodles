from __future__ import annotations

import os
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

from toodles.history import (
    activity_briefing,
    count_task_activity,
    daily_activity,
    discover_github_export,
    trailing_export_number,
    working_window_start,
)
from toodles.models import Node


def _touch(path: Path, when: datetime) -> Path:
    path.write_text("Title\tURL\n", encoding="utf-8")
    stamp = when.timestamp()
    os.utime(path, (stamp, stamp))
    return path


class CurrentExportTests(unittest.TestCase):
    def test_trailing_number_is_an_integer(self) -> None:
        self.assertEqual(trailing_export_number(Path("PM view (9).tsv")), 9)
        self.assertEqual(trailing_export_number(Path("PM view (10).tsv")), 10)
        self.assertEqual(trailing_export_number(Path("test.tsv")), 0)

    def test_discovers_highest_trailing_number_on_the_same_date(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            folder = cwd / "input"
            folder.mkdir()
            same = datetime(2026, 9, 24, 12, 15)
            _touch(folder / "PM view (10).tsv", same)
            _touch(folder / "PM view (9).tsv", same)
            _touch(folder / "PM view (11).tsv", same)
            chosen = discover_github_export(cwd)
            self.assertEqual(chosen.name, "PM view (11).tsv")

    def test_newer_file_date_wins_over_trailing_number(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            folder = cwd / "input"
            folder.mkdir()
            _touch(folder / "older (99).tsv", datetime(2026, 9, 16, 8, 0))
            _touch(folder / "newer (1).tsv", datetime(2026, 9, 24, 12, 0))
            chosen = discover_github_export(cwd)
            self.assertEqual(chosen.name, "newer (1).tsv")


class TaskActivityTests(unittest.TestCase):
    def test_windows_use_created_and_closed_timestamps(self) -> None:
        items = [
            Node(key="1", kind="Task", title="opened yesterday", created_at="2026-09-23T10:00:00Z"),
            Node(
                key="2",
                kind="Task",
                title="closed yesterday",
                created_at="2026-08-01T10:00:00Z",
                closed_at="2026-09-22T12:00:00Z",
                github_status="Closed",
            ),
            Node(key="3", kind="Task", title="opened ten days ago", created_at="2026-09-14T08:00:00Z"),
            Node(
                key="4",
                kind="Task",
                title="closed last month",
                created_at="2026-08-01T10:00:00Z",
                closed_at="2026-08-15T12:00:00Z",
                github_status="Closed",
            ),
            Node(key="5", kind="Epic", title="ignore epics", created_at="2026-09-23T10:00:00Z"),
        ]
        as_of = date(2026, 9, 24)
        self.assertEqual(working_window_start(as_of, 5), date(2026, 9, 18))
        self.assertEqual(working_window_start(as_of, 15), date(2026, 9, 4))
        five = count_task_activity(items, as_of, 5)
        fifteen = count_task_activity(items, as_of, 15)
        self.assertEqual((five.opened, five.closed), (1, 1))
        self.assertEqual((fifteen.opened, fifteen.closed), (2, 1))
        text = activity_briefing(items, as_of)
        self.assertIn(
            "In the last 5 working days, 1 new tasks have been opened and 1 tasks have been closed.",
            text,
        )
        self.assertIn(
            "In the last 15 working days, 2 new tasks have been opened and 1 tasks have been closed.",
            text,
        )

    def test_working_window_skips_weekends_but_counts_weekend_events(self) -> None:
        items = [
            Node(key="1", kind="Task", title="friday start", created_at="2026-09-18T10:00:00Z"),
            Node(key="2", kind="Task", title="thursday before window", created_at="2026-09-17T10:00:00Z"),
            Node(key="3", kind="Task", title="saturday in span", created_at="2026-09-19T10:00:00Z"),
        ]
        five = count_task_activity(items, date(2026, 9, 24), 5)
        self.assertEqual((five.opened, five.closed), (2, 0))

    def test_daily_activity_buckets_opened_and_closed(self) -> None:
        items = [
            Node(key="1", kind="Task", title="opened", created_at="2026-09-23T10:00:00Z"),
            Node(
                key="2",
                kind="Task",
                title="closed",
                created_at="2026-08-01T10:00:00Z",
                closed_at="2026-09-22T12:00:00Z",
                github_status="Closed",
            ),
        ]
        series = daily_activity(items, date(2026, 9, 24), days=3)
        self.assertEqual([day.day for day in series], [date(2026, 9, 22), date(2026, 9, 23), date(2026, 9, 24)])
        self.assertEqual([(day.opened, day.closed) for day in series], [(0, 1), (1, 0), (0, 0)])
        self.assertEqual([day.delta for day in series], [-1, 1, 0])

    def test_full_project_series_starts_at_first_task_date(self) -> None:
        items = [
            Node(key="1", kind="Task", title="opened", created_at="2026-09-01T10:00:00Z"),
            Node(
                key="2",
                kind="Task",
                title="closed",
                created_at="2026-09-01T10:00:00Z",
                closed_at="2026-09-10T12:00:00Z",
                github_status="Closed",
            ),
        ]
        series = daily_activity(items, date(2026, 9, 12))
        self.assertEqual(series[0].day, date(2026, 9, 1))
        self.assertEqual(series[-1].day, date(2026, 9, 12))
        self.assertEqual(series[0].opened, 2)
        self.assertEqual(series[9].closed, 1)
        running = 0
        opens = []
        for day in series:
            running += day.delta
            opens.append(running)
        self.assertEqual(opens[0], 2)
        self.assertEqual(opens[9], 1)
        self.assertEqual(opens[-1], 1)


if __name__ == "__main__":
    unittest.main()
