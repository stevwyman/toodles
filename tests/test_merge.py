from __future__ import annotations

import unittest
from pathlib import Path

from toodles.merge import merge_project
from toodles.parse import load_aliases, load_goal_order, parse_ado_csv, parse_github_tsv

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
        self.assertEqual(goals[2].environment, "QA")
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


if __name__ == "__main__":
    unittest.main()
