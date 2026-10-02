from __future__ import annotations

import argparse
import sys
import webbrowser
from datetime import datetime, timezone
from pathlib import Path

from toodles.briefing import generate_briefing
from toodles.github_import import (
    DEFAULT_TSV,
    env_org,
    env_project,
    env_project_number,
    github_token,
    import_project,
    load_env_file,
)
from toodles.history import discover_github_export
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


def _alias_candidates(cwd: Path) -> list[Path]:
    """Find alias JSON files. Prefer aliases.json, then other *alias*.json names."""
    found: list[Path] = []
    seen: set[Path] = set()
    for folder in (cwd / "input", cwd):
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob("*alias*.json")):
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            found.append(path)
    exact = [path for path in found if path.name == "aliases.json"]
    rest = [path for path in found if path.name != "aliases.json"]
    return exact + rest


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
        help="Optional JSON file mapping Azure DevOps epic titles to one GitHub title "
        "or a list of GitHub titles (default: input/aliases.json, aliases-multi.json, "
        "or another *alias*.json if present)",
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
    parser.add_argument(
        "--no-summary",
        action="store_true",
        help="Skip the folded status summary and charts",
    )
    parser.add_argument(
        "--import",
        dest="do_import",
        action="store_true",
        help="Fetch the GitHub project via the API, write input/my-projects.tsv, then build the report",
    )
    parser.add_argument(
        "--no-import",
        action="store_true",
        help="Skip the GitHub API import and use an existing TSV",
    )
    parser.add_argument("--github-org", default="", help="GitHub organization login (or GITHUB_ORG)")
    parser.add_argument("--github-project", default="", help="GitHub project title (or GITHUB_PROJECT)")
    parser.add_argument(
        "--github-project-number",
        type=int,
        default=None,
        help="GitHub project number (or GITHUB_PROJECT_NUMBER)",
    )
    parser.add_argument(
        "--import-output",
        type=Path,
        default=None,
        help=f"Where to write the imported TSV (default: {DEFAULT_TSV})",
    )
    return parser


def resolve_import(args: argparse.Namespace, cwd: Path) -> Path | None:
    """Import the GitHub project when asked, or when token + org + project are in the environment."""
    if getattr(args, "no_import", False):
        return None
    token = github_token()
    org = getattr(args, "github_org", "") or env_org()
    project = getattr(args, "github_project", "") or env_project()
    number = getattr(args, "github_project_number", None)
    if number is None:
        number = env_project_number()
    output = getattr(args, "import_output", None) or (cwd / DEFAULT_TSV)
    if not output.is_absolute():
        output = cwd / output
    should_import = getattr(args, "do_import", False) or (
        token and org and (project or number is not None) and getattr(args, "github", None) is None
    )
    if not should_import:
        return None
    try:
        return import_project(token=token, org=org, project=project, project_number=number, output=output)
    except (RuntimeError, ValueError, OSError) as exc:
        raise SystemExit(str(exc)) from exc


def resolve_inputs(args: argparse.Namespace, cwd: Path) -> tuple[Path, Path]:
    ado = args.ado or discover_export(cwd, "*.csv")
    if ado is None:
        raise SystemExit("No Azure DevOps CSV found. Pass --ado PATH.")
    if not ado.exists():
        raise SystemExit(f"Azure DevOps file not found: {ado}")
    imported = resolve_import(args, cwd)
    if imported is not None:
        github = imported
    elif args.github is not None:
        github = args.github
        if not github.exists():
            raise SystemExit(f"GitHub file not found: {github}")
    else:
        github = discover_github_export(cwd)
        if github is None:
            raise SystemExit(
                "No GitHub TSV found. Pass --github PATH, or --import with GITHUB_TOKEN / GITHUB_ORG."
            )
    return ado, github


def resolve_goal_order(args: argparse.Namespace, cwd: Path) -> Path | None:
    return _optional_config(cwd, args.goal_order, "goal-order.json")


def resolve_aliases(args: argparse.Namespace, cwd: Path) -> Path | None:
    if args.aliases is not None:
        if not args.aliases.exists():
            raise SystemExit(f"File not found: {args.aliases}")
        return args.aliases
    candidates = _alias_candidates(cwd)
    return candidates[0] if candidates else None


def unused_alias_files(chosen: Path | None, cwd: Path) -> list[Path]:
    if chosen is None:
        return []
    chosen_resolved = chosen.resolve()
    return [path for path in _alias_candidates(cwd) if path.resolve() != chosen_resolved]


def default_output(fmt: str) -> Path:
    suffix = {"html": ".html", "markdown": ".md", "text": ".txt", "json": ".json"}[fmt]
    return Path("output") / f"project-status{suffix}"


def render_report(report, fmt: str, briefing: str | None = None) -> str:
    if fmt == "html":
        return render_html(report, datetime.now(timezone.utc), briefing)
    if fmt == "markdown":
        return render_markdown(report)
    if fmt == "json":
        return render_json(report)
    return render_text(report)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.do_import and args.no_import:
        raise SystemExit("Use either --import or --no-import, not both.")
    cwd = Path.cwd()
    load_env_file(cwd / ".env")
    ado_path, github_path = resolve_inputs(args, cwd)
    aliases_path = resolve_aliases(args, cwd)
    aliases = load_aliases(aliases_path)
    goal_order = load_goal_order(resolve_goal_order(args, cwd))
    ado_goals = parse_ado_csv(ado_path)
    report = merge_project(
        ado_goals,
        parse_github_tsv(github_path),
        aliases,
        goal_order,
    )
    briefing = ""
    if args.format == "html" and not args.no_summary:
        briefing = generate_briefing(report)
    body = render_report(report, args.format, briefing)

    if args.stdout:
        sys.stdout.write(body)
        return 0

    output = args.output or default_output(args.format)
    if args.format == "html":
        write_html(report, output, briefing=briefing)
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(body, encoding="utf-8")

    print(f"Wrote {output}", file=sys.stderr)
    print(f"GitHub {github_path.name}", file=sys.stderr)
    if aliases_path is not None:
        print(f"Aliases {aliases_path}", file=sys.stderr)
        leftover = unused_alias_files(aliases_path, cwd)
        if leftover:
            names = ", ".join(str(path) for path in leftover)
            print(
                f"Note: not loading {names}. Pass --aliases PATH to use a different file.",
                file=sys.stderr,
            )
    else:
        print("Aliases none", file=sys.stderr)
    print(
        f"Matched {report.matched_epics} epics · "
        f"{len(report.ado_without_github)} ADO-only · "
        f"{len(report.github_without_ado)} GitHub-only",
        file=sys.stderr,
    )
    if args.open:
        webbrowser.open(output.resolve().as_uri())
    return 0
