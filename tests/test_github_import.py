from __future__ import annotations

import argparse
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from toodles.cli import resolve_inputs
from toodles.github_import import convert_rows, github_token, load_env_file, write_tsv
from toodles.parse import parse_github_tsv


def _item(
    *,
    title: str,
    url: str,
    typename: str = "Issue",
    issue_type: str = "Task",
    status: str = "In Progress",
    parent: str = "",
    created: str = "2026-09-01T10:00:00Z",
    closed: str = "",
    sub_closed: int = 0,
    sub_total: int = 0,
    effort: int | None = None,
) -> dict:
    field_nodes = [
        {"name": status, "field": {"name": "Status"}},
    ]
    if effort is not None:
        field_nodes.append({"number": effort, "field": {"name": "Effort"}})
    children = [{"state": "CLOSED"}] * sub_closed + [{"state": "OPEN"}] * max(sub_total - sub_closed, 0)
    return {
        "content": {
            "__typename": typename,
            "title": title,
            "url": url,
            "createdAt": created,
            "updatedAt": created,
            "closedAt": closed or None,
            "issueType": {"name": issue_type} if issue_type else None,
            "parent": {"url": parent} if parent else None,
            "subIssues": {"totalCount": sub_total, "nodes": children} if sub_total else None,
        },
        "fieldValues": {"nodes": field_nodes},
    }


class ConvertRowsTests(unittest.TestCase):
    def test_maps_issue_and_project_fields(self) -> None:
        rows = convert_rows(
            [
                _item(
                    title="Parent epic",
                    url="https://github.com/example/tracker/issues/3",
                    issue_type="Epic",
                    status="Needs Refinement",
                    sub_closed=1,
                    sub_total=2,
                ),
                _item(
                    title="Child task",
                    url="https://github.com/example/tracker/issues/14",
                    parent="https://github.com/example/tracker/issues/3",
                    effort=0,
                ),
                {"content": None, "fieldValues": {"nodes": []}},
            ]
        )
        self.assertEqual(len(rows), 2)
        epic, task = rows
        self.assertEqual(epic["Type"], "Epic")
        self.assertEqual(epic["Status"], "Needs Refinement")
        self.assertEqual(epic["Sub-issues progress"], "1 / 2 (50%)")
        self.assertEqual(task["Parent issue"], "https://github.com/example/tracker/issues/3")
        self.assertEqual(task["Effort"], "0")

    def test_written_tsv_parses_like_a_manual_export(self) -> None:
        rows = convert_rows(
            [
                _item(
                    title="Network config",
                    url="https://github.com/example/tracker/issues/14",
                    closed="2026-09-22T12:00:00Z",
                    status="Closed",
                )
            ]
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "my-projects.tsv"
            write_tsv(rows, path)
            items = parse_github_tsv(path)
        node = items["https://github.com/example/tracker/issues/14"]
        self.assertEqual(node.kind, "Task")
        self.assertEqual(node.github_status, "Closed")
        self.assertEqual(node.closed_at, "2026-09-22T12:00:00Z")


class EnvTests(unittest.TestCase):
    def test_token_prefers_github_token(self) -> None:
        with patch.dict(os.environ, {"GITHUB_TOKEN": "from-actions", "TOODLES_GITHUB_TOKEN": "other"}, clear=False):
            self.assertEqual(github_token(), "from-actions")

    def test_token_falls_back_to_toodles_secret_name(self) -> None:
        env = {key: value for key, value in os.environ.items() if key != "GITHUB_TOKEN"}
        env["TOODLES_GITHUB_TOKEN"] = "from-secret"
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(github_token(), "from-secret")

    def test_env_file_does_not_override_existing_vars(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text('GITHUB_ORG=from-file\nGITHUB_TOKEN="file-token"\n', encoding="utf-8")
            env = {
                key: value
                for key, value in os.environ.items()
                if key not in {"GITHUB_ORG", "TOODLES_GITHUB_ORG"}
            }
            env["GITHUB_TOKEN"] = "already-set"
            with patch.dict(os.environ, env, clear=True):
                load_env_file(path)
                self.assertEqual(os.environ["GITHUB_TOKEN"], "already-set")
                self.assertEqual(os.environ.get("GITHUB_ORG"), "from-file")


class CliImportTests(unittest.TestCase):
    def test_import_uses_written_tsv(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            folder = cwd / "input"
            folder.mkdir()
            (folder / "roadmap.csv").write_text("x", encoding="utf-8")
            written = folder / "my-projects.tsv"
            args = argparse.Namespace(
                ado=None,
                github=None,
                do_import=True,
                no_import=False,
                github_org="acme",
                github_project="Board",
                github_project_number=None,
                import_output=None,
            )
            with patch("toodles.cli.import_project", return_value=written) as mocked:
                _ado, github = resolve_inputs(args, cwd)
            self.assertEqual(github, written)
            mocked.assert_called_once()
            self.assertEqual(mocked.call_args.kwargs["org"], "acme")
            self.assertEqual(mocked.call_args.kwargs["project"], "Board")
            self.assertEqual(mocked.call_args.kwargs["output"], cwd / "input" / "my-projects.tsv")

    def test_explicit_github_file_skips_import(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            folder = cwd / "input"
            folder.mkdir()
            (folder / "roadmap.csv").write_text("x", encoding="utf-8")
            existing = folder / "hand-export.tsv"
            existing.write_text("x", encoding="utf-8")
            args = argparse.Namespace(
                ado=None,
                github=existing,
                do_import=False,
                no_import=False,
                github_org="acme",
                github_project="Board",
                github_project_number=None,
                import_output=None,
            )
            with patch("toodles.cli.import_project") as mocked:
                _ado, github = resolve_inputs(args, cwd)
            self.assertEqual(github, existing)
            mocked.assert_not_called()


if __name__ == "__main__":
    unittest.main()
