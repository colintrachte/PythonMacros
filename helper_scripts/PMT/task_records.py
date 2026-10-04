"""
task_records.py — Quest Board's domain task record and roadmap read model.

Owns task parsing, relationship derivation, and readiness views shared by the
Quest Board controller and task editor. It does not write roadmap files.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import route_tasks

HEADER_RE = re.compile(r"^- \[([ x])\]\s*\*\*(.+?)\*\*")
# A rough idea needs no bold: "- [ ] buy milk" is a task too (route_tasks' TASK_RE already
# treats any checkbox line as a task block). Use match_header(), not HEADER_RE, to read one.
PLAIN_HEADER_RE = re.compile(r"^- \[([ x])\]\s+(\S.*?)\s*$")


def match_header(line: str) -> re.Match | None:
    """A task header line: `- [ ] **text**` (anything may follow the bold) or a plain
    `- [ ] text`. group(1) is the checkbox mark, group(2) the header text, and end() is
    where a bold header's trailing text begins."""
    return HEADER_RE.match(line) or PLAIN_HEADER_RE.match(line)
# Splits a header (per roadmap.md's format convention) into its packed attributes:
# "Score <1-5> <medal> · Class <1-3> — <title>" -> score, title (class is already
# pulled separately via route_tasks.CLASS_RE; the medal glyph is matched generically
# and not trusted — the picker recomputes it from score via route_tasks._medal()).
HEADER_ATTR_RE = re.compile(
    r"^Score\s+(?P<score>[1-5])(?:\s+\S+)?\s*(?:·|-)\s*Class\s+"
    r"(?P<cls>[123](?:\s*/\s*[123])*)\s*—\s*(?P<title>.+)$"
)
# Any ## or ### heading line, used to tag each task with the section it falls under
# (e.g. "Upstream architecture study") so the picker's filter box can match on it —
# a task's own title often doesn't contain its section's theme word.
SECTION_RE = re.compile(r"^#{2,4}\s+(.+?)\s*$")
FILE_LIST_RE = re.compile(
    r"^\s+\*\*(Implement|Write|Context|Read|Evidence)"
    r"(?:\s+\([^*]*\))?:\*\*\s*(.+)",
    re.IGNORECASE,
)
ROUTE_VALUE_RE = re.compile(r"^\s*\*\*Route:\*\*\s*(.+?)\s*$")
CONTEXT_LOAD_VALUE_RE = re.compile(
    r"^\s*\*\*(?:Context Load|Effort):\*\*\s*(.+?)\s*$", re.IGNORECASE
)
EFFORT_VALUE_RE = CONTEXT_LOAD_VALUE_RE  # legacy import compatibility
CHARS_VALUE_RE = re.compile(r"^\s*\*\*Chars:\*\*\s*(.+?)\s*$")
FENCE_START_RE = re.compile(r"^\s*```text\s*$")
FENCE_END_RE = re.compile(r"^\s*```\s*$")


RAW_INTENT_SCHEMA_VERSION = 1
ASSIMILATION_REPORT_SCHEMA_VERSION = 1
ASSIMILATION_DISPOSITIONS = {
    "execute_now",
    "roadmap_task",
    "research_question",
    "duplicate",
    "discard",
}
RAW_INTENT_MAX_CHARS = 1_000_000


@dataclass(frozen=True)
class RawIntent:
    """Immutable author input awaiting repo-aware assimilation.

    Raw intent is evidence, not an executable task. The roadmap remains the only
    execution backlog.
    """

    id: str
    captured_at: str
    source_name: str
    sha256: str
    text: str


