from __future__ import annotations

import argparse
import tempfile
import unittest
from pathlib import Path

from toodles.cli import resolve_aliases, resolve_inputs, unused_alias_files


def _args(aliases: Path | None = None) -> argparse.Namespace:
    return argparse.Namespace(aliases=aliases)


class AliasDiscoveryTests(unittest.TestCase):
    def test_prefers_aliases_json_over_multi_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            folder = cwd / "input"
            folder.mkdir()
            (folder / "aliases-multi.json").write_text("{}", encoding="utf-8")
            (folder / "aliases.json").write_text("{}", encoding="utf-8")
            chosen = resolve_aliases(_args(), cwd)
            self.assertEqual(chosen, folder / "aliases.json")
            leftover = unused_alias_files(chosen, cwd)
            self.assertEqual([path.name for path in leftover], ["aliases-multi.json"])

    def test_loads_aliases_multi_json_when_aliases_json_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            folder = cwd / "input"
            folder.mkdir()
            multi = folder / "aliases-multi.json"
            multi.write_text("{}", encoding="utf-8")
            chosen = resolve_aliases(_args(), cwd)
            self.assertEqual(chosen, multi)

    def test_loads_aliasses_typo_filename(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            folder = cwd / "input"
            folder.mkdir()
            typo = folder / "aliasses-multi.json"
            typo.write_text("{}", encoding="utf-8")
            chosen = resolve_aliases(_args(), cwd)
            self.assertEqual(chosen, typo)

    def test_explicit_aliases_path_wins(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            folder = cwd / "input"
            folder.mkdir()
            (folder / "aliases.json").write_text("{}", encoding="utf-8")
            other = folder / "aliases-multi.json"
            other.write_text("{}", encoding="utf-8")
            chosen = resolve_aliases(_args(other), cwd)
            self.assertEqual(chosen, other)


class GithubDiscoveryTests(unittest.TestCase):
    def test_auto_github_picks_highest_trailing_number_on_same_date(self) -> None:
        import os
        from datetime import datetime

        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            folder = cwd / "input"
            folder.mkdir()
            (folder / "roadmap.csv").write_text("x", encoding="utf-8")
            same = datetime(2026, 9, 24, 12, 15).timestamp()
            for name in ("PM view (1).tsv", "PM view (9).tsv", "PM view (10).tsv"):
                path = folder / name
                path.write_text("x", encoding="utf-8")
                os.utime(path, (same, same))
            args = argparse.Namespace(ado=None, github=None)
            _ado, github = resolve_inputs(args, cwd)
            self.assertEqual(github.name, "PM view (10).tsv")

    def test_explicit_github_uses_that_file_only(self) -> None:
        import os
        from datetime import datetime

        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            folder = cwd / "input"
            folder.mkdir()
            (folder / "roadmap.csv").write_text("x", encoding="utf-8")
            same = datetime(2026, 9, 24, 12, 15).timestamp()
            first = folder / "PM view (1).tsv"
            for name in ("PM view (1).tsv", "PM view (2).tsv"):
                path = folder / name
                path.write_text("x", encoding="utf-8")
                os.utime(path, (same, same))
            args = argparse.Namespace(ado=None, github=first)
            _ado, github = resolve_inputs(args, cwd)
            self.assertEqual(github, first)


if __name__ == "__main__":
    unittest.main()
