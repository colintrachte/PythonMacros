"""
dashboard.py — High-level project plan and executive dashboard for PMT.

Reads docs/roadmap.md and docs/shipped.md, computes overall project health,
active workstream tracks (In Progress/Verification), strategic ready queue,
section work distribution, and dependency blocker chains.

Updates or generates DASHBOARD.md between delimited markers:
    <!-- PMT:AUTODASHBOARD:START -->
    ... auto-generated dashboard ...
    <!-- PMT:AUTODASHBOARD:END -->
preserving any human charter notes, decision guidelines, or manual lane commentary.

Usage:
    python helper_scripts/PMT/dashboard.py --write
    python helper_scripts/PMT/dashboard.py --check
    python helper_scripts/PMT/dashboard.py --json
    python helper_scripts/PMT/dashboard.py --print
    python helper_scripts/PMT/dashboard.py --project-root <path> --write
"""

import argparse
import datetime
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import summary  # noqa: E402
except ImportError:
    summary = None

import context_pack  # noqa: E402
import route_tasks  # noqa: E402
from task_records import (  # noqa: E402
    Task,
    blocker_summary,
    derive_reverse_relationships,
    parse_tasks,
    ready_tasks,
    split_header,
    task_statuses,  # noqa: E402
)

# UTF-8 stdout on Windows
for _stream in (sys.stdout, sys.stderr):
    _reconfig = getattr(_stream, "reconfigure", None)
    if callable(_reconfig):
        _reconfig(encoding="utf-8")

DEFAULT_DASHBOARD_FILENAME = "DASHBOARD.md"
LEGACY_DASHBOARD_FILENAME = "01_roadmap.md"

MARKER_START = "<!-- PMT:AUTODASHBOARD:START -->"
MARKER_END = "<!-- PMT:AUTODASHBOARD:END -->"
MARKER_BLOCK_RE = re.compile(
    rf"{re.escape(MARKER_START)}.*?{re.escape(MARKER_END)}",
    re.DOTALL,
)

SHIPPED_TASK_RE = re.compile(r"^- \[x\]\s*\*\*(.+?)\*\*")
SECTION_HEADING_RE = re.compile(r"^#{2,4}\s+(.+?)\s*$")


@dataclass
class ShippedRecord:
    header: str
    title: str
    score: str = ""
    task_class: str = ""
    milestone: str = ""


@dataclass
class DashboardMetrics:
    generated_at: str
    project_name: str
    total_tasks: int
    shipped_count: int
    open_count: int
    active_count: int
    ready_count: int
    blocked_count: int
    draft_count: int
    status_counts: dict[str, int]
    class_counts: dict[str, int]
    score_counts: dict[str, int]
    sections: list[dict[str, Any]]
    active_tasks: list[dict[str, Any]]
    ready_queue: list[dict[str, Any]]
    top_blockers: list[dict[str, Any]]
    blocked_tasks: list[dict[str, Any]]
    standfirst: str = ""
    freshness_message: str = ""
    phases: list[dict[str, Any]] = field(default_factory=list)


def parse_shipped_records(shipped_path: Path) -> list[ShippedRecord]:
    """Parse completed tasks from docs/shipped.md."""
    if not shipped_path.is_file():
        return []
    try:
        lines = shipped_path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []

    records: list[ShippedRecord] = []
    current_milestone = ""

    for line in lines:
        sm = SECTION_HEADING_RE.match(line)
        if sm:
            current_milestone = sm.group(1)
            continue
        m = SHIPPED_TASK_RE.match(line)
        if m:
            header = m.group(1)
            score, title = split_header(header)
            class_value = route_tasks.header_class(line)
            cls = class_value or "?"
            records.append(
                ShippedRecord(
                    header=header,
                    title=title,
                    score=score,
                    task_class=cls,
                    milestone=current_milestone,
                )
            )
    return records


def render_progress_bar(completed: int, total: int, width: int = 12) -> str:
    """Render a clean Unicode progress bar for bounded task sets."""
    if total <= 0:
        return f"[{'░' * width}] 0%"
    pct = min(1.0, max(0.0, completed / total))
    filled = min(width, max(0, round(pct * width)))
    empty = width - filled
    bar = "█" * filled + "░" * empty
    return f"[{bar}] {round(pct * 100)}%"


