from __future__ import annotations

from dataclasses import dataclass, field

from toodles.models import Node, Progress, normalize_title
from toodles.parse import link_github_children, normalize_alias_map


@dataclass
class MatchGap:
    title: str
    ado_id: str = ""
    github_url: str = ""
    github_number: str = ""
    reason: str = ""


@dataclass
class ProjectReport:
    goals: list[Node]
    unmapped_epics: list[Node] = field(default_factory=list)
    orphan_tasks: list[Node] = field(default_factory=list)
    ado_without_github: list[MatchGap] = field(default_factory=list)
    github_without_ado: list[MatchGap] = field(default_factory=list)
    matched_epics: int = 0

    def overall_progress(self) -> Progress:
        result = Progress()
        for goal in self.goals:
            result.merge(goal.progress())
        return result


def _github_epic_index(items: dict[str, Node]) -> dict[str, Node]:
    index: dict[str, Node] = {}
    for node in items.values():
        if node.kind != "Epic":
            continue
        index[normalize_title(node.title)] = node
    return index


def _candidate_github_titles(ado_epic: Node, aliases: dict[str, list[str]]) -> list[str]:
    ado_title = normalize_title(ado_epic.title)
    titles: list[str] = []
    seen: set[str] = set()
    for title in aliases.get(ado_title, []):
        if title and title not in seen:
            seen.add(title)
            titles.append(title)
    if ado_title and ado_title not in seen:
        titles.append(ado_title)
    return titles


def _resolve_github_epics(
    ado_epic: Node,
    gh_epics: dict[str, Node],
    aliases: dict[str, list[str]],
) -> list[Node]:
    matches: list[Node] = []
    seen: set[str] = set()
    for title in _candidate_github_titles(ado_epic, aliases):
        gh_epic = gh_epics.get(title)
        if gh_epic is None or gh_epic.key in seen:
            continue
        seen.add(gh_epic.key)
        matches.append(gh_epic)
    return matches


def _github_links_for(matches: list[Node]) -> list[tuple[str, str]]:
    links: list[tuple[str, str]] = []
    seen: set[str] = set()
    for match in matches:
        key = match.github_url or match.github_number
        if not key or key in seen:
            continue
        seen.add(key)
        links.append((match.github_number, match.github_url))
    return links


def _attach_github_epics(epic: Node, matches: list[Node], claimed: set[str]) -> int:
    available = [match for match in matches if match.key not in claimed]
    if not available:
        return 0
    epic.matched = True
    epic.github_links = _github_links_for(available)
    if len(available) == 1:
        gh_epic = available[0]
        epic.github_url = gh_epic.github_url
        epic.github_status = gh_epic.github_status
        epic.github_number = gh_epic.github_number
        epic.closed_at = gh_epic.closed_at
        epic.updated_at = gh_epic.updated_at
        epic.children = gh_epic.children
    else:
        epic.children = available
    for match in available:
        _mark_subtree(match, claimed)
    return len(available)


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
    aliases: dict[str, str] | dict[str, list[str]] | None = None,
    goal_order: list[str] | None = None,
) -> ProjectReport:
    aliases = normalize_alias_map(aliases)
    link_github_children(github_items)
    gh_epics = _github_epic_index(github_items)
    matched_github_keys: set[str] = set()
    matched_count = 0
    ado_without_github: list[MatchGap] = []

    for goal in ado_goals:
        for epic in goal.children:
            matches = _resolve_github_epics(epic, gh_epics, aliases)
            attached = _attach_github_epics(epic, matches, matched_github_keys)
            if not attached:
                ado_without_github.append(
                    MatchGap(
                        title=epic.title,
                        ado_id=epic.ado_id,
                        reason="No GitHub epic with the same title or alias",
                    )
                )
                continue
            matched_count += attached

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

    unmapped_epics.sort(key=lambda item: item.title.casefold())
    orphan_tasks.sort(key=lambda item: item.title.casefold())
    return ProjectReport(
        goals=sort_goals(ado_goals, goal_order),
        unmapped_epics=unmapped_epics,
        orphan_tasks=orphan_tasks,
        ado_without_github=ado_without_github,
        github_without_ado=github_without_ado,
        matched_epics=matched_count,
    )
