from __future__ import annotations

import csv
import json
import re
from pathlib import Path

from toodles.models import Node, environment_from_title, looks_like_noise, normalize_title

ISSUE_NUMBER_RE = re.compile(r"/issues/(\d+)(?:[?#]|$)")


def _open_text(path: Path):
    return path.open(encoding="utf-8-sig", newline="")


def issue_number(url: str) -> str:
    match = ISSUE_NUMBER_RE.search(url or "")
    return match.group(1) if match else ""


def load_aliases(path: Path | None) -> dict[str, str]:
    if path is None:
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    aliases: dict[str, str] = {}
    if not isinstance(raw, dict):
        raise ValueError("Alias file must be a JSON object of ADO title → GitHub title")
    for source, target in raw.items():
        aliases[normalize_title(str(source))] = normalize_title(str(target))
    return aliases


def load_goal_order(path: Path | None) -> list[str]:
    """Load a JSON array of Azure DevOps goal IDs in the desired report order."""
    if path is None:
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("Goal order file must be a JSON array of Azure DevOps IDs")
    return [str(item).strip() for item in raw if str(item).strip()]


def parse_ado_csv(path: Path) -> list[Node]:
    """Parse an Azure DevOps CSV where each Goal is followed by its child Epics."""
    goals: list[Node] = []
    current_goal: Node | None = None

    with _open_text(path) as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError(f"No header row found in {path}")
        for row in reader:
            kind = (row.get("Work Item Type") or "").strip()
            title = (row.get("Title") or "").strip()
            item_id = (row.get("ID") or "").strip()
            if not title:
                continue
            if kind == "Goal":
                current_goal = Node(
                    key=f"ado:{item_id}",
                    kind="Goal",
                    title=title,
                    environment=environment_from_title(title),
                    ado_id=item_id,
                    ado_state=(row.get("State") or "").strip(),
                    ado_assignee=(row.get("Assigned To") or "").strip(),
                    ado_tags=(row.get("Tags") or "").strip(),
                )
                goals.append(current_goal)
                continue
            if kind != "Epic":
                continue
            epic = Node(
                key=f"ado:{item_id}",
                kind="Epic",
                title=title,
                environment=environment_from_title(title) if current_goal is None else (current_goal.environment),
                ado_id=item_id,
                ado_state=(row.get("State") or "").strip(),
                ado_assignee=(row.get("Assigned To") or "").strip(),
                ado_tags=(row.get("Tags") or "").strip(),
            )
            if current_goal is None:
                current_goal = Node(
                    key="ado:unassigned",
                    kind="Goal",
                    title="Unassigned epics",
                    environment="Other",
                )
                goals.append(current_goal)
            if epic.environment == "Other":
                epic.environment = current_goal.environment
            current_goal.children.append(epic)
    return goals


def parse_github_tsv(path: Path) -> dict[str, Node]:
    """Parse a GitHub project TSV into a URL-indexed map of issues."""
    items: dict[str, Node] = {}
    with _open_text(path) as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if not reader.fieldnames:
            raise ValueError(f"No header row found in {path}")
        for row in reader:
            url = (row.get("URL") or "").strip()
            title = (row.get("Title") or "").strip()
            if not url or not title:
                continue
            kind_raw = (row.get("Type") or "").strip()
            status = (row.get("Status") or "").strip()
            closed = (row.get("Closed") or "").strip()
            parent = (row.get("Parent issue") or "").strip()
            noise = looks_like_noise(kind_raw, title)
            if kind_raw in {"Epic", "Task", "Bug"}:
                kind = kind_raw
            elif noise:
                kind = "Issue"
            else:
                kind = "Task"
            node = Node(
                key=url,
                kind=kind,
                title=title,
                environment=environment_from_title(title),
                github_url=url,
                github_status=status or ("Closed" if closed else ""),
                github_number=issue_number(url),
                closed_at=closed,
                updated_at=(row.get("Updated") or "").strip(),
                parent_url=parent,
                noise=noise,
            )
            items[url] = node
    return items


def _creates_cycle(parent: Node, child: Node) -> bool:
    return any(node.key == parent.key for node in child.walk())


def link_github_children(items: dict[str, Node]) -> None:
    """Attach child issues using the Parent issue column. Detects cycles."""
    for node in items.values():
        parent = items.get(node.parent_url) if node.parent_url else None
        if parent is None or node in parent.children or _creates_cycle(parent, node):
            continue
        parent.children.append(node)
