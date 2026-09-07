# Toodles

Merges two exports into one Goal → Epic → Task → Task view:

1. **Azure DevOps CSV** — high-level Goals, with their Epics listed directly underneath each Goal.
2. **GitHub TSV** — Epics and Tasks (including nested tasks) plus the parent-issue links.

Epics are the join key. The tool matches them by title across both systems, then hangs GitHub tasks (and sub-tasks) under the Azure DevOps goal they belong to.

## Input files

Put local exports in `input/` (this folder is gitignored):

```
input/
  roadmap.csv          # Azure DevOps export
  tracker.tsv          # GitHub export
  aliases.json         # optional title mapping
  goal-order.json      # optional goal ID order
```

```bash
python3 -m toodles
```

If you omit `--ado` / `--github`, the newest `*.csv` and `*.tsv` in `input/` (or the current directory) are used. `input/aliases.json` and `input/goal-order.json` are picked up automatically when present.

```bash
python3 -m toodles --format markdown -o output/status.md
python3 -m toodles --format text --stdout
python3 -m toodles --format json -o output/status.json
python3 -m toodles --open
```

## How matching works

- The CSV is read top to bottom: each `Goal` owns every following `Epic` until the next Goal.
- Goal order is **manual**: list Azure DevOps IDs from first to last in `goal-order.json`. Goals not listed stay at the end in CSV order.
- GitHub rows are linked with the `Parent issue` column, so tasks can sit under epics or under other tasks.
- An ADO epic is matched to GitHub epics when the titles are equal (case and whitespace insensitive), and/or when `aliases.json` maps them.
- One ADO epic can map to **several GitHub epics**. Their tasks all roll up into that ADO epic and its goal.
- A GitHub epic can only hang under **one** ADO epic. If two ADO epics claim the same GitHub title, the first one in CSV order keeps it.
- Unmatched work is listed separately: ADO epics not yet in GitHub, GitHub epics not under a Goal, and orphan tasks with no parent.

If an epic was renamed, or one ADO epic should collect several GitHub epics, add a mapping in `aliases.json`. Keys are Azure DevOps titles. Values are one GitHub title or a list of GitHub titles:

```json
{
  "Azure DevOps epic title": "GitHub epic title",
  "Network design": [
    "Network design",
    "DNS zones ready",
    "[qa] Hardware base setup"
  ]
}
```

Exact title matches still apply even if you also list extra GitHub titles. You only need to list the GitHub names that differ.

Goal sequence:

```json
["1001", "1003", "1002"]
```

## What the report counts

Progress is the share of GitHub **tasks / bugs** that are closed, rolled up to epic and goal. When several GitHub epics map to one ADO epic, their tasks are counted together. Azure DevOps Goal/Epic state is shown as a status badge but is not mixed into the percentage. Epics that exist only in Azure DevOps appear in the tree with “No GitHub tasks yet”. Sync-test, Dependabot and similar noise issues are excluded.

## Expected export columns

Azure DevOps CSV: `ID`, `Work Item Type`, `Title`, `Assigned To`, `State`, `Tags`

GitHub TSV: `Type`, `Title`, `URL`, `Status`, `Parent issue`, `Closed`, `Updated`

## Tests

```bash
PYTHONPATH=. python3 -m unittest tests.test_merge -v
```

Tests use anonymized fixtures in `tests/fixtures/`.
