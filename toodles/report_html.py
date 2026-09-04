from __future__ import annotations

import json
from datetime import datetime, timezone
from html import escape
from pathlib import Path

from toodles.merge import ProjectReport
from toodles.models import Node, Progress

BUCKET_LABELS = {
    "done": "Done",
    "review": "In review",
    "progress": "In progress",
    "waiting": "Waiting",
    "todo": "Not started",
    "unknown": "No status",
}

BUCKET_COLORS = {
    "done": "#3e8635",
    "review": "#5752d7",
    "progress": "#06c",
    "waiting": "#f0ab00",
    "todo": "#8a8d90",
    "unknown": "#6a6e73",
}


def _pct(progress: Progress) -> str:
    return f"{progress.percent:.0f}%"


def _bar(progress: Progress) -> str:
    if progress.total == 0:
        return '<div class="bar empty"><span>No GitHub tasks yet</span></div>'
    segments = []
    for bucket, label in BUCKET_LABELS.items():
        count = progress.by_bucket.get(bucket, 0)
        if not count:
            continue
        width = 100.0 * count / progress.total
        segments.append(
            f'<i class="seg {bucket}" style="width:{width:.2f}%" title="{escape(label)}: {count}"></i>'
        )
    return f'<div class="bar">{"".join(segments)}</div>'


def _status_pill(node: Node) -> str:
    status = node.display_status or "No status"
    return f'<span class="pill {escape(node.bucket)}">{escape(status)}</span>'


def _item_meta(node: Node) -> str:
    bits: list[str] = []
    if node.ado_id:
        bits.append(f"ADO {escape(node.ado_id)}")
    if node.github_number:
        label = f"#{escape(node.github_number)}"
        if node.github_url:
            bits.append(f'<a href="{escape(node.github_url)}" target="_blank" rel="noreferrer">{label}</a>')
        else:
            bits.append(label)
    if node.ado_assignee:
        name = node.ado_assignee.split("<")[0].strip().rstrip(",")
        if name:
            bits.append(escape(name))
    return " · ".join(bits)


def _render_task(node: Node, depth: int) -> str:
    if node.noise:
        return ""
    nested = "".join(_render_task(child, depth + 1) for child in node.children)
    open_attr = " open" if depth < 1 and node.children else ""
    title = escape(node.title)
    if node.github_url:
        title = f'<a href="{escape(node.github_url)}" target="_blank" rel="noreferrer">{title}</a>'
    body = f'<div class="kids">{nested}</div>' if nested else ""
    return (
        f'<details class="task depth-{depth}" data-kind="{escape(node.kind)}" '
        f'data-status="{escape(node.bucket)}" data-title="{escape(node.title.casefold())}"{open_attr}>'
        f"<summary><span class='kind'>{escape(node.kind)}</span>"
        f"<span class='name'>{title}</span>{_status_pill(node)}</summary>"
        f"{body}</details>"
    )


def _render_epic(epic: Node) -> str:
    progress = epic.progress()
    tasks = "".join(_render_task(child, 0) for child in epic.children)
    if not epic.children:
        tasks = '<p class="empty-note">No GitHub tasks linked to this epic yet.</p>'
    title = escape(epic.title)
    if epic.github_url:
        title = f'<a href="{escape(epic.github_url)}" target="_blank" rel="noreferrer">{title}</a>'
    return (
        f'<details class="epic" data-env="{escape(epic.environment)}" '
        f'data-status="{escape(epic.bucket)}" data-title="{escape(epic.title.casefold())}" open>'
        f"<summary><div class='epic-head'>"
        f"<div class='epic-title'><span class='kind'>Epic</span><span class='name'>{title}</span></div>"
        f"<div class='epic-stats'>{_status_pill(epic)}"
        f"<strong>{progress.done}/{progress.total}</strong> {_bar(progress)}</div>"
        f"<div class='meta'>{_item_meta(epic)}</div>"
        f"</div></summary>"
        f"<div class='kids'>{tasks}</div></details>"
    )


