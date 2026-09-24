from __future__ import annotations

import unittest
from datetime import date
from pathlib import Path

from toodles.briefing import generate_briefing
from toodles.merge import ProjectReport, merge_project
from toodles.models import Node
from toodles.parse import parse_ado_csv, parse_github_tsv
from toodles.report_html import render_html

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _report():
    return merge_project(parse_ado_csv(FIXTURES / "ado.csv"), parse_github_tsv(FIXTURES / "github.tsv"))


def _dated_report() -> ProjectReport:
    epic = Node(
        key="e",
        kind="Epic",
        title="Epic",
        children=[
            Node(key="t-new", kind="Task", title="New task", created_at="2026-09-23T10:00:00Z"),
            Node(
                key="t-closed",
                kind="Task",
                title="Closed task",
                created_at="2026-09-01T10:00:00Z",
                closed_at="2026-09-22T12:00:00Z",
                github_status="Closed",
            ),
            Node(key="t-older", kind="Task", title="Older open", created_at="2026-09-12T08:00:00Z"),
        ],
    )
    goal = Node(key="g", kind="Goal", title="Goal", children=[epic])
    return ProjectReport(goals=[goal])


class BriefingTests(unittest.TestCase):
    def test_facts_use_task_timestamps_not_files(self) -> None:
        facts = generate_briefing(_dated_report(), as_of=date(2026, 9, 24))
        self.assertIn("In the last 5 working days, 1 new tasks have been opened and 1 tasks have been closed.", facts)
        self.assertIn("In the last 15 working days, 2 new tasks have been opened and 1 tasks have been closed.", facts)
        self.assertNotIn(".tsv", facts)
        self.assertNotIn("Overall GitHub work items closed:", facts)

    def test_html_briefing_is_collapsed_by_default(self) -> None:
        html = render_html(
            _report(),
            briefing="- In the last 5 working days, 2 new tasks have been opened and 5 tasks have been closed.",
        )
        self.assertIn('<details class="briefing">', html)
        self.assertNotIn('<details class="briefing" open>', html)
        self.assertIn("Status summary", html)
        self.assertNotIn("briefing-meta", html)
        self.assertIn("2 new tasks have been opened", html)
        self.assertIn('class="activity-chart"', html)

    def test_html_chart_uses_task_days(self) -> None:
        html = render_html(
            _dated_report(),
            briefing="- In the last 5 working days, 1 new tasks have been opened and 1 tasks have been closed.",
            as_of=date(2026, 9, 24),
        )
        self.assertIn('class="activity-chart"', html)
        self.assertIn("01 Sep: 1 open", html)
        self.assertIn("24 Sep: 2 open", html)
        self.assertIn("Cumulative opened vs closed", html)
        self.assertIn("Open tickets", html)
        self.assertIn('class="open-line"', html)
        self.assertIn('class="activity-charts"', html)
        self.assertIn("Last 5 working days", html)

    def test_html_omits_briefing_when_empty(self) -> None:
        html = render_html(_report())
        self.assertNotIn('class="briefing"', html)


if __name__ == "__main__":
    unittest.main()