def collect_dashboard_metrics(
    roadmap_path: Path,
    shipped_path: Path,
    project_root: Path,
) -> DashboardMetrics:
    """Read roadmap and shipped files and compute full project metrics."""
    if not roadmap_path.is_file():
        raise FileNotFoundError(f"Roadmap file not found: {roadmap_path}")

    roadmap_lines = roadmap_path.read_text(encoding="utf-8").splitlines(keepends=True)
    open_tasks = parse_tasks(roadmap_lines, project_root)
    derive_reverse_relationships(open_tasks)

    shipped_records = parse_shipped_records(shipped_path)

    lifecycle_lines = list(roadmap_lines)
    if shipped_path.is_file():
        lifecycle_lines.extend(shipped_path.read_text(encoding="utf-8").splitlines(keepends=True))
    status_map = task_statuses(lifecycle_lines)

    total_shipped = len(shipped_records)
    total_open = len(open_tasks)
    total_all = total_shipped + total_open

    # Status counts
    status_counts: dict[str, int] = {
        "Shipped": total_shipped,
        "Verification": 0,
        "In Progress": 0,
        "Ready": 0,
        "Defined": 0,
        "Draft": 0,
        "Blocked": 0,
        "Held": 0,
        "Deferred": 0,
    }
    for task in open_tasks:
        s = task.status or "Draft"
        matched = False
        for canon in status_counts:
            if canon != "Shipped" and s.lower().startswith(canon.lower()):
                status_counts[canon] += 1
                matched = True
                break
        if not matched:
            status_counts["Draft"] += 1

    active_count = status_counts["In Progress"] + status_counts["Verification"]
    ready_count = status_counts["Ready"]
    blocked_count = status_counts["Blocked"]
    draft_count = status_counts["Draft"] + status_counts["Defined"]

    # Class & Score distribution across open tasks
    class_counts: dict[str, int] = {"1": 0, "2": 0, "3": 0}
    score_counts: dict[str, int] = {"5": 0, "4": 0, "3": 0, "2": 0, "1": 0}

    for task in open_tasks:
        if task.task_class in class_counts:
            class_counts[task.task_class] += 1
        score, _ = split_header(task.header)
        if score in score_counts:
            score_counts[score] += 1

    # Sections progress
    section_map: dict[str, list[Task]] = {}
    for task in open_tasks:
        sec = task.section or "Uncategorized"
        section_map.setdefault(sec, []).append(task)

    sections_data = []
    for sec_name, tasks in section_map.items():
        sec_ready = sum(1 for t in tasks if t.status == "Ready")
        sec_in_prog = sum(1 for t in tasks if t.status in ("In Progress", "Verification"))
        sec_blocked = sum(1 for t in tasks if t.status == "Blocked" or t.dependencies)
        sections_data.append(
            {
                "name": sec_name,
                "open_count": len(tasks),
                "ready_count": sec_ready,
                "in_progress_count": sec_in_prog,
                "blocked_count": sec_blocked,
            }
        )

    # Active work track: In Progress or Verification
    active_tasks = []
    for task in open_tasks:
        if task.status in ("In Progress", "Verification"):
            score, title = split_header(task.header)
            active_tasks.append(
                {
                    "id": task.id,
                    "status": task.status,
                    "header": task.header,
                    "title": title,
                    "score": score,
                    "class": task.task_class,
                    "route": task.route,
                    "section": task.section,
                }
            )

    # Strategic Ready Queue (unblocked Ready tasks)
    tasks_by_id = {task.id: task for task in open_tasks if task.id}
    ready_candidates = ready_tasks(open_tasks, status_map)

    def _ready_sort_key(t: Task):
        score_str, _ = split_header(t.header)
        score_val = int(score_str) if score_str.isdigit() else 0
        effort_val = int(t.effort) if t.effort.isdigit() else 9999
        return (-score_val, effort_val, t.roadmap_order)

    ready_candidates.sort(key=_ready_sort_key)

    ready_queue = []
    for task in ready_candidates[:8]:  # Top 8
        score, title = split_header(task.header)
        ready_queue.append(
            {
                "id": task.id,
                "title": title,
                "header": task.header,
                "score": score,
                "class": task.task_class,
                "route": task.route,
                "section": task.section,
                "context_load": task.effort,
            }
        )

    # Blocker analysis & critical path
    open_task_ids = set(tasks_by_id.keys())
    blocker_impact: dict[str, list[str]] = {}
    for task in open_tasks:
        for dep in task.dependencies:
            if dep in open_task_ids:
                blocker_impact.setdefault(dep, []).append(task.id)

    top_blockers = []
    for blocker_id, blocked_ids in sorted(
        blocker_impact.items(), key=lambda item: len(item[1]), reverse=True
    ):
        blocker_task = tasks_by_id.get(blocker_id)
        if blocker_task:
            score, title = split_header(blocker_task.header)
            top_blockers.append(
                {
                    "id": blocker_id,
                    "title": title,
                    "status": blocker_task.status,
                    "blocks_count": len(blocked_ids),
                    "blocks_task_ids": blocked_ids,
                }
            )

    blocked_tasks = []
    for task in open_tasks:
        if task.status == "Blocked" or (
            task.dependencies and any(status_map.get(dep) != "Shipped" for dep in task.dependencies)
        ):
            _, title = split_header(task.header)
            blocked_tasks.append(
                {
                    "id": task.id,
                    "title": title,
                    "status": task.status,
                    "warning": blocker_summary(task, tasks_by_id, status_map),
                }
            )

    project_name = project_root.name
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    # Canonical Summary integration
    standfirst = ""
    freshness_message = ""
    phases_data = []
    if summary is not None:
        try:
            summary_doc = summary.load_summary(project_root)
            standfirst = summary_doc.standfirst
            freshness = summary.check_freshness(summary_doc, total_shipped, total_open)
            freshness_message = f"Canonical Summary: {freshness.message}"
            phases_data = [p.to_dict() for p in summary_doc.phases]
        except Exception:
            pass

    return DashboardMetrics(
        generated_at=now_str,
        project_name=project_name,
        total_tasks=total_all,
        shipped_count=total_shipped,
        open_count=total_open,
        active_count=active_count,
        ready_count=ready_count,
        blocked_count=blocked_count,
        draft_count=draft_count,
        status_counts=status_counts,
        class_counts=class_counts,
        score_counts=score_counts,
        sections=sections_data,
        active_tasks=active_tasks,
        ready_queue=ready_queue,
        top_blockers=top_blockers[:5],
        blocked_tasks=blocked_tasks[:5],
        standfirst=standfirst,
        freshness_message=freshness_message,
        phases=phases_data,
    )