def capture_raw_intent(intent_dir: Path, text: str, source_name: str = "typed input") -> Path:
    """Persist one raw text or review submission without requiring task metadata."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    if not normalized.strip():
        raise ValueError("raw intent is empty")
    if len(normalized) > RAW_INTENT_MAX_CHARS:
        raise ValueError(f"raw intent exceeds the {RAW_INTENT_MAX_CHARS:,}-character limit")
    source = source_name.strip() or "typed input"
    if "\n" in source or "\r" in source:
        raise ValueError("source name must fit on one line")

    intent_id = f"intent_{uuid.uuid4().hex}"
    payload = {
        "schema_version": RAW_INTENT_SCHEMA_VERSION,
        "id": intent_id,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "source_name": source,
        "sha256": hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
        "text": normalized,
    }
    intent_dir.mkdir(parents=True, exist_ok=True)
    path = intent_dir / f"{intent_id}.json"
    route_tasks._atomic_write(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return path


def load_raw_intent(path: Path) -> RawIntent:
    """Load and integrity-check one immutable raw-intent record."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != RAW_INTENT_SCHEMA_VERSION:
        raise ValueError("unsupported raw-intent schema")
    required = ("id", "captured_at", "source_name", "sha256", "text")
    if any(not isinstance(payload.get(key), str) for key in required):
        raise ValueError("raw-intent record has missing or invalid fields")
    digest = hashlib.sha256(payload["text"].encode("utf-8")).hexdigest()
    if digest != payload["sha256"]:
        raise ValueError("raw-intent content hash does not match")
    if path.stem != payload["id"]:
        raise ValueError("raw-intent filename does not match its ID")
    return RawIntent(
        id=payload["id"],
        captured_at=payload["captured_at"],
        source_name=payload["source_name"],
        sha256=payload["sha256"],
        text=payload["text"],
    )


def build_assimilation_prompt(intent: RawIntent) -> str:
    """Build the repo-aware review request for one raw-intent record."""
    return f"""Assimilate this raw author input against the CURRENT repository.

Read the repository's own judgment docs (AGENTS.md / CLAUDE.md, and a CHARTER.md or
README.md if present), docs/roadmap.md, docs/shipped.md, relevant research/contracts,
and the owning code/tests. Validate every observation, deduplicate it against existing work,
and return JSON only using schema_version 1. Do not edit files or implement anything in this
assimilation pass. Raw input never authorizes implementation.

Required top-level keys:
- source_id: {intent.id!r}
- source_sha256: {intent.sha256!r}
- coverage_complete: true only after every distinct finding has a disposition
- implementation_authorized: false
- findings: an array of objects

Every finding requires summary, evidence (an exact non-empty excerpt from the raw input),
disposition, and rationale. disposition is one of: execute_now, roadmap_task,
research_question, duplicate, discard. duplicate also requires duplicate_of, naming an
existing task ID or authoritative owner. section must name an existing roadmap heading
(its text, with or without the leading '#' marks); do not invent new sections.
roadmap_task requires task with title, section,
priority (1-5), class (1-3), current_owner, consequence, outcome, verification, acceptance
(non-empty array), implement (array), context (array), and optional blocked_by. Class 2/3
tasks require approval_required=true; Class 3 also requires safety_review_required=true and
hardware_evidence_required=true or false. Proposed tasks remain Draft and must be bounded,
non-duplicate work. Research questions remain in the report; they are not executable tasks.

RAW INPUT ({intent.source_name}):
---
{intent.text}
---
"""


