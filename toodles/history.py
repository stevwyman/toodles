from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from toodles.models import Node

TRAILING_NUMBER = re.compile(r"\((\d+)\)\s*$")
ACTIVITY_WINDOWS = ((5, "5 working days"), (15, "15 working days"))


def parse_item_date(value: str) -> date | None:
    """Parse a GitHub Created/Closed timestamp to a calendar date."""
    text = (value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None


def is_working_day(day: date) -> bool:
    return day.weekday() < 5


def working_window_start(as_of: date, weekdays: int) -> date:
    """Oldest weekday in the last `weekdays` working days, ending on `as_of`."""
    remaining = weekdays
    cursor = as_of
    oldest = as_of
    for _ in range(400):
        if remaining <= 0:
            break
        if is_working_day(cursor):
            remaining -= 1
            oldest = cursor
        cursor -= timedelta(days=1)
    return oldest


@dataclass(frozen=True)
class TaskActivity:
    opened: int
    closed: int
    days: int
    label: str


@dataclass(frozen=True)
class DayActivity:
    day: date
    opened: int
    closed: int

    @property
    def delta(self) -> int:
        return self.opened - self.closed


def count_task_activity(items: list[Node], as_of: date, weekdays: int) -> TaskActivity:
    """Opened/closed in the last `weekdays` working days, using task timestamps."""
    start = working_window_start(as_of, weekdays)
    opened = 0
    closed = 0
    for item in items:
        if item.kind not in {"Task", "Bug", "Issue"}:
            continue
        created = parse_item_date(item.created_at)
        if created is not None and start <= created <= as_of:
            opened += 1
        finished = parse_item_date(item.closed_at)
        if finished is not None and start <= finished <= as_of:
            closed += 1
    label = next((name for span, name in ACTIVITY_WINDOWS if span == weekdays), f"{weekdays} working days")
    return TaskActivity(opened=opened, closed=closed, days=weekdays, label=label)


def daily_activity(items: list[Node], as_of: date, days: int | None = None) -> list[DayActivity]:
    """Per-day opened/closed counts. `days` limits the window; omit it for the full project."""
    counts: dict[date, list[int]] = {}
    for item in items:
        if item.kind not in {"Task", "Bug", "Issue"}:
            continue
        created = parse_item_date(item.created_at)
        finished = parse_item_date(item.closed_at)
        if created is not None and created <= as_of:
            counts.setdefault(created, [0, 0])[0] += 1
        if finished is not None and finished <= as_of:
            counts.setdefault(finished, [0, 0])[1] += 1
    if days is not None:
        window_start = as_of - timedelta(days=days)
        ordered = [window_start + timedelta(days=offset) for offset in range(1, days + 1)]
    elif not counts:
        return []
    else:
        cursor = min(counts)
        ordered = []
        while cursor <= as_of:
            ordered.append(cursor)
            cursor += timedelta(days=1)
    return [
        DayActivity(day=day, opened=counts.get(day, [0, 0])[0], closed=counts.get(day, [0, 0])[1])
        for day in ordered
    ]


def activity_briefing(items: list[Node], as_of: date | None = None) -> str:
    """Two window lines: last 5 working days, then last 15 working days."""
    as_of = as_of or date.today()
    bullets = []
    for weekdays, _label in ACTIVITY_WINDOWS:
        activity = count_task_activity(items, as_of, weekdays)
        bullets.append(
            f"- In the last {activity.label}, {activity.opened} new tasks have been opened "
            f"and {activity.closed} tasks have been closed."
        )
    return "\n".join(bullets)


def trailing_export_number(path: Path) -> int:
    """`(12)` at the end of the filename, otherwise 0."""
    match = TRAILING_NUMBER.search(path.stem)
    return int(match.group(1)) if match else 0


def export_file_date(path: Path) -> date:
    return datetime.fromtimestamp(path.stat().st_mtime).date()


def export_sort_key(path: Path) -> tuple:
    """Oldest first: file date, then trailing (n), then name."""
    return (export_file_date(path), trailing_export_number(path), path.name.casefold())


def discover_github_export(cwd: Path) -> Path | None:
    """The current GitHub TSV: newest file date, then highest trailing (n)."""
    matches: list[Path] = []
    seen: set[Path] = set()
    for folder in (cwd / "input", cwd):
        if not folder.is_dir():
            continue
        for path in folder.glob("*.tsv"):
            resolved = path.resolve()
            if resolved in seen or not path.is_file():
                continue
            seen.add(resolved)
            matches.append(path)
    if not matches:
        return None
    return max(matches, key=export_sort_key)
