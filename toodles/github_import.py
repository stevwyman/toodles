from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

GITHUB_GRAPHQL_URL = "https://api.github.com/graphql"
DEFAULT_TSV = Path("input") / "my-projects.tsv"
TSV_COLUMNS = [
    "Type",
    "Title",
    "URL",
    "Status",
    "Parent issue",
    "Sub-issues progress",
    "Created",
    "Updated",
    "Closed",
    "Start date",
    "Priority",
    "Target date",
    "Effort",
]
FIELD_MAP = {
    "Status": "Status",
    "Priority": "Priority",
    "Target date": "Target date",
    "Start date": "Start date",
    "Effort": "Effort",
    "Parent issue": "Parent issue",
    "Sub-issues progress": "Sub-issues progress",
    "Type": "Type",
    "Issue Type": "Type",
}

PROJECT_BY_NUMBER = """
query($org: String!, $number: Int!) {
  organization(login: $org) {
    projectV2(number: $number) {
      id
      title
    }
  }
}
"""

PROJECTS_PAGE = """
query($org: String!, $cursor: String) {
  organization(login: $org) {
    projectsV2(first: 50, after: $cursor) {
      pageInfo { hasNextPage endCursor }
      nodes { id title number }
    }
  }
}
"""

PROJECT_ITEMS = """
query($projectId: ID!, $cursor: String) {
  node(id: $projectId) {
    ... on ProjectV2 {
      items(first: 100, after: $cursor) {
        pageInfo { hasNextPage endCursor }
        nodes {
          content {
            __typename
            ... on Issue {
              title
              number
              url
              state
              createdAt
              updatedAt
              closedAt
              issueType { name }
              parent { number title url }
              subIssues(first: 100) {
                totalCount
                nodes { state }
              }
            }
          }
          fieldValues(first: 50) {
            nodes {
              ... on ProjectV2ItemFieldTextValue {
                text
                field { ... on ProjectV2FieldCommon { name } }
              }
              ... on ProjectV2ItemFieldSingleSelectValue {
                name
                field { ... on ProjectV2FieldCommon { name } }
              }
              ... on ProjectV2ItemFieldNumberValue {
                number
                field { ... on ProjectV2FieldCommon { name } }
              }
              ... on ProjectV2ItemFieldDateValue {
                date
                field { ... on ProjectV2FieldCommon { name } }
              }
              ... on ProjectV2ItemFieldIterationValue {
                title
                field { ... on ProjectV2FieldCommon { name } }
              }
            }
          }
        }
      }
    }
  }
}
"""


def github_token() -> str:
    """Token from the process environment. GitHub Actions should pass a repo secret as GITHUB_TOKEN."""
    return (
        os.environ.get("GITHUB_TOKEN") or os.environ.get("TOODLES_GITHUB_TOKEN") or ""
    ).strip()


def env_org() -> str:
    return (os.environ.get("GITHUB_ORG") or os.environ.get("TOODLES_GITHUB_ORG") or "").strip()


def env_project() -> str:
    return (os.environ.get("GITHUB_PROJECT") or os.environ.get("TOODLES_GITHUB_PROJECT") or "").strip()


def env_project_number() -> int | None:
    raw = (
        os.environ.get("GITHUB_PROJECT_NUMBER")
        or os.environ.get("TOODLES_GITHUB_PROJECT_NUMBER")
        or ""
    ).strip()
    return int(raw) if raw.isdigit() else None