def _render_goal(goal: Node) -> str:
    progress = goal.progress()
    epics = "".join(_render_epic(epic) for epic in goal.children)
    assignee = goal.ado_assignee.split("<")[0].strip().rstrip(",")
    return (
        f'<article class="goal" data-env="{escape(goal.environment)}" '
        f'data-title="{escape(goal.title.casefold())}" data-order="{goal.source_order}">'
        f'<header><div class="goal-kicker">'
        f'<span class="seq" title="Manual goal order from goal-order.json">{goal.source_order}</span>'
        f'<p class="env-tag {escape(goal.environment.casefold())}">{escape(goal.environment)}</p>'
        f"</div>"
        f"<h2>{escape(goal.title)}</h2>"
        f'<div class="goal-meta">'
        f"{_status_pill(goal)}"
        f'<span>ADO {escape(goal.ado_id or "—")}</span>'
        f'<span>{escape(assignee or "Unassigned")}</span>'
        f"<span>{len(goal.children)} epics</span>"
        f"<span>{progress.done}/{progress.total} GitHub tasks closed</span>"
        f"</div>"
        f'<div class="goal-progress"><div class="pct">{_pct(progress)}</div>{_bar(progress)}</div>'
        f"</header>"
        f'<div class="epics">{epics}</div>'
        f"</article>"
    )


def _gap_list(title: str, rows: list, empty: str) -> str:
    if not rows:
        return f'<section class="gap"><h3>{escape(title)}</h3><p class="empty-note">{escape(empty)}</p></section>'
    items = []
    for row in rows:
        extra = []
        if row.ado_id:
            extra.append(f"ADO {escape(row.ado_id)}")
        if row.github_number:
            extra.append(f"#{escape(row.github_number)}")
        meta = " · ".join(extra)
        items.append(
            f"<li><strong>{escape(row.title)}</strong>"
            f"<span>{escape(row.environment)}{(' · ' + meta) if meta else ''}</span></li>"
        )
    return (
        f'<section class="gap"><h3>{escape(title)}</h3>'
        f'<p class="count">{len(rows)}</p><ul>{"".join(items)}</ul></section>'
    )


def _legend() -> str:
    chips = []
    for bucket, label in BUCKET_LABELS.items():
        chips.append(f'<span class="pill {bucket}">{escape(label)}</span>')
    return "".join(chips)


def _summary_card(label: str, progress: Progress, extra: str = "") -> str:
    return (
        f'<div class="summary-card"><p>{escape(label)}</p>'
        f"<strong>{_pct(progress)}</strong>"
        f"<span>{progress.done} of {progress.total} tasks closed</span>"
        f"{_bar(progress)}"
        f"{extra}</div>"
    )


