# Toodles

Merges two exports into one Goal → Epic → Task → Task view:

1. **Azure DevOps CSV** — high-level Goals, with their Epics listed directly underneath each Goal.
2. **GitHub TSV** — Epics and Tasks (including nested tasks) plus the parent-issue links.

Epics are the join key. The tool matches them by title across both systems, then hangs GitHub tasks (and sub-tasks) under the Azure DevOps goal they belong to.

## Input files

Put local exports in `input/`. TSV snapshots stay gitignored; the Azure DevOps CSV, aliases, and goal-order files can be committed so CI can build the report.

```
input/
  roadmap.csv          # Azure DevOps export
  tracker.tsv          # GitHub export
  aliases.json         # optional title mapping (also aliases-multi.json)
  goal-order.json      # optional goal ID order
```

```bash
python3 -m toodles --import
```

That fetches the GitHub project through the API, writes `input/my-projects.tsv`, then builds the report. The token is read from the environment (`GITHUB_TOKEN`, or `TOODLES_GITHUB_TOKEN`). Org and project come from `--github-org` / `--github-project` / `--github-project-number`, or from `GITHUB_ORG`, `GITHUB_PROJECT`, and `GITHUB_PROJECT_NUMBER`. A local `.env` file is loaded if present (see `.env.example`) and never overrides variables already set.

If you omit `--import` but those environment values are already set, the same fetch-then-build path runs. Use `--no-import` to keep an existing TSV. Use `--github PATH` to point at a hand-exported file.

If you omit `--ado` / `--github`, the newest `*.csv` in `input/` (or the current directory) is used, and the GitHub TSV is the **latest** `*.tsv` after sorting by file date, then by the trailing `(n)` in the filename (`(9)` before `(10)`). Only that current TSV is processed. Alias files (`aliases.json`, `aliases-multi.json`, or another `*alias*.json`) and `input/goal-order.json` are picked up automatically when present. If several alias files exist, `aliases.json` wins; pass `--aliases PATH` to choose another.

```bash
python3 -m toodles --import --open
python3 -m toodles --no-import
python3 -m toodles --format markdown -o output/status.md
python3 -m toodles --format text --stdout
python3 -m toodles --format json -o output/status.json
python3 -m toodles --no-summary
```

Import alone:

```bash
python3 -m toodles.github_import --org my-org --project "My board" --output input/my-projects.tsv
```

A folded **Status summary** at the top of the HTML report is computed from each task's `Created` and `Closed` timestamps (last 5 working days and last 15 working days), with two charts for the full project: cumulative opened vs closed, and open tickets each day (running opened minus closed). Use `--no-summary` to skip it.

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

Progress is the share of GitHub **tasks / bugs** that are closed, rolled up to epic and goal. When several GitHub epics map to one ADO epic, their tasks are counted together. GitHub issues typed as **Bug** also get their own summary card (closed vs open), including bugs that sit under a goal and orphan bugs with no parent. The HTML report lists every Task and Bug GitHub status as checkboxes so you can hide statuses you do not want to see. The **All** switch next to them checks or clears every status at once, so you can turn them all off and then tick only the ones you want. Goal and epic status badges use the Azure DevOps CSV `State` column (not the GitHub board status). Task and bug pills still use GitHub status because those items are not in the CSV. Epics that exist only in Azure DevOps appear in the tree with “No GitHub tasks yet”. Sync-test, Dependabot and similar noise issues are excluded.

## Expected export columns

Azure DevOps CSV: `ID`, `Work Item Type`, `Title`, `Assigned To`, `State`, `Tags`

GitHub TSV: `Type`, `Title`, `URL`, `Status`, `Parent issue`, `Closed`, `Updated`

## GitHub Actions and Pages

`.github/workflows/publish-status.yml` imports the project every six hours (and on push to `main`), writes `output/index.html`, and publishes it to GitHub Pages.

1. Create a fine-grained or classic PAT that can read the org project (`read:project` and `read:org`).
2. Add a repository secret named `TOODLES_GITHUB_TOKEN`.
3. Add repository variables `TOODLES_GITHUB_ORG`, `TOODLES_GITHUB_PROJECT`, and optionally `TOODLES_GITHUB_PROJECT_NUMBER`.
4. Commit the Azure DevOps CSV plus `input/aliases*.json` and `input/goal-order.json` (those config files are no longer gitignored).
5. In the repo: **Settings → Pages → Build and deployment → Source: GitHub Actions**.

The workflow passes the secret into the process environment as `GITHUB_TOKEN`:

```yaml
env:
  GITHUB_TOKEN: ${{ secrets.TOODLES_GITHUB_TOKEN }}
  GITHUB_ORG: ${{ vars.TOODLES_GITHUB_ORG }}
  GITHUB_PROJECT: ${{ vars.TOODLES_GITHUB_PROJECT }}
  GITHUB_PROJECT_NUMBER: ${{ vars.TOODLES_GITHUB_PROJECT_NUMBER }}
```

The published site is `https://<owner>.github.io/<repo>/`.

## Tests

```bash
PYTHONPATH=. python3 -m unittest discover -s tests -v
```

Tests use anonymized fixtures in `tests/fixtures/`.