def generate_dashboard_markdown(metrics: DashboardMetrics) -> str:
    """Format DashboardMetrics into the standardized auto-dashboard Markdown block."""
    lines = [
        MARKER_START,
        "## Executive Project Dashboard",
        "",
    ]

    if metrics.standfirst:
        lines.extend(
            [
                f"> **Executive Standfirst:** {metrics.standfirst}",
                "",
            ]
        )
    if metrics.freshness_message:
        lines.extend(
            [
                f"_{metrics.freshness_message}_",
                "",
            ]
        )

    lines.extend(
        [
            f"> **Active Work Stream:** {metrics.active_count} In Flight · "
            f"{metrics.ready_count} Ready to Dispatch · {metrics.blocked_count} Blocked/Waiting · "
            f"{metrics.shipped_count} Shipped to date",
            "",
        ]
    )

    if metrics.phases:
        lines.extend(
            [
                "### Milestone & Phase Progression",
                "",
            ]
        )
        for p in metrics.phases:
            check_box = "[x]" if p.get("status") == "done" else "[ ]"
            desc = p.get("description", "")
            desc = re.sub(
                r"^\((Active|Planned|Done|In Progress)\)\s*[-—]?\s*", "", desc, flags=re.IGNORECASE
            ).strip()
            tag = f" ({p.get('status').title()})" if p.get("status") in ("active", "now") else ""
            desc_str = f" — {desc}" if desc else ""
            lines.append(f"- {check_box} **{p.get('title')}**{tag}{desc_str}")
        lines.append("")

    lines.extend(
        [
            "### Current Work Distribution",
            "",
            "| Work Stream | Count | Focus & Description |",
            "| :--- | :--- | :--- |",
            f"| ⚡ **Active (In Flight)** | {metrics.active_count} | Tasks currently being drafted or verified ({metrics.status_counts.get('In Progress', 0)} In Progress, {metrics.status_counts.get('Verification', 0)} Verification) |",
            f"| 🟢 **Execution Ready** | {metrics.ready_count} | Unblocked tasks ready for immediate dispatch |",
            f"| ⏳ **Blocked / Waiting** | {metrics.blocked_count} | Tasks with unmet dependencies or awaiting external input |",
            f"| 📝 **Draft & Backlog** | {metrics.draft_count} | Early-stage task definitions awaiting refinement |",
            f"| 🛡️ **Safety Spine (Class 3)** | {metrics.class_counts.get('3', 0)} open | High-stakes destructive write & architecture boundaries |",
            f"| 📦 **Shipped (Archive)** | {metrics.shipped_count} | Completed roadmap items recorded in `docs/shipped.md` |",
            "",
        ]
    )

    # Active work track
    lines.extend(
        [
            "### Active Work Track (In Flight)",
            "",
        ]
    )
    if metrics.active_tasks:
        for t in metrics.active_tasks:
            icon = "🔄" if t["status"] == "In Progress" else "🔍"
            medal = route_tasks._medal(t["score"]) if t["score"] else ""
            lines.append(
                f"- {icon} **{t['status']}** · Score {t['score']} {medal} · Class {t['class']} — **{t['title']}** "
                f"(`{t['id']}`)"
            )
            if t.get("route"):
                lines.append(f"  - *Assigned / Routed:* `{t['route']}` · *Section:* {t['section']}")
    else:
        lines.append(
            "*No tasks currently in flight. Pick an unblocked item from the Ready Queue below.*"
        )
    lines.append("")

    # Strategic Ready Queue
    lines.extend(
        [
            "### Strategic Ready Queue (Next Up)",
            "",
        ]
    )
    if metrics.ready_queue:
        for idx, t in enumerate(metrics.ready_queue, 1):
            medal = route_tasks._medal(t["score"]) if t["score"] else ""
            lines.append(
                f"{idx}. **Score {t['score']} {medal} · Class {t['class']} — {t['title']}** "
                f"(`{t['id']}`)"
            )
            lines.append(
                f"   - *Route:* `{t['route']}` · *Context Load:* `{t['context_load']}` · *Section:* {t['section']}"
            )
    else:
        lines.append(
            "*No open tasks marked Ready. Promote high-priority Draft/Defined tasks in Quest Board.*"
        )
    lines.append("")

    # Sections progress
    if metrics.sections:
        lines.extend(
            [
                "### Section Breakdown",
                "",
            ]
        )
        for sec in metrics.sections:
            lines.append(
                f"- **{sec['name']}**: {sec['open_count']} open "
                f"({sec['in_progress_count']} in flight, {sec['ready_count']} ready, {sec['blocked_count']} blocked/waiting)"
            )
        lines.append("")

    # Blocker & critical path leverage
    if metrics.top_blockers:
        lines.extend(
            [
                "### Critical Path & Unblocking Leverage",
                "",
                "_Completing these items delivers the highest downstream unblocking value:_",
                "",
            ]
        )
        for b in metrics.top_blockers:
            lines.append(
                f"- ⚡ **{b['title']}** (`{b['id']}`) unblocks **{b['blocks_count']}** open downstream task(s) "
                f"(Status: `{b['status']}`)"
            )
        lines.append("")

    lines.extend(
        [
            f"_Auto-generated by PMT Dashboard on {metrics.generated_at}._",
            MARKER_END,
        ]
    )

    return "\n".join(lines)


