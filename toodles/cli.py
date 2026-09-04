from __future__ import annotations

import argparse
import sys
import webbrowser
from datetime import datetime, timezone
from pathlib import Path

from toodles.merge import merge_project
from toodles.parse import load_aliases, load_goal_order, parse_ado_csv, parse_github_tsv
from toodles.report_html import render_html, render_json, write_html
from toodles.report_text import render_markdown, render_text


def _newest(paths: list[Path]) -> Path | None:
    if not paths:
        return None
    return max(paths, key=lambda path: path.stat().st_mtime)


def discover_export(cwd: Path, pattern: str) -> Path | None:
    matches: list[Path] = []
    for folder in (cwd / "input", cwd):
        if folder.is_dir():
            matches.extend(folder.glob(pattern))
    return _newest(matches)


def _optional_config(cwd: Path, explicit: Path | None, filename: str) -> Path | None:
    if explicit is not None:
        if not explicit.exists():
            raise SystemExit(f"File not found: {explicit}")
        return explicit
    for candidate in (cwd / "input" / filename, cwd / filename):
        if candidate.exists():
            return candidate
    return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Merge an Azure DevOps goal/epic CSV with a GitHub epic/task TSV "
            "and print a Goal → Epic → Task status report."
        )
    )
    parser.add_argument("--ado", type=Path, help="Azure DevOps CSV export (goals with epics listed below each goal)")
    parser.add_argument("--github", type=Path, help="GitHub TSV export of epics, tasks and parent links")
    parser.add_argument(
        "--aliases",
        type=Path,
        help="Optional JSON file mapping Azure DevOps epic titles to GitHub epic titles "
        "(default: input/aliases.json or aliases.json if present)",
    )
    parser.add_argument(
        "--goal-order",
        type=Path,
        help="JSON array of Azure DevOps goal IDs in report order "
        "(default: input/goal-order.json or goal-order.json if present)",
    )
    parser.add_argument(
        "--format",
        choices=("html", "markdown", "text", "json"),
        default="html",
        help="Report format (default: html)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        help="Output file. Defaults to output/project-status.html (or stdout for text formats if omitted with --stdout)",
    )
    parser.add_argument("--stdout", action="store_true", help="Write the report to stdout instead of a file")
    parser.add_argument("--open", action="store_true", help="Open the HTML report in a browser after writing")
    return parser


def resolve_inputs(args: argparse.Namespace, cwd: Path) -> tuple[Path, Path]:
    ado = args.ado or discover_export(cwd, "*.csv")
    github = args.github or discover_export(cwd, "*.tsv")
    if ado is None:
        raise SystemExit("No Azure DevOps CSV found. Pass --ado PATH.")
    if github is None:
        raise SystemExit("No GitHub TSV found. Pass --github PATH.")
    if not ado.exists():
        raise SystemExit(f"Azure DevOps file not found: {ado}")
    if not github.exists():
        raise SystemExit(f"GitHub file not found: {github}")
    return ado, github


def resolve_goal_order(args: argparse.Namespace, cwd: Path) -> Path | None:
    return _optional_config(cwd, args.goal_order, "goal-order.json")


def resolve_aliases(args: argparse.Namespace, cwd: Path) -> Path | None:
    return _optional_config(cwd, args.aliases, "aliases.json")


def default_output(fmt: str) -> Path:
    suffix = {"html": ".html", "markdown": ".md", "text": ".txt", "json": ".json"}[fmt]
    return Path("output") / f"project-status{suffix}"


def render_report(report, fmt: str) -> str:
    if fmt == "html":
        return render_html(report, datetime.now(timezone.utc))
    if fmt == "markdown":
        return render_markdown(report)
    if fmt == "json":
        return render_json(report)
    return render_text(report)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cwd = Path.cwd()
    ado_path, github_path = resolve_inputs(args, cwd)
    aliases = load_aliases(resolve_aliases(args, cwd))
    goal_order = load_goal_order(resolve_goal_order(args, cwd))
    report = merge_project(
        parse_ado_csv(ado_path),
        parse_github_tsv(github_path),
        aliases,
        goal_order,
    )
    body = render_report(report, args.format)

    if args.stdout:
        sys.stdout.write(body)
        return 0

    output = args.output or default_output(args.format)
    if args.format == "html":
        write_html(report, output)
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(body, encoding="utf-8")

    print(f"Wrote {output}", file=sys.stderr)
    print(
        f"Matched {report.matched_epics} epics · "
        f"{len(report.ado_without_github)} ADO-only · "
        f"{len(report.github_without_ado)} GitHub-only",
        file=sys.stderr,
    )
    if args.open:
        webbrowser.open(output.resolve().as_uri())
    return 0
