from __future__ import annotations

from toodles.merge import ProjectReport
from toodles.models import Node, Progress


def _progress_line(progress: Progress) -> str:
    if progress.total == 0:
        return "no GitHub tasks"
    return f"{progress.done}/{progress.total} ({progress.percent:.0f}%)"


def _goal_progress(goal: Node) -> Progress:
    return goal.progress()


def render_markdown(report: ProjectReport) -> str:
    overall = report.overall_progress()
    lines = [
        "# Project status",
        "",
        f"Overall: **{_progress_line(overall)}** tasks closed · {report.matched_epics} epics matched across Azure DevOps and GitHub.",
        "",
        "Goals follow the manual order in goal-order.json.",
        "",
    ]
    for goal in report.goals:
        progress = _goal_progress(goal)
        lines.append(f"- **{goal.source_order}. {goal.title}**: {_progress_line(progress)}")
    lines.append("")

    for goal in report.goals:
        progress = _goal_progress(goal)
        lines += [
            f"## {goal.source_order}. {goal.title}",
            "",
            f"- ADO state: {goal.ado_state or 'n/a'} (`{goal.ado_id or '—'}`)",
            f"- Progress: {_progress_line(progress)}",
            "",
        ]
        if not goal.children:
            lines.append("_No epics listed under this goal._")
            lines.append("")
            continue
        for epic in goal.children:
            epic_progress = epic.progress()
            gh = "".join(
                f" · [#{number}]({url})" if url else f" · #{number}"
                for number, url in epic.github_refs()
                if number or url
            )
            lines.append(
                f"### {epic.title}{gh}"
            )
            lines.append(
                f"- Status: {epic.display_status or 'n/a'} · ADO {epic.ado_id or '—'} / {epic.ado_state or 'n/a'}"
            )
            lines.append(f"- Tasks: {_progress_line(epic_progress)}")
            lines.append("")
            _append_tasks(lines, epic.children, depth=0)
            lines.append("")
    if report.unmapped_epics or report.orphan_tasks:
        lines += ["## Unmapped GitHub work", ""]
        for epic in report.unmapped_epics:
            lines.append(f"- Epic: {epic.title} ({epic.display_status or 'no status'})")
        for task in report.orphan_tasks:
            lines.append(f"- {task.kind}: {task.title} ({task.display_status or 'no status'})")
        lines.append("")
    if report.ado_without_github:
        lines += ["## Azure DevOps epics without a GitHub match", ""]
        for gap in report.ado_without_github:
            lines.append(f"- {gap.title} (ADO {gap.ado_id})")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _append_tasks(lines: list[str], nodes: list[Node], depth: int) -> None:
    indent = "  " * depth
    for node in nodes:
        status = node.display_status or "no status"
        refs = [
            f"[#{number}]({url})" if url else f"#{number}"
            for number, url in node.github_refs()
            if number or url
        ]
        link = f" {refs[0]}" if len(refs) == 1 else ("" if not refs else " " + ", ".join(refs))
        prefix = "Epic: " if node.kind == "Epic" else ""
        lines.append(f"{indent}- [{status}] {prefix}{node.title}{link}")
        _append_tasks(lines, node.children, depth + 1)


def render_text(report: ProjectReport) -> str:
    overall = report.overall_progress()
    lines = [
        "Project status",
        "=" * 14,
        f"Overall {_progress_line(overall)} tasks closed",
        f"Matched epics: {report.matched_epics}",
        "Goals follow the manual order in goal-order.json",
        "",
    ]
    for goal in report.goals:
        progress = _goal_progress(goal)
        lines.append(f"{goal.source_order}. {goal.title}")
        lines.append(f"  ADO {goal.ado_id or '—'} · {goal.ado_state or 'n/a'} · {_progress_line(progress)}")
        for epic in goal.children:
            epic_progress = epic.progress()
            gh = "".join(
                f" GH#{number}" for number, _url in epic.github_refs() if number
            )
            lines.append(
                f"  - {epic.title} [{epic.display_status or 'n/a'}]{gh} {_progress_line(epic_progress)}"
            )
            _append_text_tasks(lines, epic.children, indent="      ")
        lines.append("")
    if report.ado_without_github:
        lines.append("ADO epics missing in GitHub:")
        for gap in report.ado_without_github:
            lines.append(f"  - {gap.title}")
        lines.append("")
    if report.github_without_ado:
        lines.append("GitHub epics missing from ADO goals:")
        for gap in report.github_without_ado:
            lines.append(f"  - {gap.title}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _append_text_tasks(lines: list[str], nodes: list[Node], indent: str) -> None:
    for node in nodes:
        status = node.display_status or "n/a"
        num = f" #{node.github_number}" if node.github_number else ""
        lines.append(f"{indent}{node.kind}{num} [{status}] {node.title}")
        _append_text_tasks(lines, node.children, indent + "  ")