def build_default_high_level_roadmap(
    project_name: str,
    dashboard_md: str,
) -> str:
    """Generate a clean initial DASHBOARD.md document."""
    return f"""# {project_name} — High-Level Project Dashboard

This is the human decision document and executive dashboard. It synthesizes open tasks in
`docs/roadmap.md` and completed history in `docs/shipped.md` into an auto-populated status
summary, active track overview, and strategic prioritization guide.

`docs/roadmap.md` holds the bounded, executable tasks with file lists and dependencies.
`docs/shipped.md` holds completed history.
Strategic charter decisions, architecture principles, and platform boundaries live here.

{dashboard_md}

## Strategic Objectives & Committed Destinations

These remain part of the project vision even when they have no immediate task in `docs/roadmap.md`:

- **Core Usability & Ergonomics**: Low-friction workflows, clear status feedback, and zero unnecessary manual overhead.
- **Safety First**: Destructive writes and critical boundaries must be protected by explicit tests and verification gates.
- **Self-Hosting & Dogfooding**: Rely on our own tools to plan and deliver work.

## Decision Guidelines & Planning Rules

- **One Focused Track**: Keep bounded, focused tasks in progress rather than fragmenting context.
- **Start Simple, Enrich Later**: Capture tasks with simple drafts and add file lists when preparing for execution.
- **Class 3 Safety**: All file writes and migrations must be atomic and reversible.
"""


