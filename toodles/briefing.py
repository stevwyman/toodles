from __future__ import annotations

from datetime import date

from toodles.history import activity_briefing
from toodles.merge import ProjectReport


def generate_briefing(report: ProjectReport, as_of: date | None = None) -> str:
    """Briefing from each task's Created and Closed timestamps."""
    return activity_briefing(report.work_items(), as_of)
