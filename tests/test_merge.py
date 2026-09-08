from __future__ import annotations

import unittest
from pathlib import Path

from toodles.merge import merge_project
from toodles.models import Node, normalize_title
from toodles.parse import load_aliases, load_goal_order, normalize_alias_map, parse_ado_csv, parse_github_tsv
from toodles.report_html import _sorted_epics, render_html

FIXTURES = Path(__file__).resolve().parent / "fixtures"
ADO = FIXTURES / "ado.csv"
GITHUB = FIXTURES / "github.tsv"


class MergeTests(unittest.TestCase):
    def test_ado_groups_epics_under_goals(self) -> None:
        goals = parse_ado_csv(ADO)
        self.assertEqual(len(goals), 3)
        self.assertEqual(goals[0].title, "[QA] Platform can be installed")
        self.assertEqual(
            [epic.title for epic in goals[0].children],
            ["[QA] Load balancer is ready"],
        )
        self.assertEqual(len(goals[2].children), 4)

    def test_report_uses_manual_goal_order(self) -> None:
        order = load_goal_order(FIXTURES / "goal-order.json")
        report = merge_project(parse_ado_csv(ADO), parse_github_tsv(GITHUB), goal_order=order)
        self.assertEqual(
            [goal.ado_id for goal in report.goals],
            ["1001", "1003", "1002"],
        )
        self.assertEqual([goal.source_order for goal in report.goals], [1, 2, 3])

    def test_unlisted_goals_keep_csv_order_at_the_end(self) -> None:
        report = merge_project(
            parse_ado_csv(ADO),
            parse_github_tsv(GITHUB),
            goal_order=["1001", "1002"],
        )
        self.assertEqual(
            [goal.ado_id for goal in report.goals],
            ["1001", "1002", "1003"],
        )

    def test_github_parent_links_build_a_tree(self) -> None:
        report = merge_project(parse_ado_csv(ADO), parse_github_tsv(GITHUB))
        designs = next(
            epic for goal in report.goals for epic in goal.children if "High-level designs" in epic.title
        )
        self.assertEqual(designs.github_number, "19")
        self.assertEqual(len(designs.children), 2)
        network = next(child for child in designs.children if child.github_number == "71")
        self.assertTrue(any(child.github_number == "42" for child in network.children))

    def test_merge_matches_shared_epic_titles(self) -> None:
        report = merge_project(parse_ado_csv(ADO), parse_github_tsv(GITHUB))
        self.assertGreaterEqual(report.matched_epics, 4)
        access = next(epic for goal in report.goals for epic in goal.children if epic.title == "Team access granted")
        self.assertEqual(access.github_number, "17")
        titles = {child.title for child in access.children}
        self.assertIn("Grant portal access", titles)

    def test_aliases_can_match_renamed_epics(self) -> None:
        aliases = load_aliases(FIXTURES / "aliases.json")
        self.assertEqual(
            aliases[normalize_title("Network prerequisites for production")],
            [normalize_title("[prod] Network infrastructure is ready")],
        )
        report = merge_project(parse_ado_csv(ADO), parse_github_tsv(GITHUB), aliases)
        network = next(
            epic
            for goal in report.goals
            for epic in goal.children
            if "Network prerequisites" in epic.title
        )
        self.assertTrue(network.matched)
        self.assertEqual(network.github_number, "3")
        self.assertTrue(any(child.github_number == "14" for child in network.children))

    def test_aliases_can_map_many_github_epics_to_one_ado_epic(self) -> None:
        aliases = load_aliases(FIXTURES / "aliases-multi.json")
        report = merge_project(parse_ado_csv(ADO), parse_github_tsv(GITHUB), aliases)
        network = next(
            epic
            for goal in report.goals
            for epic in goal.children
            if "Network prerequisites" in epic.title
        )
        self.assertTrue(network.matched)
        self.assertEqual(
            [child.title for child in network.children],
            ["[prod] Network infrastructure is ready", "DNS zones ready"],
        )
        self.assertEqual(
            {item.github_number for item in network.work_items()},
            {"14", "81"},
        )
        self.assertFalse(any(epic.github_number == "80" for epic in report.unmapped_epics))
        overlay = next(
            epic
            for goal in report.goals
            for epic in goal.children
            if epic.title == "Overlay components configured"
        )
        self.assertFalse(overlay.matched)
        self.assertTrue(any(gap.ado_id == "1304" for gap in report.ado_without_github))

    def test_alias_values_must_be_titles(self) -> None:
        with self.assertRaises(ValueError):
            normalize_alias_map({"An ADO epic": 12})
        with self.assertRaises(ValueError):
            normalize_alias_map({"An ADO epic": ["GitHub epic", 3]})

    def test_matched_epic_uses_csv_state_not_github_status(self) -> None:
        report = merge_project(parse_ado_csv(ADO), parse_github_tsv(GITHUB))
        designs = next(
            epic
            for goal in report.goals
            for epic in goal.children
            if "High-level designs" in epic.title
        )
        self.assertEqual(designs.ado_state, "Active")
        self.assertEqual(designs.display_status, "Active")
        self.assertEqual(designs.github_status, "")
        html = render_html(report)
        snippet = html[html.index("High-level designs complete") :][:400]
        self.assertIn(">Active</span>", snippet)
        self.assertNotIn(">In Progress</span>", snippet)

    def test_html_sorts_epics_by_workflow_status(self) -> None:
        nodes = [
            Node(key="c", kind="Epic", title="Closed one", github_status="Closed"),
            Node(key="n", kind="Epic", title="New one", ado_state="New"),
            Node(key="a", kind="Epic", title="Active one", ado_state="Active"),
            Node(key="r", kind="Epic", title="Ready one", github_status="Ready"),
            Node(key="x", kind="Epic", title="Analyse one", github_status="Needs Refinement"),
            Node(key="s", kind="Epic", title="Resolved one", ado_state="Resolved"),
        ]
        self.assertEqual(
            [node.title for node in _sorted_epics(nodes)],
            [
                "New one",
                "Analyse one",
                "Ready one",
                "Active one",
                "Resolved one",
                "Closed one",
            ],
        )

    def test_html_goals_are_collapsible(self) -> None:
        html = render_html(merge_project(parse_ado_csv(ADO), parse_github_tsv(GITHUB)))
        self.assertIn('class="goal-fold"', html)
        self.assertIn("<article class=\"goal\"", html)
        self.assertGreater(html.count("<details class=\"epic\""), 3)


if __name__ == "__main__":
    unittest.main()