def parse_assimilation_report(
    report_text: str,
    intent: RawIntent,
    existing_tasks: list[Task],
) -> dict:
    """Validate a repo-aware assimilation report before it can affect the roadmap."""
    try:
        report = json.loads(report_text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"assimilation report is not valid JSON: {exc}") from exc
    if report.get("schema_version") != ASSIMILATION_REPORT_SCHEMA_VERSION:
        raise ValueError("unsupported assimilation-report schema")
    if report.get("source_id") != intent.id or report.get("source_sha256") != intent.sha256:
        raise ValueError("assimilation report does not match the captured raw intent")
    if report.get("coverage_complete") is not True:
        raise ValueError("assimilation report must explicitly cover every finding")
    if report.get("implementation_authorized") is not False:
        raise ValueError("raw intent cannot authorize implementation")
    findings = report.get("findings")
    if not isinstance(findings, list) or not findings:
        raise ValueError("assimilation report must contain at least one finding")

    existing_ids = {task.id for task in existing_tasks if task.id}
    existing_titles = {split_header(task.header)[1].strip().casefold() for task in existing_tasks}
    proposed_titles: set[str] = set()
    for index, finding in enumerate(findings, start=1):
        prefix = f"finding {index}"
        if not isinstance(finding, dict):
            raise ValueError(f"{prefix} must be an object")
        for key in ("summary", "evidence", "rationale", "disposition"):
            if not isinstance(finding.get(key), str) or not finding[key].strip():
                raise ValueError(f"{prefix} requires non-empty {key}")
        if finding["evidence"] not in intent.text:
            raise ValueError(f"{prefix} evidence is not an exact raw-input excerpt")
        disposition = finding["disposition"]
        if disposition not in ASSIMILATION_DISPOSITIONS:
            raise ValueError(f"{prefix} has unknown disposition {disposition!r}")
        if disposition == "duplicate" and not str(finding.get("duplicate_of", "")).strip():
            raise ValueError(f"{prefix} duplicate disposition requires duplicate_of")
        if disposition != "roadmap_task":
            continue

        task = finding.get("task")
        if not isinstance(task, dict):
            raise ValueError(f"{prefix} roadmap disposition requires a task object")
        scalar_fields = (
            "title",
            "section",
            "current_owner",
            "consequence",
            "outcome",
            "verification",
        )
        for key in scalar_fields:
            if not isinstance(task.get(key), str) or not task[key].strip():
                raise ValueError(f"{prefix} task requires non-empty {key}")
        if task.get("priority") not in range(1, 6):
            raise ValueError(f"{prefix} task priority must be 1-5")
        if task.get("class") not in range(1, 4):
            raise ValueError(f"{prefix} task class must be 1-3")
        for key in ("acceptance", "implement", "context"):
            values = task.get(key)
            if not isinstance(values, list) or (key == "acceptance" and not values):
                raise ValueError(f"{prefix} task {key} must be an array")
            if any(not isinstance(value, str) or not value.strip() for value in values):
                raise ValueError(f"{prefix} task {key} contains an empty value")
        if not task["implement"] and not task["context"]:
            raise ValueError(f"{prefix} task must name a current implementation or context owner")
        blocked_by = task.get("blocked_by", [])
        if not isinstance(blocked_by, list) or any(
            dependency not in existing_ids for dependency in blocked_by
        ):
            raise ValueError(f"{prefix} task has an unknown blocked_by ID")
        normalized_title = task["title"].strip().casefold()
        if normalized_title in existing_titles or normalized_title in proposed_titles:
            raise ValueError(f"{prefix} task duplicates an existing or proposed title")
        proposed_titles.add(normalized_title)
        task_class = task["class"]
        if task_class >= 2 and task.get("approval_required") is not True:
            raise ValueError(f"{prefix} Class {task_class} task must require author approval")
        if task_class == 3:
            if task.get("safety_review_required") is not True:
                raise ValueError(f"{prefix} Class 3 task must require safety review")
            if not isinstance(task.get("hardware_evidence_required"), bool):
                raise ValueError(
                    f"{prefix} Class 3 task must decide whether hardware evidence is required"
                )
    return report


def assimilation_task_fields(report: dict) -> list[dict]:
    """Convert validated roadmap dispositions into Draft task-editor field dictionaries."""
    fields = []
    for finding in report["findings"]:
        if finding["disposition"] != "roadmap_task":
            continue
        task = finding["task"]
        rationale = (
            f"Owner: {task['current_owner'].strip()}. Consequence: {task['consequence'].strip()}"
        )
        fields.append(
            {
                "score": str(task["priority"]),
                "task_class": str(task["class"]),
                "title": task["title"].strip(),
                # Sections are addressed by heading text, not by the "## " markup. A
                # report naturally writes either form, so accept both rather than
                # failing deep inside insert_task_block with a "not found" error.
                "section": task["section"].strip().lstrip("#").strip(),
                "id": f"task_{uuid.uuid4().hex}",
                "status": "Draft",
                "outcome": task["outcome"].strip(),
                "rationale": rationale,
                "acceptance_conditions": [value.strip() for value in task["acceptance"]],
                "acceptance_evidence": [task["verification"].strip()],
                "work_mode": "",
                "execution_mode": "",
                "execution_size": "",
                "uncertainty": "",
                "capabilities": [],
                "constraints": [],
                "protected_behaviors": [],
                "dependencies": list(task.get("blocked_by", [])),
                "preferred_after": [],
                "parents": [],
                "supersedes": [],
                "related": [],
                "file_fields": {
                    "Implement": list(task["implement"]),
                    "Context": list(task["context"]),
                    "Write": [],
                    "Read": [],
                    "Evidence": [],
                },
                "manual_route": None,
                "pack_override": False,
                "body": finding["rationale"].strip(),
                "is_fenced": False,
            }
        )
    return fields


