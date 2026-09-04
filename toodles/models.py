from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable


DONE_STATUSES = {"closed", "resolved", "done", "completed"}
NOISE_TITLE_MARKERS = (
    "dependency dashboard",
    "mend configuration",
    "github-azdo-sync",
    "azdo->github-sync",
    "vulnerabilities",
    "autoclosed",
)


def normalize_title(title: str) -> str:
    return " ".join((title or "").casefold().split())


def environment_from_title(title: str) -> str:
    upper = (title or "").upper()
    has_qa = any(token in upper for token in ("HWQA", "[QA]"))
    has_prod = any(token in upper for token in ("HWPROD", "HW-PROD", "HW PROD", "[PROD]"))
    if has_qa and has_prod:
        return "Shared"
    if "HWQA" in upper:
        return "HWQA"
    if has_qa:
        return "QA"
    if any(token in upper for token in ("HWPROD", "HW-PROD", "HW PROD")):
        return "HWPROD"
    if has_prod:
        return "PROD"
    return "Other"


def status_bucket(status: str | None) -> str:
    value = (status or "").strip().casefold()
    if not value:
        return "unknown"
    if value in DONE_STATUSES:
        return "done"
    if value in {"in progress", "active"}:
        return "progress"
    if value in {"in review"}:
        return "review"
    if value in {"waiting", "blocked"}:
        return "waiting"
    if value in {"ready", "planned", "needs refinement", "new", "to do", "todo"}:
        return "todo"
    return "todo"


def is_done(status: str | None, closed_at: str | None = None) -> bool:
    if status_bucket(status) == "done":
        return True
    return bool((closed_at or "").strip())


def looks_like_noise(kind: str, title: str) -> bool:
    lowered = (title or "").casefold()
    if any(marker in lowered for marker in NOISE_TITLE_MARKERS):
        return True
    return kind in {"", "Issue"} and "sync test" in lowered


@dataclass
class Progress:
    total: int = 0
    done: int = 0
    by_bucket: dict[str, int] = field(default_factory=dict)

    @property
    def percent(self) -> float:
        if self.total == 0:
            return 0.0
        return 100.0 * self.done / self.total

    def add(self, bucket: str, done: bool) -> None:
        self.total += 1
        if done:
            self.done += 1
        self.by_bucket[bucket] = self.by_bucket.get(bucket, 0) + 1

    def merge(self, other: "Progress") -> None:
        self.total += other.total
        self.done += other.done
        for key, value in other.by_bucket.items():
            self.by_bucket[key] = self.by_bucket.get(key, 0) + value


@dataclass
class Node:
    """A node in the Goal → Epic → Task → Task tree."""

    key: str
    kind: str
    title: str
    environment: str = "Other"
    ado_id: str = ""
    ado_state: str = ""
    ado_assignee: str = ""
    ado_tags: str = ""
    github_url: str = ""
    github_status: str = ""
    github_number: str = ""
    closed_at: str = ""
    updated_at: str = ""
    parent_url: str = ""
    matched: bool = False
    noise: bool = False
    source_order: int = 0
    children: list["Node"] = field(default_factory=list)

    @property
    def display_status(self) -> str:
        if self.github_status:
            return self.github_status
        if self.ado_state:
            return self.ado_state
        if self.closed_at:
            return "Closed"
        return ""

    @property
    def bucket(self) -> str:
        return status_bucket(self.display_status)

    def walk(self, seen: set[str] | None = None) -> Iterable["Node"]:
        seen = seen if seen is not None else set()
        if self.key in seen:
            return
        seen.add(self.key)
        yield self
        for child in self.children:
            yield from child.walk(seen)

    def work_items(self, include_self: bool = False) -> list["Node"]:
        items: list[Node] = []
        for node in self.walk():
            if node is self and not include_self:
                continue
            if node.noise:
                continue
            if node.kind in {"Task", "Bug", "Issue"}:
                items.append(node)
        return items

    def progress(self) -> Progress:
        result = Progress()
        for item in self.work_items():
            result.add(item.bucket, is_done(item.display_status, item.closed_at))
        return result