def update_or_create_dashboard_file(
    target_path: Path,
    dashboard_md: str,
    project_name: str = "",
) -> bool:
    """Write or update target_path with the generated dashboard block.
    Preserves all content outside the dashboard markers."""
    if not project_name:
        project_name = target_path.parent.name

    if target_path.is_file():
        original_content = target_path.read_text(encoding="utf-8")
        if MARKER_START in original_content and MARKER_END in original_content:
            new_content = MARKER_BLOCK_RE.sub(dashboard_md, original_content)
        else:
            header_match = re.search(r"^(#\s+[^\n]+(?:\n\n[^\n]+)?)\n\n", original_content)
            if header_match:
                insert_pos = header_match.end()
                new_content = (
                    original_content[:insert_pos]
                    + dashboard_md
                    + "\n\n"
                    + original_content[insert_pos:]
                )
            else:
                new_content = dashboard_md + "\n\n" + original_content
    else:
        new_content = build_default_high_level_roadmap(project_name, dashboard_md)

    # Atomic write
    target_path.parent.mkdir(parents=True, exist_ok=True)
    temp_file = target_path.with_suffix(".tmp")
    try:
        # Keep the file's line-ending style (a bare write_text() emits CRLF on Windows).
        newline = route_tasks.newline_of(target_path)
        temp_file.write_text(new_content, encoding="utf-8", newline=newline)
        temp_file.replace(target_path)
    finally:
        if temp_file.exists():
            temp_file.unlink(missing_ok=True)

    return True


TIMESTAMP_LINE_RE = re.compile(r"^_Auto-generated by PMT Dashboard on [^.]+\._$", re.MULTILINE)


def check_dashboard_file(target_path: Path, dashboard_md: str) -> bool:
    """Check if target_path exists and contains a current dashboard block (ignoring timestamp differences)."""
    if not target_path.is_file():
        return False
    content = target_path.read_text(encoding="utf-8")
    m = MARKER_BLOCK_RE.search(content)
    if not m:
        return False
    existing_block = TIMESTAMP_LINE_RE.sub("", m.group(0)).strip()
    candidate_block = TIMESTAMP_LINE_RE.sub("", dashboard_md).strip()
    return existing_block == candidate_block