def load_env_file(path: Path) -> None:
    """Load KEY=value pairs without overwriting variables already in the environment."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = value


def graphql_query(token: str, query: str, variables: dict | None = None) -> dict:
    payload = json.dumps({"query": query, "variables": variables or {}}).encode("utf-8")
    request = urllib.request.Request(
        GITHUB_GRAPHQL_URL,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "toodles",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub GraphQL HTTP {exc.code}: {detail[:400]}") from exc
    if data.get("errors"):
        raise RuntimeError(json.dumps(data["errors"], indent=2))
    return data["data"]


def find_project(token: str, org: str, project_name: str = "", project_number: int | None = None) -> str:
    """Return the ProjectV2 id for an organization project."""
    if project_number is not None:
        data = graphql_query(token, PROJECT_BY_NUMBER, {"org": org, "number": project_number})
        org_data = (data or {}).get("organization") or {}
        project = org_data.get("projectV2")
        if not project:
            raise ValueError(f"GitHub project #{project_number} was not found in org '{org}'.")
        title = project.get("title") or ""
        if project_name and title.casefold() != project_name.casefold():
            raise ValueError(
                f"GitHub project #{project_number} is titled '{title}', not '{project_name}'."
            )
        return project["id"]

    if not project_name:
        raise ValueError("Pass a GitHub project title or project number.")

    cursor = None
    while True:
        data = graphql_query(token, PROJECTS_PAGE, {"org": org, "cursor": cursor})
        org_data = (data or {}).get("organization")
        if org_data is None:
            raise ValueError(f"GitHub organization '{org}' was not found or is not visible to this token.")
        page = org_data["projectsV2"]
        for project in page["nodes"]:
            if (project.get("title") or "").casefold() == project_name.casefold():
                return project["id"]
        if not page["pageInfo"]["hasNextPage"]:
            break
        cursor = page["pageInfo"]["endCursor"]
    raise ValueError(f"Project '{project_name}' was not found in org '{org}'.")


def get_project_items(token: str, project_id: str) -> list[dict]:
    items: list[dict] = []
    cursor = None
    while True:
        data = graphql_query(token, PROJECT_ITEMS, {"projectId": project_id, "cursor": cursor})
        page = ((data or {}).get("node") or {}).get("items")
        if not page:
            raise ValueError("GitHub project items could not be read. Check project id and token scopes.")
        items.extend(page["nodes"])
        if not page["pageInfo"]["hasNextPage"]:
            break
        cursor = page["pageInfo"]["endCursor"]
    return items


def _field_value(field_value: dict) -> str:
    for key in ("text", "name", "number", "date", "title"):
        if key in field_value and field_value[key] is not None:
            return str(field_value[key])
    return ""


def convert_rows(items: list[dict]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for item in items:
        row = {column: "" for column in TSV_COLUMNS}
        for field_value in (item.get("fieldValues") or {}).get("nodes") or []:
            field = field_value.get("field") or {}
            mapped = FIELD_MAP.get(field.get("name") or "")
            if mapped:
                row[mapped] = _field_value(field_value)

        content = item.get("content") or {}
        title = content.get("title") or ""
        url = content.get("url") or ""
        if title:
            row["Title"] = title
        if url:
            row["URL"] = url
        if content.get("createdAt"):
            row["Created"] = content["createdAt"]
        if content.get("updatedAt"):
            row["Updated"] = content["updatedAt"]
        if content.get("closedAt"):
            row["Closed"] = content["closedAt"]

        issue_type = content.get("issueType") or {}
        if issue_type.get("name"):
            row["Type"] = issue_type["name"]
        elif not row["Type"] and content.get("__typename"):
            row["Type"] = content["__typename"]

        parent = content.get("parent") or {}
        if parent.get("url"):
            row["Parent issue"] = parent["url"]

        sub_issues = content.get("subIssues")
        if sub_issues:
            total = sub_issues.get("totalCount") or 0
            completed = sum(1 for child in sub_issues.get("nodes") or [] if child.get("state") == "CLOSED")
            percent = round(completed * 100 / total) if total else 0
            row["Sub-issues progress"] = f"{completed} / {total} ({percent}%)"

        if row["URL"] and row["Title"]:
            rows.append(row)
    return rows


def write_tsv(rows: list[dict[str, str]], output_file: Path) -> Path:
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=TSV_COLUMNS, delimiter="\t", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return output_file


def import_project(
    *,
    token: str,
    org: str,
    output: Path,
    project: str = "",
    project_number: int | None = None,
) -> Path:
    """Fetch a GitHub ProjectV2 board and write it as a TSV the report parser already understands."""
    if not token:
        raise RuntimeError("GITHUB_TOKEN not found in the environment or .env file")
    if not org:
        raise RuntimeError("GitHub org is missing. Pass --github-org or set GITHUB_ORG.")
    print("Locating GitHub project...", file=sys.stderr)
    project_id = find_project(token, org, project, project_number)
    print(f"Project ID: {project_id}", file=sys.stderr)
    print("Downloading items...", file=sys.stderr)
    items = get_project_items(token, project_id)
    rows = convert_rows(items)
    write_tsv(rows, output)
    print(f"Retrieved {len(items)} items · wrote {len(rows)} rows to {output}", file=sys.stderr)
    return output


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export a GitHub ProjectV2 board to a TSV.")
    parser.add_argument("--org", default="", help="GitHub organization login (or GITHUB_ORG)")
    parser.add_argument("--project", default="", help="GitHub project title (or GITHUB_PROJECT)")
    parser.add_argument(
        "--project-number",
        type=int,
        default=None,
        help="GitHub project number (or GITHUB_PROJECT_NUMBER)",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_TSV, help=f"TSV path (default: {DEFAULT_TSV})")
    return parser


def main(argv: list[str] | None = None) -> int:
    load_env_file(Path.cwd() / ".env")
    args = build_parser().parse_args(argv)
    import_project(
        token=github_token(),
        org=args.org or env_org(),
        project=args.project or env_project(),
        project_number=args.project_number if args.project_number is not None else env_project_number(),
        output=args.output,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