def _raw_intent_files(intent_dir: Path) -> list[Path]:
    """Every captured intent record in intent_dir.

    Reports are stored beside their intent as `<intent_id>.report.json`, which the
    `intent_*.json` glob also matches — so filter them out by suffix, or a recorded
    report gets listed as an intent awaiting one.
    """
    if not intent_dir.is_dir():
        return []
    return [
        path for path in intent_dir.glob("intent_*.json") if not path.name.endswith(".report.json")
    ]


def latest_raw_intent_path(intent_dir: Path) -> Path | None:
    """Most recently captured raw-intent record, or None when none exist."""
    candidates = _raw_intent_files(intent_dir)
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def pending_raw_intents(intent_dir: Path) -> list[Path]:
    """Captured intents that have no recorded assimilation report yet, oldest first."""
    pending = [
        path
        for path in _raw_intent_files(intent_dir)
        if not path.with_suffix(".report.json").exists()
    ]
    return sorted(pending, key=lambda p: p.stat().st_mtime)


def split_header(header: str) -> tuple[str, str]:
    """Break a task header into (score, title), for table columns."""
    m = HEADER_ATTR_RE.match(header)
    if not m:
        return "", header
    return m.group("score"), m.group("title")


@dataclass
class Task:
    header: str
    task_class: str
    id: str = ""
    status: str = ""
    section: str = ""  # nearest preceding ##/### heading this task falls under
    roadmap_order: int = 0  # authored order is the default recommended execution order
    work_mode: str = ""
    route: str = "?"
    context_load: str = "?"
    files: list[Path] = field(default_factory=list)  # resolved, existing paths, in file-list order
    missing: list[str] = field(
        default_factory=list
    )  # raw backtick strings that didn't resolve to a file
    prompt: str = ""  # extracted ```text block body, if the item has one
    start: int = -1  # index into the parsed lines[] of this task's header
    end: int = -1  # exclusive end index (route_tasks.scan_block_end)
    dependencies: list[str] = field(default_factory=list)
    preferred_after: list[str] = field(default_factory=list)
    parents: list[str] = field(default_factory=list)
    supersedes: list[str] = field(default_factory=list)
    related: list[str] = field(default_factory=list)
    blocks: list[str] = field(default_factory=list)
    preferred_before: list[str] = field(default_factory=list)
    children: list[str] = field(default_factory=list)
    superseded_by: list[str] = field(default_factory=list)
    readiness_gaps: list[str] = field(default_factory=list)
    artifacts: list[dict[str, str]] = field(default_factory=list)

    @property
    def effort(self) -> str:
        """Read-compatible alias for callers migrating from generated Effort."""
        return self.context_load


