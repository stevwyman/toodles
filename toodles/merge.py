from __future__ import annotations

from dataclasses import dataclass, field

from toodles.models import Node, Progress, environment_from_title, normalize_title
from toodles.parse import link_github_children


@dataclass
class MatchGap:
    title: str
    ado_id: str = ""
    github_url: str = ""
    github_number: str = ""
    environment: str = "Other"
    reason: str = ""


@dataclass
class ProjectReport:
    goals: list[Node]
    unmapped_epics: list[Node] = field(default_factory=list)
    orphan_tasks: list[Node] = field(default_factory=list)
    ado_without_github: list[MatchGap] = field(default_factory=list)
    github_without_ado: list[MatchGap] = field(default_factory=list)
    matched_epics: int = 0

    def environments(self) -> list[str]:
        seen: list[str] = []
        for goal in self.goals:
            if goal.environment not in seen:
                seen.append(goal.environment)
        if self.unmapped_epics or self.orphan_tasks:
            if "Unmapped" not in seen:
                seen.append("Unmapped")
        return seen

    def summary_environments(self) -> list[str]:
        return [env for env in self.environments() if env != "Unmapped"]

    def goals_for(self, environment: str | None) -> list[Node]:
        if environment in (None, "All"):
            return self.goals
        return [goal for goal in self.goals if goal.environment == environment]

    def overall_progress(self, environment: str | None = None) -> Progress:
        result = Progress()
        for goal in self.goals_for(environment):
            result.merge(goal.progress())
        return result


def _github_epic_index(items: dict[str, Node]) -> dict[str, Node]:
    index: dict[str, Node] = {}
    for node in items.values():
        if node.kind != "Epic":
            continue
        index[normalize_title(node.title)] = node
    return index


def _resolve_github_epic(
    ado_epic: Node,
    gh_epics: dict[str, Node],
    aliases: dict[str, str],
) -> Node | None:
    ado_title = normalize_title(ado_epic.title)
    aliased = aliases.get(ado_title, ado_title)
    return gh_epics.get(aliased) or gh_epics.get(ado_title)


def sort_goals(goals: list[Node], ordered_ids: list[str] | None = None) -> list[Node]:
    """Apply a manual Azure DevOps ID order. Unlisted goals keep CSV order at the end."""
    if ordered_ids:
        rank = {item_id: index for index, item_id in enumerate(ordered_ids)}
        listed = [goal for goal in goals if goal.ado_id in rank]
        rest = [goal for goal in goals if goal.ado_id not in rank]
        listed.sort(key=lambda goal: rank[goal.ado_id])
        ordered = listed + rest
    else:
        ordered = list(goals)
    for index, goal in enumerate(ordered, start=1):
        goal.source_order = index
    return ordered


def _mark_subtree(node: Node, seen: set[str]) -> None:
    seen.add(node.key)
    for child in node.children:
        _mark_subtree(child, seen)


def merge_project(
    ado_goals: list[Node],
    github_items: dict[str, Node],
    aliases: dict[str, str] | None = None,
    goal_order: list[str] | None = None,
) -> ProjectReport:
    aliases = aliases or {}
    link_github_children(github_items)
    gh_epics = _github_epic_index(github_items)
    matched_github_keys: set[str] = set()
    matched_count = 0
    ado_without_github: list[MatchGap] = []

    for goal in ado_goals:
        for epic in goal.children:
            gh_epic = _resolve_github_epic(epic, gh_epics, aliases)
            if gh_epic is None:
                ado_without_github.append(
                    MatchGap(
                        title=epic.title,
                        ado_id=epic.ado_id,
                        environment=epic.environment or goal.environment,
                        reason="No GitHub epic with the same title",
                    )
                )
                continue
            matched_count += 1
            epic.matched = True
            epic.github_url = gh_epic.github_url
            epic.github_status = gh_epic.github_status
            epic.github_number = gh_epic.github_number
            epic.closed_at = gh_epic.closed_at
            epic.updated_at = gh_epic.updated_at
            epic.children = gh_epic.children
            if epic.environment == "Other":
                epic.environment = environment_from_title(gh_epic.title) or goal.environment
            _mark_subtree(gh_epic, matched_github_keys)

    unmapped_epics: list[Node] = []
    github_without_ado: list[MatchGap] = []
    for node in github_items.values():
        if node.kind != "Epic" or node.key in matched_github_keys:
            continue
        unmapped_epics.append(node)
        github_without_ado.append(
            MatchGap(
                title=node.title,
                github_url=node.github_url,
                github_number=node.github_number,
                environment=node.environment,
                reason="GitHub epic is not listed under any Azure DevOps goal",
            )
        )
        _mark_subtree(node, matched_github_keys)

    orphan_tasks: list[Node] = []
    for node in github_items.values():
        if node.key in matched_github_keys or node.noise:
            continue
        if node.parent_url and node.parent_url in github_items:
            continue
        if node.kind in {"Task", "Bug", "Issue"}:
            orphan_tasks.append(node)
            _mark_subtree(node, matched_github_keys)

    unmapped_epics.sort(key=lambda item: (item.environment, item.title.casefold()))
    orphan_tasks.sort(key=lambda item: (item.environment, item.title.casefold()))
    return ProjectReport(
        goals=sort_goals(ado_goals, goal_order),
        unmapped_epics=unmapped_epics,
        orphan_tasks=orphan_tasks,
        ado_without_github=ado_without_github,
        github_without_ado=github_without_ado,
        matched_epics=matched_count,
    )