def resolve_paths(
    project_root: Path | None,
    roadmap_path: Path | None,
    shipped_path: Path | None,
    write_path: Path | None,
) -> tuple[Path, Path, Path, Path]:
    """Resolve project root, roadmap, shipped, and write target paths."""
    project_root = context_pack.repo_root() if project_root is None else project_root.resolve()
    roadmap_path = (
        project_root / "docs" / "roadmap.md" if roadmap_path is None else roadmap_path.resolve()
    )
    shipped_path = (
        project_root / "docs" / "shipped.md" if shipped_path is None else shipped_path.resolve()
    )
    if write_path is None:
        # Check if legacy 01_roadmap.md already exists in project root, else use default DASHBOARD.md
        legacy_path = project_root / LEGACY_DASHBOARD_FILENAME
        default_path = project_root / DEFAULT_DASHBOARD_FILENAME
        write_path = (
            legacy_path if legacy_path.is_file() and not default_path.is_file() else default_path
        )
    else:
        write_path = write_path.resolve()

    return project_root, roadmap_path, shipped_path, write_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate or update auto-populated high-level project dashboard."
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=None,
        help="Project root directory (default: git repo root)",
    )
    parser.add_argument(
        "--roadmap",
        type=Path,
        default=None,
        help="Path to roadmap.md (default: docs/roadmap.md)",
    )
    parser.add_argument(
        "--shipped",
        type=Path,
        default=None,
        help="Path to shipped.md (default: docs/shipped.md)",
    )
    parser.add_argument(
        "--write",
        nargs="?",
        const=DEFAULT_DASHBOARD_FILENAME,
        default=None,
        help="Write dashboard to DASHBOARD.md or specified path",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check whether target dashboard file is up to date (exit 0 if clean, 1 if drifted)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output metrics as JSON to stdout",
    )
    parser.add_argument(
        "--print",
        dest="print_md",
        action="store_true",
        help="Print generated markdown dashboard to stdout",
    )
    parser.add_argument(
        "--pack-summary",
        action="store_true",
        help="Print prompt for external AI to update canonical summary",
    )

    args = parser.parse_args(argv)

    # A bare --write means "the project's dashboard" (DASHBOARD.md, or the legacy
    # 01_roadmap.md) under --project-root. Resolving it against the working directory
    # instead wrote the dashboard into whichever folder the command ran from.
    write_target = Path(args.write) if args.write and args.write != DEFAULT_DASHBOARD_FILENAME else None
    project_root, roadmap_path, shipped_path, write_target = resolve_paths(
        args.project_root,
        args.roadmap,
        args.shipped,
        write_target,
    )

    try:
        metrics = collect_dashboard_metrics(
            roadmap_path=roadmap_path,
            shipped_path=shipped_path,
            project_root=project_root,
        )
    except Exception as exc:
        print(f"error: failed to collect dashboard metrics: {exc}", file=sys.stderr)
        return 1

    if args.pack_summary and summary is not None:
        summary_doc = summary.load_summary(project_root)
        prompt = summary.pack_summary_prompt(
            summary=summary_doc,
            project_name=project_root.name,
            metrics=metrics,
            recent_shipped=[],
            active_tasks=metrics.active_tasks,
            ready_tasks=metrics.ready_queue,
        )
        print(prompt)
        return 0

    if args.json:
        print(json.dumps(asdict(metrics), indent=2))
        return 0

    dashboard_md = generate_dashboard_markdown(metrics)

    if args.print_md:
        print(dashboard_md)
        return 0

    if args.check:
        is_clean = check_dashboard_file(write_target, dashboard_md)
        if is_clean:
            print(f"ok: {write_target.name} is synchronized with roadmap and shipped history.")
            return 0
        else:
            print(
                f"drift: {write_target.name} is out of date. Run 'python dashboard.py --write' to update.",
                file=sys.stderr,
            )
            return 1

    if args.write is not None:
        # Only the "Auto-generated on <time>" line would change: leave the file alone, so a
        # routing pass over an unchanged roadmap is a true no-op (no timestamp churn in git).
        if write_target.is_file() and check_dashboard_file(write_target, dashboard_md):
            print(f"unchanged: {write_target}")
            return 0
        update_or_create_dashboard_file(
            target_path=write_target,
            dashboard_md=dashboard_md,
            project_name=project_root.name,
        )
        print(f"updated: {write_target}")
        return 0

    # Default action if no flags provided: print to stdout
    print(dashboard_md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