def parse_tasks(lines: list[str], root: Path) -> list[Task]:
    """Walk freshly-routed roadmap.md lines into open Task objects."""
    tasks = []
    i = 0
    section = ""
    while i < len(lines):
        sm = SECTION_RE.match(lines[i])
        if sm:
            section = sm.group(1)
            i += 1
            continue

        m = match_header(lines[i])
        if not m or m.group(1) == "x":
            i += 1
            continue

        task_class_value = route_tasks.header_class(lines[i])
        task = Task(
            header=m.group(2),
            task_class=task_class_value or "?",
            section=section,
            roadmap_order=len(tasks) + 1,
            start=i,
        )

        # Shared fence-aware block scan (route_tasks.scan_block_end) — so this parser
        # and route_tasks._process()/find_task_block() can't disagree about where one
        # task ends and the next begins.
        j = route_tasks.scan_block_end(lines, i + 1)
        task.end = j
        block = lines[i + 1 : j]
        relationships = route_tasks.task_relationships_of(block)
        task.dependencies = relationships["dependencies"]
        task.preferred_after = relationships["preferred_after"]
        task.parents = relationships["parents"]
        task.supersedes = relationships["supersedes"]
        task.related = relationships["related"]

        seen = set()
        in_fence = False
        fence_lines = []
        body_lines = []
        for bl in block:
            idm = route_tasks.ID_RE.match(bl)
            if idm:
                task.id = idm.group(1)
                continue
            statusm = route_tasks.STATUS_RE.match(bl)
            if statusm:
                task.status = route_tasks.task_status_of([bl]) or ""
                continue
            work_mode_match = route_tasks.WORK_MODE_RE.match(bl)
            if work_mode_match:
                task.work_mode = work_mode_match.group(1)
                continue
            rm = ROUTE_VALUE_RE.match(bl)
            if rm:
                task.route = rm.group(1)
                continue
            load_match = CONTEXT_LOAD_VALUE_RE.match(bl)
            if load_match:
                task.context_load = load_match.group(1)
                continue
            if CHARS_VALUE_RE.match(bl):
                continue
            fm = FILE_LIST_RE.match(bl)
            if fm:
                for raw in route_tasks.BACKTICK_RE.findall(fm.group(2)):
                    task.artifacts.append({"role": fm.group(1).lower(), "path": raw})
                files, missing = route_tasks.resolve_file_list(fm.group(2), root)
                for p in files:
                    key = p.as_posix()
                    if key in seen:
                        continue
                    seen.add(key)
                    task.files.append(p)
                for raw in missing:
                    if raw in seen:
                        continue
                    seen.add(raw)
                    task.missing.append(raw)
                continue
            if FENCE_START_RE.match(bl):
                in_fence = True
                continue
            if in_fence and FENCE_END_RE.match(bl):
                in_fence = False
                continue
            if in_fence:
                fence_lines.append(bl)
            else:
                body_lines.append(bl)

        if not task.id:
            task.id = route_tasks.task_id_of(lines[i:j]) or ""

        # A fenced ```text block (a ready-made, model-facing prompt) takes priority when
        # present; most items have no fence at all, so fall back to the plain description
        # paragraph under the header — otherwise those tasks packed with an empty prompt box.
        task.prompt = "".join(fence_lines).strip()
        if not task.prompt:
            # header_tail is the word-wrapped start of the same sentence the body
            # continues (the roadmap's line-wrap convention splits mid-sentence, not
            # at a paragraph boundary) — join with a space, not a blank line, or it
            # reads as two sentence fragments instead of one.
            header_tail = lines[i][m.end() :].strip(" \t\n-—")
            desc = "".join(body_lines).strip()
            task.prompt = f"{header_tail} {desc}".strip() if header_tail else desc
        tasks.append(task)
        i = j
    return tasks


def derive_reverse_relationships(tasks: list[Task]) -> None:
    """Populate reverse and symmetric in-memory edges from authored forward edges."""
    by_id = {task.id: task for task in tasks if task.id}
    for task in tasks:
        task.blocks = []
        task.preferred_before = []
        task.children = []
        task.superseded_by = []
        task.related = list(dict.fromkeys(task.related))
    for task in tasks:
        if not task.id:
            continue
        for relationship_field, reverse in (
            ("dependencies", "blocks"),
            ("preferred_after", "preferred_before"),
            ("parents", "children"),
            ("supersedes", "superseded_by"),
        ):
            for target_id in getattr(task, relationship_field):
                target = by_id.get(target_id)
                if target is not None and task.id not in getattr(target, reverse):
                    getattr(target, reverse).append(task.id)
        for target_id in list(task.related):
            target = by_id.get(target_id)
            if target is not None and task.id not in target.related:
                target.related.append(task.id)


def ready_tasks(tasks: list[Task], status_map: dict[str, str]) -> list[Task]:
    """Return explicitly Ready tasks whose blocking dependencies are all Shipped."""
    return [
        task
        for task in tasks
        if task.status == "Ready"
        and not task.readiness_gaps
        and all(status_map.get(task_id) == "Shipped" for task_id in task.dependencies)
    ]


def blocker_summary(task: Task, tasks_by_id: dict[str, Task], status_map: dict[str, str]) -> str:
    """Describe hard blockers, readiness gaps, and soft ordering preferences."""
    blockers = []
    for dependency in task.dependencies:
        status = status_map.get(dependency)
        if status == "Shipped":
            continue
        target = tasks_by_id.get(dependency)
        label = split_header(target.header)[1] if target is not None else dependency
        blockers.append(f"{label} ({status or 'missing'})")
    blockers.extend(
        gap.removesuffix(".")
        for gap in task.readiness_gaps
        if not gap.startswith("Dependency ") and gap != "A Blocked task cannot be Ready."
    )
    for predecessor in task.preferred_after:
        if status_map.get(predecessor) == "Shipped":
            continue
        target = tasks_by_id.get(predecessor)
        label = split_header(target.header)[1] if target is not None else predecessor
        blockers.append(f"prefer after {label} ({status_map.get(predecessor) or 'missing'})")
    if blockers:
        return "; ".join(blockers)
    if task.status == "Blocked":
        return "Blocked status has no dependency/reason"
    if task.status in {"Draft", "Defined"}:
        return "No readiness gap — promote to Ready"
    return ""