def render_html(report: ProjectReport, generated_at: datetime | None = None) -> str:
    generated_at = generated_at or datetime.now(timezone.utc)
    overall = report.overall_progress()
    env_cards = [_summary_card(env, report.overall_progress(env)) for env in report.summary_environments()]
    env_options = "".join(
        f'<option value="{escape(env)}">{escape(env)}</option>' for env in report.summary_environments()
    )
    goals = "".join(_render_goal(goal) for goal in report.goals)
    unmapped = ""
    if report.unmapped_epics or report.orphan_tasks:
        epic_html = "".join(_render_epic(epic) for epic in report.unmapped_epics)
        orphans = "".join(_render_task(task, 0) for task in report.orphan_tasks)
        unmapped = (
            '<article class="goal unmapped" data-env="Unmapped">'
            "<header><div class='goal-kicker'><p class='env-tag other'>Unmapped</p></div>"
            "<h2>Work not hanging under an Azure DevOps goal</h2>"
            "<p class='lede'>GitHub epics and tasks that could not be matched by title to the ADO roadmap.</p>"
            "</header>"
            f'<div class="epics">{epic_html}'
            + (f'<h3 class="orphan-head">Orphan tasks</h3>{orphans}' if report.orphan_tasks else "")
            + "</div></article>"
        )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Project status by goal</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Red+Hat+Display:wght@400;500;700&family=Red+Hat+Text:wght@400;500;700&display=swap" rel="stylesheet">
  <style>
    :root {{
      --pf-black: #151515;
      --pf-ink: #151515;
      --pf-muted: #6a6e73;
      --pf-page: #f0f0f0;
      --pf-card: #fff;
      --pf-line: #d2d2d2;
      --pf-red: #ee0000;
      --pf-red-dark: #a60000;
      --pf-link: #06c;
      --pf-radius: 3px;
      --hwqa: #2b9af3;
      --hwprod: #c9190b;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      color: var(--pf-ink);
      background: var(--pf-page);
      font: 16px/1.5 "Red Hat Text", "RedHatText", Helvetica, Arial, sans-serif;
    }}
    h1, h2, h3, .pct, .summary-card strong, .brand-name {{
      font-family: "Red Hat Display", "RedHatDisplay", "Red Hat Text", Helvetica, Arial, sans-serif;
    }}
    a {{ color: var(--pf-link); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .masthead {{
      background: var(--pf-black);
      color: #fff;
      border-top: 4px solid var(--pf-red);
      min-height: 72px;
      display: flex;
      align-items: center;
    }}
    .masthead-inner {{
      width: min(1200px, 100%);
      margin: 0 auto;
      padding: 12px 24px;
      display: flex;
      align-items: center;
      gap: 16px;
    }}
    .brand-bar {{
      width: 4px;
      height: 28px;
      background: var(--pf-red);
      flex: none;
    }}
    .brand-name {{ font-size: 18px; font-weight: 500; letter-spacing: 0.01em; }}
    .brand-sub {{ color: #b8bbbe; font-size: 13px; margin-left: auto; }}
    .page {{ width: min(1200px, 100%); margin: 0 auto; padding: 24px 24px 48px; }}
    .page-header h1 {{
      font-size: 28px;
      font-weight: 500;
      margin: 0 0 8px;
    }}
    .lede {{ color: var(--pf-muted); max-width: 70ch; margin: 0 0 16px; }}
    .toolbar {{
      display: flex; flex-wrap: wrap; gap: 8px; align-items: center;
      margin: 0 0 12px;
    }}
    .toolbar input, .toolbar select {{
      font: 14px/1.4 "Red Hat Text", Helvetica, Arial, sans-serif;
      border: 1px solid var(--pf-line);
      background: #fff;
      border-radius: var(--pf-radius);
      padding: 6px 12px;
      color: var(--pf-ink);
      min-height: 36px;
    }}
    .toolbar input {{ min-width: 260px; }}
    .toolbar input:focus, .toolbar select:focus {{
      outline: 2px solid var(--pf-link);
      outline-offset: 2px;
      border-color: var(--pf-link);
    }}
    .legend {{ display: flex; flex-wrap: wrap; gap: 6px; margin: 0 0 20px; }}
    .summary {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 16px;
      margin-bottom: 24px;
    }}
    .summary-card, .goal, .gap {{
      background: var(--pf-card);
      border: 1px solid var(--pf-line);
      border-radius: var(--pf-radius);
      box-shadow: 0 1px 2px rgba(3,3,3,0.06);
    }}
    .summary-card {{ padding: 16px 20px 18px; border-top: 3px solid var(--pf-red); }}
    .summary-card p {{
      margin: 0;
      font-size: 12px;
      font-weight: 500;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      color: var(--pf-muted);
    }}
    .summary-card strong {{ display: block; font-size: 32px; font-weight: 700; margin: 8px 0 2px; }}
    .summary-card span {{ color: var(--pf-muted); font-size: 13px; }}
    main {{ display: grid; gap: 16px; }}
    .goal header {{ padding: 16px 20px 12px; }}
    .goal-kicker {{ display: flex; align-items: center; gap: 8px; margin: 0 0 8px; }}
    .seq {{
      display: inline-flex; align-items: center; justify-content: center;
      min-width: 1.7em; height: 1.7em; padding: 0 6px;
      border-radius: var(--pf-radius);
      background: var(--pf-black); color: #fff;
      font-size: 12px; font-weight: 700;
    }}
    .goal h2 {{ margin: 0 0 8px; font-size: 20px; font-weight: 500; }}
    .goal-meta {{ display: flex; flex-wrap: wrap; gap: 8px 14px; color: var(--pf-muted); font-size: 13px; }}
    .goal-progress {{ display: grid; grid-template-columns: auto 1fr; gap: 12px; align-items: center; margin-top: 12px; }}
    .pct {{ font-size: 24px; font-weight: 700; color: var(--pf-black); }}
    .env-tag {{
      display: inline-block; margin: 0; padding: 2px 8px; border-radius: var(--pf-radius);
      font-size: 11px; font-weight: 500; letter-spacing: 0.04em; text-transform: uppercase; color: #fff;
      background: #6a6e73;
    }}
    .env-tag.qa, .env-tag.hwqa {{ background: var(--hwqa); }}
    .env-tag.prod, .env-tag.hwprod {{ background: var(--hwprod); }}
    .epics {{ padding: 0 8px 12px; }}
    details.epic {{
      border-top: 1px solid var(--pf-line);
      padding: 10px 12px;
    }}
    details.task {{
      background: #fafafa;
      border: 1px solid var(--pf-line);
      border-radius: var(--pf-radius);
      margin: 6px 0;
      padding: 6px 10px;
    }}
    summary {{ cursor: pointer; list-style: none; }}
    summary::-webkit-details-marker {{ display: none; }}
    summary::before {{
      content: "";
      display: inline-block;
      width: 0; height: 0;
      margin-right: 8px;
      border-top: 5px solid transparent;
      border-bottom: 5px solid transparent;
      border-left: 6px solid #6a6e73;
      transform: translateY(-1px);
    }}
    details[open] > summary::before {{
      border-left: 5px solid transparent;
      border-right: 5px solid transparent;
      border-top: 6px solid #6a6e73;
      border-bottom: 0;
    }}
    .epic-head {{ display: grid; gap: 6px; }}
    .epic-title, details.task summary {{ display: flex; gap: 8px; align-items: baseline; flex-wrap: wrap; }}
    .epic-stats {{ display: grid; grid-template-columns: auto auto 1fr; gap: 10px; align-items: center; }}
    .kind {{
      font-size: 11px; font-weight: 500; letter-spacing: 0.04em; text-transform: uppercase;
      color: var(--pf-muted); border: 1px solid var(--pf-line); border-radius: var(--pf-radius); padding: 1px 6px;
    }}
    .name {{ font-weight: 500; }}
    .meta {{ color: var(--pf-muted); font-size: 12px; }}
    .bar {{
      display: flex; height: 8px; background: #f0f0f0; border-radius: var(--pf-radius); overflow: hidden;
    }}
    .bar.empty {{ height: auto; background: none; color: var(--pf-muted); font-size: 12px; }}
    .seg {{ display: block; height: 100%; }}
    .seg.done {{ background: {BUCKET_COLORS["done"]}; }}
    .seg.review {{ background: {BUCKET_COLORS["review"]}; }}
    .seg.progress {{ background: {BUCKET_COLORS["progress"]}; }}
    .seg.waiting {{ background: {BUCKET_COLORS["waiting"]}; }}
    .seg.todo {{ background: {BUCKET_COLORS["todo"]}; }}
    .seg.unknown {{ background: {BUCKET_COLORS["unknown"]}; }}
    .pill {{
      display: inline-flex; align-items: center; border-radius: var(--pf-radius);
      padding: 0 8px; font-size: 12px; font-weight: 500; min-height: 22px;
      border: 1px solid transparent;
    }}
    .pill.done {{ background: #e9f7e6; color: #1e4f18; }}
    .pill.review {{ background: #f0effc; color: #2a2670; }}
    .pill.progress {{ background: #e3f2fd; color: #002952; }}
    .pill.waiting {{ background: #fdf7e7; color: #795600; }}
    .pill.todo {{ background: #f0f0f0; color: #151515; }}
    .pill.unknown {{ background: #fff; color: #6a6e73; border-color: var(--pf-line); }}
    .empty-note {{ color: var(--pf-muted); font-style: italic; margin: 8px 12px; }}
    .kids {{ margin-left: 16px; }}
    .gaps {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; }}
    .gap {{ padding: 16px 20px; }}
    .gap h3 {{ margin: 0 0 8px; font-size: 16px; font-weight: 500; }}
    .gap .count {{ float: right; margin: 0; color: var(--pf-muted); }}
    .gap ul {{ margin: 0; padding: 0; list-style: none; display: grid; gap: 8px; }}
    .gap li span {{ display: block; color: var(--pf-muted); font-size: 12px; }}
    .orphan-head {{ margin: 16px 12px 8px; font-size: 16px; font-weight: 500; }}
    .hidden {{ display: none !important; }}
    @media print {{
      .masthead {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
      .toolbar {{ display: none; }}
    }}
  </style>
</head>
<body>
  <header class="masthead">
    <div class="masthead-inner">
      <span class="brand-bar" aria-hidden="true"></span>
      <span class="brand-name">Project status</span>
      <span class="brand-sub">Goal · Epic · Task</span>
    </div>
  </header>
  <div class="page">
    <div class="page-header">
      <h1>Status by goal</h1>
      <p class="lede">Merged Azure DevOps goals with GitHub epics and nested tasks.
        Goals follow the manual order in goal-order.json.
        Generated {escape(generated_at.strftime("%d %b %Y, %H:%M UTC"))}.
        {report.matched_epics} epics matched across both systems.</p>
      <div class="toolbar">
        <input id="search" type="search" placeholder="Filter by title">
        <select id="env">
          <option value="All">All environments</option>
          {env_options}
          <option value="Unmapped">Unmapped work</option>
        </select>
      </div>
      <div class="legend">{_legend()}</div>
    </div>
    <section class="summary">
      {_summary_card("Overall", overall, f"<span style='display:block;margin-top:8px'>{len(report.goals)} goals · {report.matched_epics} matched epics</span>")}
      {"".join(env_cards)}
    </section>
    <main>
      {goals}
      {unmapped}
      <div class="gaps">
        {_gap_list("ADO epics not found in GitHub", report.ado_without_github, "Every Azure DevOps epic has a GitHub counterpart.")}
        {_gap_list("GitHub epics not under an ADO goal", report.github_without_ado, "Every GitHub epic is attached to a goal.")}
      </div>
    </main>
  </div>
  <script>
    const search = document.getElementById("search");
    const env = document.getElementById("env");
    function applyFilter() {{
      const q = (search.value || "").trim().toLowerCase();
      const selected = env.value;
      document.querySelectorAll("article.goal").forEach((goal) => {{
        const envOk = selected === "All" || goal.dataset.env === selected;
        const titleOk = !q || goal.dataset.title.includes(q) ||
          [...goal.querySelectorAll("[data-title]")].some((n) => n.dataset.title.includes(q));
        goal.classList.toggle("hidden", !(envOk && titleOk));
        if (q) {{
          goal.querySelectorAll("details").forEach((d) => {{
            const hit = (d.dataset.title || "").includes(q) || d.querySelector("[data-title]") &&
              [...d.querySelectorAll("[data-title]")].some((n) => n.dataset.title.includes(q));
            if (hit) d.open = true;
          }});
        }}
      }});
    }}
    search.addEventListener("input", applyFilter);
    env.addEventListener("change", applyFilter);
  </script>
</body>
</html>
"""


def write_html(report: ProjectReport, path: Path, generated_at: datetime | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_html(report, generated_at), encoding="utf-8")


def report_to_dict(report: ProjectReport) -> dict:
    def node_dict(node: Node) -> dict:
        progress = node.progress()
        return {
            "kind": node.kind,
            "title": node.title,
            "environment": node.environment,
            "order": node.source_order or None,
            "ado_id": node.ado_id or None,
            "ado_state": node.ado_state or None,
            "github_url": node.github_url or None,
            "github_status": node.github_status or None,
            "status": node.display_status or None,
            "progress": {
                "done": progress.done,
                "total": progress.total,
                "percent": round(progress.percent, 1),
                "by_status": progress.by_bucket,
            },
            "children": [node_dict(child) for child in node.children],
        }

    overall = report.overall_progress()
    return {
        "overall": {
            "done": overall.done,
            "total": overall.total,
            "percent": round(overall.percent, 1),
        },
        "matched_epics": report.matched_epics,
        "goals": [node_dict(goal) for goal in report.goals],
        "unmapped_epics": [node_dict(epic) for epic in report.unmapped_epics],
        "orphan_tasks": [node_dict(task) for task in report.orphan_tasks],
        "gaps": {
            "ado_without_github": [gap.__dict__ for gap in report.ado_without_github],
            "github_without_ado": [gap.__dict__ for gap in report.github_without_ado],
        },
    }


def render_json(report: ProjectReport) -> str:
    return json.dumps(report_to_dict(report), indent=2, ensure_ascii=False) + "\n"
