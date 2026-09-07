from __future__ import annotations

import argparse
import tempfile
import unittest
from pathlib import Path

from toodles.cli import resolve_aliases, unused_alias_files


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


if __name__ == "__main__":
    unittest.main()