def task_execution_constraints(
    tasks: list[Task], status_map: dict[str, str]
) -> tuple[list[str], list[str]]:
    """Return (hard, soft) execution warnings: not-Ready status or unshipped hard
    prerequisites, and unmet ``Prefer after`` ordering preferences.

    Both are advisory. PMT never refuses to pack, send or save because of them — the
    maintainer decides; callers show them as heads-ups next to the result. The split
    only says how strongly the roadmap recommends waiting.
    """
    blockers = []
    preferences = []
    for task in tasks:
        _, title = split_header(task.header)
        hard_reasons = []
        if task.status != "Ready":
            hard_reasons.append(f"status is {task.status or 'Legacy'}, not Ready")
        open_dependencies = [
            dependency
            for dependency in task.dependencies
            if status_map.get(dependency) != "Shipped"
        ]
        if open_dependencies:
            hard_reasons.append(f"{len(open_dependencies)} hard prerequisite(s) not Shipped")
        if hard_reasons:
            blockers.append(f"{title}: {', '.join(hard_reasons)}")

        open_preferences = [
            predecessor
            for predecessor in task.preferred_after
            if status_map.get(predecessor) != "Shipped"
        ]
        if open_preferences:
            preferences.append(
                f"{title}: preferably follows {len(open_preferences)} unshipped task(s)"
            )
    return blockers, preferences


def task_order_advisories(tasks: list[Task], status_map: dict[str, str]) -> list[str]:
    """Read-compatible wrapper returning both hard and soft execution warnings."""
    blockers, preferences = task_execution_constraints(tasks, status_map)
    return blockers + preferences


# ── Editable field view and readiness (shared by PMT1's editor and PMT2) ──
#
# Moved here from task_editor.py so PMT2 — whose backend may not import tkinter — can
# use the one canonical readiness rule instead of carrying a simplified fork of it.
# task_editor re-exports every name, so existing imports keep working.

FILE_FIELD_LABELS = ("Implement", "Context", "Write", "Read", "Evidence")
FILE_FIELD_DISPLAY = {
    "Implement": "Mutable",
    "Context": "Input",
    "Write": "Output",
    "Read": "Input (additional)",
    "Evidence": "Evidence",
}
_LABEL_CANON = {label.lower(): label for label in FILE_FIELD_LABELS}
# A file-list line using a parenthetical suffix, e.g. "**Implement (Class 3 — ...):**"
# (see ROADMAP.template.md's format convention) -- a real, exercised case this editor's
# flat per-label model can't preserve; parse_task_fields() flags it so the dialog can warn
# instead of silently dropping the annotation on save.
FIELD_SUFFIX_RE = re.compile(
    r"^\s+\*\*(?:Implement|Write|Context|Read|Evidence)\s*\(", re.IGNORECASE
)
MANUAL_ROUTE_SUFFIX_RE = re.compile(r"^(.*?)\s*\(manual\)\s*$")
SECTION_BOUNDARY_RE = re.compile(r"^#{2,4}\s|^---\s*$")
TEXT_FIELD_RE = re.compile(
    r"^\s+\*\*(Outcome|Rationale|Acceptance|Expected evidence|Work mode|Execution mode|Execution size|Uncertainty|"
    r"Capability|Constraint|Protected behavior|Dependency|Blocked by|Prefer after|Parent|Supersedes|Related):\*\*\s*(.*)$",
    re.IGNORECASE,
)
TEXT_FIELD_KEYS = {
    "outcome": "outcome",
    "rationale": "rationale",
    "acceptance": "acceptance_conditions",
    "expected evidence": "acceptance_evidence",
    "work mode": "work_mode",
    "execution mode": "execution_mode",
    "execution size": "execution_size",
    "uncertainty": "uncertainty",
    "capability": "capabilities",
    "constraint": "constraints",
    "protected behavior": "protected_behaviors",
    "dependency": "dependencies",
    "blocked by": "dependencies",
    "prefer after": "preferred_after",
    "parent": "parents",
    "supersedes": "supersedes",
    "related": "related",
}
LIST_TASK_FIELDS = {
    "acceptance_conditions",
    "acceptance_evidence",
    "capabilities",
    "constraints",
    "protected_behaviors",
    "dependencies",
    "preferred_after",
    "parents",
    "supersedes",
    "related",
}

PACK_OVERRIDE_RE = re.compile(r"^\s+\*\*Pack Override:\*\*\s*(.*)$", re.IGNORECASE)
READY_OVERRIDE_RE = re.compile(r"^\s+\*\*Ready Override:\*\*\s*(.*)$", re.IGNORECASE)


def parse_task_fields(block_lines: list[str]) -> dict:
    """Parse a task block (header line first, e.g. roadmap_lines[task.start:task.end])
    into an editable field-dict -- the inverse of build_task_lines(). Unlike
    parse_tasks()/Task.files, file-list values are kept as raw backtick strings bucketed
    per label rather than resolved Paths, since **Write:** targets and `<name>/...`
    external refs often don't exist on disk yet and still need to round-trip through the
    editor. Returns {score, task_class, title, body, is_fenced, file_fields, manual_route,
    has_field_suffix} -- callers fill in "section" themselves (Task.section, not
    derivable from the block alone)."""
    header_m = match_header(block_lines[0])
    attr_m = HEADER_ATTR_RE.match(header_m.group(2)) if header_m else None
    class_m = route_tasks.CLASS_RE.search(block_lines[0])

    file_fields = {label: [] for label in FILE_FIELD_LABELS}
    task_id = None
    status = None
    logical = {
        "outcome": "",
        "rationale": "",
        "acceptance_conditions": [],
        "acceptance_evidence": [],
        "work_mode": "",
        "execution_mode": "",
        "execution_size": "",
        "uncertainty": "",
        "capabilities": [],
        "constraints": [],
        "protected_behaviors": [],
        "dependencies": [],
        "preferred_after": [],
        "parents": [],
        "supersedes": [],
        "related": [],
    }
    manual_route = None
    has_field_suffix = False
    in_fence = False
    fence_lines = []
    body_lines = []
    pack_override = False

    for bl in block_lines[1:]:
        if PACK_OVERRIDE_RE.match(bl) or READY_OVERRIDE_RE.match(bl):
            m = PACK_OVERRIDE_RE.match(bl) or READY_OVERRIDE_RE.match(bl)
            val = m.group(1).strip().lower()
            if val in ("true", "yes", "1", "forced", "on") or val == "" or "true" in val:
                pack_override = True
            continue
        idm = route_tasks.ID_RE.match(bl)
        if idm:
            task_id = idm.group(1)
            continue
        statusm = route_tasks.STATUS_RE.match(bl)
        if statusm:
            status = route_tasks.task_status_of([bl])
            continue
        tm = TEXT_FIELD_RE.match(bl)
        if tm:
            key = TEXT_FIELD_KEYS[tm.group(1).lower()]
            value = tm.group(2).strip()
            if key in LIST_TASK_FIELDS:
                if key in {
                    "dependencies",
                    "preferred_after",
                    "parents",
                    "supersedes",
                    "related",
                }:
                    logical[key].extend(
                        reference for reference in re.split(r"\s*·\s*", value) if reference
                    )
                else:
                    logical[key].append(value)
            else:
                logical[key] = value
            continue
        rm = ROUTE_VALUE_RE.match(bl)
        if rm:
            mm = MANUAL_ROUTE_SUFFIX_RE.match(rm.group(1))
            if mm and rm.group(1).endswith("(manual)"):
                manual_route = mm.group(1).strip()
            continue
        if (
            route_tasks.EFFORT_RE.match(bl)
            or route_tasks.CONTEXT_LOAD_RE.match(bl)
            or CHARS_VALUE_RE.match(bl)
        ):
            continue
        fm = FILE_LIST_RE.match(bl)
        if fm:
            if FIELD_SUFFIX_RE.match(bl):
                has_field_suffix = True
            label = _LABEL_CANON[fm.group(1).lower()]
            file_fields[label].extend(route_tasks.BACKTICK_RE.findall(fm.group(2)))
            continue
        if FENCE_START_RE.match(bl):
            in_fence = True
            continue
        if in_fence and FENCE_END_RE.match(bl):
            in_fence = False
            continue
        if in_fence:
            fence_lines.append(bl)
        else:
            body_lines.append(bl)

    fenced_body = "".join(fence_lines).strip()
    is_fenced = bool(fenced_body)
    if is_fenced:
        body = fenced_body
    else:
        # header_tail mirrors parse_tasks()'s own fallback (see its comment above) --
        # build_task_lines() never emits one, so on a round-trip this is always "".
        header_tail = block_lines[0][header_m.end() :].strip(" \t\n-—") if header_m else ""
        desc = "".join(body_lines).strip()
        body = f"{header_tail} {desc}".strip() if header_tail else desc

    return {
        "score": attr_m.group("score") if attr_m else "",
        "task_class": class_m.group(1) if class_m else "",
        "title": (attr_m.group("title") if attr_m else header_m.group(2) if header_m else ""),
        "body": body,
        "is_fenced": is_fenced,
        "file_fields": file_fields,
        "manual_route": manual_route,
        "has_field_suffix": has_field_suffix,
        "id": task_id,
        "status": status,
        "pack_override": pack_override,
        **logical,
    }


def readiness_diagnostics(fields: dict, root: Path, task_status_map: dict[str, str] | None = None):
    """Return every readiness gap. Drafts may be saved with gaps; Ready may not.
    When pack_override is set, no gaps are reported — task is considered ready for packing."""
    if fields.get("pack_override"):
        return []
    gaps = []
    if not fields.get("outcome", "").strip():
        gaps.append("Outcome is required before Ready.")
    if not any(value.strip() for value in fields.get("acceptance_conditions", [])):
        gaps.append("At least one acceptance condition is required before Ready.")
    if not any(value.strip() for value in fields.get("acceptance_evidence", [])):
        gaps.append("Expected acceptance evidence is required before Ready.")
    if fields.get("work_mode") == "Forge + Steward" and not any(
        value.strip() for value in fields.get("protected_behaviors", [])
    ):
        gaps.append("Forge + Steward requires at least one protected behavior.")
    for label in ("Implement", "Context", "Read"):
        for ref in fields.get("file_fields", {}).get(label, []):
            files, missing = route_tasks.resolve_file_list(f"`{ref}`", root)
            if not files and missing:
                gaps.append(
                    f"Required {FILE_FIELD_DISPLAY[label].lower()} artifact is unresolved: {ref}"
                )
    if fields.get("status") == "Blocked":
        gaps.append("A Blocked task cannot be Ready.")
    if task_status_map is not None:
        for dependency in fields.get("dependencies", []):
            dep_status = task_status_map.get(dependency)
            if dep_status is None:
                gaps.append(f"Dependency does not resolve: {dependency}")
            elif dep_status != "Shipped":
                gaps.append(f"Dependency is not Shipped: {dependency} ({dep_status})")
    return gaps


def derive_task_readiness(
    tasks: list[Task], lines: list[str], root: Path, status_map: dict[str, str]
) -> None:
    """Attach the editor's mechanical readiness diagnostics to parsed tasks.

    The result is display/filter state only. Authored status and relationship fields remain
    untouched, so Quest Board can explain an inconsistency without silently rewriting it.
    """
    for task in tasks:
        if not task.status:
            task.readiness_gaps = []
            continue
        fields = parse_task_fields(lines[task.start : task.end])
        task.readiness_gaps = readiness_diagnostics(fields, root, status_map)
        task.pack_override = bool(fields.get("pack_override"))


def task_statuses(lines: list[str]) -> dict[str, str]:
    """Map permanent IDs to explicit status, treating checked history as Shipped."""
    result = {}
    i = 0
    while i < len(lines):
        match = route_tasks.TASK_RE.match(lines[i])
        if not match:
            i += 1
            continue
        end = route_tasks.scan_block_end(lines, i + 1)
        task_id = route_tasks.task_id_of(lines[i:end])
        if task_id:
            result[task_id] = (
                "Shipped"
                if match.group(1) == "x"
                else route_tasks.task_status_of(lines[i:end]) or "Legacy"
            )
        i = end
    return result
