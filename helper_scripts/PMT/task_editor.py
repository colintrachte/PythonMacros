"""
task_editor.py — Quest Board task editing mechanics and diff-gated Tk dialogs.

The pure helpers build candidate roadmap content without writing. The dialog's
apply boundary delegates the guarded atomic write to route_tasks.write_roadmap().
"""

import difflib
import sys
import tkinter as tk
import uuid
from pathlib import Path
from tkinter import filedialog, scrolledtext, ttk
from typing import TYPE_CHECKING

import gui_theme
import route_tasks
from task_records import (
    FILE_FIELD_DISPLAY,
    FILE_FIELD_LABELS,
    SECTION_BOUNDARY_RE,
    SECTION_RE,
    Task,
    parse_task_fields,
    readiness_diagnostics,
)

# The field view and readiness rule moved to task_records (tk-free, shared with PMT2);
# these names stay importable from here for existing callers.
from task_records import derive_task_readiness as derive_task_readiness
from task_records import task_statuses as task_statuses

if TYPE_CHECKING:
    from pack_task import App


def _wrap_with_parent(label, parent, inset=0):
    """Keep a label's wrap length aligned with the width its parent actually receives."""

    def resize(event):
        label.configure(wraplength=max(120, event.width - inset))

    parent.bind("<Configure>", resize, add="+")


# ── task editor: pure parse/build/splice helpers (no Tkinter) ──
#
# These back TaskEditorDialog's Save path. Kept free of Tkinter so they're unit-testable
# headlessly (see tests/test_task_editor.py) -- this repo's own REVIEW_TIERS.md Class 3
# rule for any docs/roadmap.md write path requires a round-trip test, and a function tied
# to live widgets can't be driven without a display.


def task_field_suggestions(sources: list[list[str]]) -> dict[str, tuple[str, ...]]:
    """Collect reusable field-level suggestions from current and shipped task records.

    Values remain suggestions rather than defaults: historical task-specific details may
    be stale, while an editable combobox still makes recurring phrasing cheap to reuse.
    """
    suggestions = {"title": [], "outcome": [], "rationale": []}
    for lines in sources:
        i = 0
        while i < len(lines):
            if not route_tasks.TASK_RE.match(lines[i]):
                i += 1
                continue
            end = route_tasks.scan_block_end(lines, i + 1)
            fields = parse_task_fields(lines[i:end])
            for key in suggestions:
                value = fields[key].strip()
                if value and value not in suggestions[key]:
                    suggestions[key].append(value)
            i = end
    return {key: tuple(values) for key, values in suggestions.items()}


def build_task_lines(fields: dict) -> list[str]:
    """Render a field-dict (see parse_task_fields()) into a well-formed task block ending
    in exactly one blank line. Never emits Context Load/Chars, and emits Route only when
    a manual override is set -- those stay generated, left to the App's
    refresh_routes()/_load_tasks() pipeline on the next reload.

    Known simplification: hand-authored items in this repo's own docs/roadmap.md often
    keep the description as an inline continuation of the header line; this always emits
    it as a separate paragraph instead. parse_tasks() concatenates header_tail + body
    either way, so this is cosmetic re-wrapping on save, not a semantic change."""
    medal = route_tasks._medal(fields["score"])
    lines = [
        f"- [ ] **Score {fields['score']} {medal} · Class {fields['task_class']} "
        f"— {fields['title']}**\n",
    ]
    if fields.get("id"):
        lines.append(f"  **ID:** {fields['id']}\n")
    if fields.get("status"):
        lines.append(f"  **Status:** {fields['status']}\n")
    if fields.get("pack_override"):
        lines.append("  **Pack Override:** true\n")
    for label, key in (("Outcome", "outcome"), ("Rationale", "rationale")):
        if fields.get(key):
            lines.append(f"  **{label}:** {fields[key].strip()}\n")
    for label, key in (
        ("Acceptance", "acceptance_conditions"),
        ("Expected evidence", "acceptance_evidence"),
    ):
        for value in fields.get(key, []):
            if value.strip():
                lines.append(f"  **{label}:** {value.strip()}\n")
    if fields.get("execution_mode"):
        lines.append(f"  **Execution mode:** {fields['execution_mode'].strip()}\n")
    if fields.get("work_mode"):
        lines.append(f"  **Work mode:** {fields['work_mode'].strip()}\n")
    if fields.get("execution_size"):
        lines.append(f"  **Execution size:** {fields['execution_size'].strip()}\n")
    if fields.get("uncertainty"):
        lines.append(f"  **Uncertainty:** {fields['uncertainty'].strip()}\n")
    for label, key in (
        ("Capability", "capabilities"),
        ("Constraint", "constraints"),
        ("Protected behavior", "protected_behaviors"),
        ("Blocked by", "dependencies"),
        ("Prefer after", "preferred_after"),
        ("Parent", "parents"),
        ("Supersedes", "supersedes"),
        ("Related", "related"),
    ):
        for value in fields.get(key, []):
            if value.strip():
                lines.append(f"  **{label}:** {value.strip()}\n")
    lines.append("\n")

    for label in FILE_FIELD_LABELS:
        paths = fields["file_fields"].get(label) or []
        if paths:
            joined = " · ".join(f"`{p}`" for p in paths)
            lines.append(f"  **{label}:** {joined}\n")
    if fields.get("manual_route"):
        lines.append(f"  **Route:** {fields['manual_route']} (manual)\n")

    body = (fields.get("body") or "").strip()
    if body:
        lines.append("\n")
        if fields.get("is_fenced"):
            lines.append("  ```text\n")
            for bline in body.splitlines():
                lines.append(f"  {bline}\n" if bline else "\n")
            lines.append("  ```\n")
        else:
            for bline in body.splitlines():
                lines.append(f"  {bline}\n" if bline else "\n")
    lines.append("\n")
    return lines


def validate_task_fields(
    fields: dict, existing_ids: set[str] | None = None, allow_empty_files: bool = False
) -> str | None:
    """Save-button validation, per ROADMAP.template.md's format convention. Returns the
    first violation's user-facing message, or None if the fields are savable.

    When pack_override or allow_empty_files is set, minimal structural checks remain —
    file list etc are allowed to be missing so you can quickly capture draft tasks.
    """
    if fields.get("pack_override"):
        if not fields.get("title", "").strip():
            return "Title cannot be empty (even with pack override)."
        if fields.get("score") not in {"1", "2", "3", "4", "5"}:
            return "Score must be 1-5."
        if fields.get("task_class") not in {"1", "2", "3"}:
            return "Class must be 1-3."
        if not fields.get("section", "").strip():
            return "Choose a section to file this task under."
        task_id = fields.get("id")
        if task_id and not route_tasks.TASK_ID_RE.fullmatch(task_id):
            return "ID must be task_ followed by 32 lowercase hexadecimal characters."
        if task_id and existing_ids is not None and task_id in existing_ids:
            return f"Task ID {task_id} already exists."
        return None

    if not fields.get("title", "").strip():
        return "Title cannot be empty."
    if fields.get("score") not in {"1", "2", "3", "4", "5"}:
        return "Score must be 1-5."
    if fields.get("task_class") not in {"1", "2", "3"}:
        return "Class must be 1-3."
    if not fields.get("section", "").strip():
        return "Choose a section to file this task under."
    task_id = fields.get("id")
    if task_id and not route_tasks.TASK_ID_RE.fullmatch(task_id):
        return "ID must be task_ followed by 32 lowercase hexadecimal characters."
    if task_id and existing_ids is not None and task_id in existing_ids:
        return f"Task ID {task_id} already exists."
    status = fields.get("status")
    # Status is free-form: a leading canonical word drives routing/unblocking,
    # anything else is just an author note. Only Shipped is reserved.
    if status and status.strip().casefold().startswith("shipped"):
        return "Use Mark Complete to move a task into Shipped history."
    work_mode = fields.get("work_mode", "")
    if work_mode and work_mode not in route_tasks.WORK_MODES:
        return "Work mode must be Forge, Steward, or Forge + Steward."
    for relationship_field in (
        "dependencies",
        "preferred_after",
        "parents",
        "supersedes",
        "related",
    ):
        for reference in fields.get(relationship_field, []):
            if not route_tasks.TASK_ID_RE.fullmatch(reference):
                label = relationship_field.replace("_", " ").title()
                return f"{label} reference {reference!r} is invalid."
            if reference == task_id:
                return f"A task cannot reference itself in {relationship_field.replace('_', ' ')}."
    if not allow_empty_files and not any(
        fields.get("file_fields", {}).get(label) for label in FILE_FIELD_LABELS
    ):
        return "At least one file path is required (Implement/Context/Write/Read)."
    return None


def roadmap_diff(before: list[str], after: list[str], path: str = "docs/roadmap.md") -> str:
    """Exact unified diff for the candidate lines the save path would write."""
    return "".join(difflib.unified_diff(before, after, fromfile=f"a/{path}", tofile=f"b/{path}"))


def compute_context_load(file_fields: dict, root: Path) -> int:
    """Live Context Load preview -- the same packaging formula route_tasks.py
    stamps on refresh (max(1, round(total_files * total_chars / 1000))), computed from
    whatever paths currently sit in the dialog's four file-list fields. total_files counts
    every listed entry regardless of whether it resolves (matching route_tasks._count_entries);
    total_chars only counts entries that currently resolve to a real file on disk -- a
    **Write:** target named ahead of creation contributes 0 chars here, same as it will
    once route_tasks.py re-stamps the saved task for real."""
    total_files = sum(len(v) for v in file_fields.values())
    if total_files == 0:
        return 1
    seen = set()
    resolved = []
    for paths in file_fields.values():
        if not paths:
            continue
        joined = " · ".join(f"`{p}`" for p in paths)
        files, _missing = route_tasks.resolve_file_list(joined, root)
        for f in files:
            key = f.as_posix()
            if key not in seen:
                seen.add(key)
                resolved.append(f)
    total_chars = sum(c for _, c in route_tasks._char_sizes(resolved, root))
    return route_tasks.context_load(total_files, total_chars)


compute_task_effort = compute_context_load  # legacy import compatibility


def _section_headings(lines: list[str]) -> list[str]:
    """Distinct ##/### heading texts in document order, for the editor's Section combobox."""
    seen = []
    for line in lines:
        m = SECTION_RE.match(line)
        if m and m.group(1) not in seen:
            seen.append(m.group(1))
    return seen


def find_section_end(lines: list[str], section_heading: str) -> int:
    """Index just before the next ##/###/--- boundary after `section_heading`'s own
    heading line. Raises ValueError if the heading isn't found. Matches the first
    occurrence if the same heading text appears more than once in the file."""
    i = 0
    while i < len(lines):
        m = SECTION_RE.match(lines[i])
        if m and m.group(1) == section_heading:
            j = i + 1
            while j < len(lines) and not SECTION_BOUNDARY_RE.match(lines[j]):
                j += 1
            return j
        i += 1
    raise ValueError(f"section heading not found: {section_heading!r}")


def insert_task_block(lines: list[str], section_heading: str, block_lines: list[str]) -> list[str]:
    """Insert a new task block (see build_task_lines()) at the end of `section_heading`,
    trimming any trailing blank lines immediately before the section boundary first and
    inserting exactly one blank-line separator -- so spacing stays consistent with the
    rest of the file regardless of how much trailing whitespace was already there."""
    end = find_section_end(lines, section_heading)
    while end > 0 and lines[end - 1].strip() == "":
        end -= 1
    return lines[:end] + ["\n"] + block_lines + lines[end:]


def replace_task_block(lines: list[str], start: int, end: int, block_lines: list[str]) -> list[str]:
    """Splice a rebuilt block over an existing task's [start, end) span (from
    Task.start/Task.end, which already includes the trailing blank line before the next
    header/boundary per route_tasks.scan_block_end) -- block_lines' own trailing blank
    line keeps spacing consistent with what it replaces."""
    return lines[:start] + block_lines + lines[end:]


def delete_task_block(lines: list[str], start: int, end: int) -> list[str]:
    """Remove exactly one parsed task's [start, end) span from a roadmap copy."""
    return lines[:start] + lines[end:]


def move_task_block(
    lines: list[str], start: int, end: int, new_section: str, block_lines: list[str]
) -> list[str]:
    """Edit-save when the section changed: remove [start, end) first, then insert into
    new_section fresh -- avoids stale-index interaction with find_section_end's own scan
    of what would otherwise be an already-mutated list."""
    remaining = lines[:start] + lines[end:]
    return insert_task_block(remaining, new_section, block_lines)


class TaskEditorDialog(ttk.Frame):
    """Create/edit panel behind the picker screen's "+ New Task"/"Edit" buttons.
    A class (deviating from the file's usual inline-function dialog pattern, e.g.
    _show_response) given the field/widget count. Builds a field-dict via the pure
    parse_task_fields()/build_task_lines()/validate_task_fields() helpers above and writes
    through route_tasks.write_roadmap() -- the same guarded atomic-write path
    refresh_routes()/_on_mark_complete() already use, per REVIEW_TIERS.md's Class 3 rule
    for any docs/roadmap.md write path. It opens as an in-window panel (never a popup) in
    place of the picker, so no picker action can reload app.roadmap_lines while it's open;
    _candidate() still refuses if they changed (_base_lines), since the task's line spans
    are only valid against the lines it opened with."""

    SCORE_VALUES = ("1", "2", "3", "4", "5")
    CLASS_VALUES = ("1", "2", "3")
    FILE_GROUP_BREAKPOINT = 680

    def __init__(self, app: "App", task: Task | None, clone: bool = False):
        sections = _section_headings(app.roadmap_lines)
        if not sections:
            super().__init__(app)  # never shown
            self.app = app
            app._notify_error(
                "No sections found",
                "roadmap.md has no ##/### section headings to file a task under -- "
                "add one by hand first.",
            )
            return
        title = "Clone Task" if clone else "Edit Task" if task is not None else "New Task"
        super().__init__(app._show_panel(title))
        self.pack(fill="both", expand=True)
        self.app = app
        self.task = None if clone else task
        self.source_task = task
        self.clone = clone
        self._manual_route = None  # round-tripped from an existing task, not settable here
        self._base_lines = list(app.roadmap_lines)
        self.path_entries = {}

        self.file_lists = {label: [] for label in FILE_FIELD_LABELS}
        self.listboxes = {}
        self.file_group_boxes = {}
        self._file_group_columns = None
        self.suffix_warning = None

        self.score_var = tk.StringVar(value="3")
        self.class_var = tk.StringVar(value="2")
        self.title_var = tk.StringVar()
        self.section_var = tk.StringVar(value=sections[0])
        self.id_var = tk.StringVar(value=f"task_{uuid.uuid4().hex}")
        self.status_var = tk.StringVar(value="Draft")
        self.outcome_var = tk.StringVar()
        self.rationale_var = tk.StringVar()
        self.work_mode_var = tk.StringVar()
        self.execution_mode_var = tk.StringVar()
        self.execution_size_var = tk.StringVar()
        self.uncertainty_var = tk.StringVar()
        self.is_fenced_var = tk.BooleanVar(value=False)
        self.pack_override_var = tk.BooleanVar(value=False)
        self._force_override = False
        self.context_load_var = tk.StringVar()

        suggestion_sources = [app.roadmap_lines]
        if app.SHIPPED_PATH.is_file():
            suggestion_sources.append(
                app.SHIPPED_PATH.read_text(encoding="utf-8").splitlines(keepends=True)
            )
        self.field_suggestions = task_field_suggestions(suggestion_sources)

        self._build_widgets(sections)
        if task is not None:
            self._prefill(task)
            if clone:
                self.id_var.set(f"task_{uuid.uuid4().hex}")
                self.status_var.set("Draft")
                self._manual_route = None
        self._refresh_context_load_preview()

    def _close(self):
        self.app._close_panel()

    # ── layout ──

    def _build_widgets(self, sections):
        f = ttk.Frame(self, padding=12)
        f.pack(fill="both", expand=True)

        # Claim the action row first so shrinking the dialog never pushes Save/Cancel
        # below the window. The content above receives whatever height remains.
        bottom = ttk.Frame(f)
        bottom.pack(side="bottom", fill="x", pady=(4, 0))
        bottom.columnconfigure(0, weight=1)
        effort_label = ttk.Label(
            bottom,
            textvariable=self.context_load_var,
            foreground=gui_theme.COLOR_MUTED,
            justify="left",
        )
        effort_label.grid(row=0, column=0, sticky="ew")
        self.force_btn = ttk.Button(
            bottom,
            text="⚑ Mark Ready Without Validation",
            command=self._on_force_ready_clicked,
        )
        self.force_btn.grid(row=0, column=1, padx=(6, 0))
        ttk.Button(bottom, text="Validate", command=self._on_validate_clicked).grid(
            row=0, column=2, padx=(6, 0)
        )
        ttk.Button(bottom, text="Preview Diff", command=self._on_preview_clicked).grid(
            row=0, column=3, padx=(6, 0)
        )
        ttk.Button(bottom, text="Preview & Save", command=self._on_save_clicked).grid(
            row=0, column=4, padx=(6, 0)
        )
        ttk.Button(bottom, text="Cancel", command=self._close).grid(row=0, column=5, padx=(6, 0))
        _wrap_with_parent(effort_label, bottom, inset=500)

        override_row = ttk.Frame(f)
        override_row.pack(side="bottom", fill="x", pady=(6, 0))
        self.override_check = ttk.Checkbutton(
            override_row,
            text="Pack Override — allow Ready even if Outcome, Acceptance, Files etc are missing (adds **Pack Override: true**)",
            variable=self.pack_override_var,
        )
        self.override_check.pack(side="left")
        ttk.Label(
            override_row,
            text="  Use to pack incomplete tasks for AI runs",
            foreground=gui_theme.COLOR_MUTED,
        ).pack(side="left", padx=(8, 0))

        tabs = ttk.Notebook(f)
        self.tabs = tabs
        tabs.pack(fill="both", expand=True, pady=(0, 8))
        record_tab = ttk.Frame(tabs, padding=8)
        artifacts_tab = ttk.Frame(tabs, padding=8)
        self.artifacts_tab = artifacts_tab
        requirements_tab = ttk.Frame(tabs, padding=8)
        tabs.add(record_tab, text="Task record")
        tabs.add(artifacts_tab, text="Artifacts")
        tabs.add(requirements_tab, text="Requirements")

        top = ttk.Frame(record_tab)
        top.pack(fill="x", pady=(0, 8))
        top.columnconfigure(1, weight=1)
        score_class = ttk.Frame(top)
        score_class.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))
        ttk.Label(score_class, text="Score:").grid(row=0, column=0, sticky="w")
        ttk.Combobox(
            score_class,
            textvariable=self.score_var,
            values=self.SCORE_VALUES,
            state="readonly",
            width=4,
        ).grid(row=0, column=1, padx=(4, 16))
        ttk.Label(score_class, text="Class:").grid(row=0, column=2, sticky="w")
        ttk.Combobox(
            score_class,
            textvariable=self.class_var,
            values=self.CLASS_VALUES,
            state="readonly",
            width=4,
        ).grid(row=0, column=3, padx=(4, 16))
        ttk.Label(top, text="Section:").grid(row=1, column=0, sticky="w")
        ttk.Combobox(top, textvariable=self.section_var, values=sections, state="readonly").grid(
            row=1, column=1, sticky="ew", padx=(6, 0)
        )
        ttk.Label(top, text="Status:").grid(row=2, column=0, sticky="w", pady=(6, 0))
        ttk.Combobox(
            top,
            textvariable=self.status_var,
            values=tuple(s for s in route_tasks.LIFECYCLE_STATUSES if s != "Shipped"),
            state="normal",
        ).grid(row=2, column=1, sticky="ew", padx=(6, 0), pady=(6, 0))
        ttk.Label(top, text="ID:").grid(row=3, column=0, sticky="w", pady=(6, 0))
        ttk.Entry(top, textvariable=self.id_var, state="readonly").grid(
            row=3, column=1, sticky="ew", padx=(6, 0), pady=(6, 0)
        )

        title_row = ttk.Frame(record_tab)
        title_row.pack(fill="x", pady=(0, 8))
        ttk.Label(title_row, text="Title:").pack(side="left")
        ttk.Combobox(
            title_row,
            textvariable=self.title_var,
            values=self.field_suggestions["title"],
        ).pack(side="left", fill="x", expand=True, padx=(6, 0))

        history_help = ttk.Label(
            record_tab,
            text=(
                "Type freely, or use each field's arrow to reuse wording from open and "
                "shipped tasks."
            ),
            foreground=gui_theme.COLOR_MUTED,
            justify="left",
        )
        history_help.pack(fill="x", pady=(0, 6))
        _wrap_with_parent(history_help, record_tab)

        if self.source_task is not None:
            self.suffix_warning = ttk.Label(record_tab, text="", foreground="#a00", justify="left")
            self.suffix_warning.pack(fill="x", pady=(0, 4))
            _wrap_with_parent(self.suffix_warning, record_tab)

        for label, variable in (("Outcome", self.outcome_var), ("Rationale", self.rationale_var)):
            row = ttk.Frame(record_tab)
            row.pack(fill="x", pady=(0, 6))
            ttk.Label(row, text=f"{label}:", width=10).pack(side="left")
            ttk.Combobox(
                row,
                textvariable=variable,
                values=self.field_suggestions[label.lower()],
            ).pack(side="left", fill="x", expand=True)

        record_lists = ttk.PanedWindow(record_tab, orient="horizontal")
        record_lists.pack(fill="both", expand=True, pady=(0, 6))
        acceptance_box = ttk.LabelFrame(record_lists, text="Acceptance conditions (one per line)")
        evidence_box = ttk.LabelFrame(record_lists, text="Expected evidence (one per line)")
        self.acceptance_text = scrolledtext.ScrolledText(acceptance_box, wrap="word", height=7)
        self.acceptance_text.pack(fill="both", expand=True, padx=4, pady=4)
        self.acceptance_evidence_text = scrolledtext.ScrolledText(
            evidence_box, wrap="word", height=7
        )
        self.acceptance_evidence_text.pack(fill="both", expand=True, padx=4, pady=4)
        record_lists.add(acceptance_box, weight=1)
        record_lists.add(evidence_box, weight=1)

        ttk.Label(artifacts_tab, text="Description / execution notes:").pack(anchor="w")
        self.body_text = scrolledtext.ScrolledText(artifacts_tab, wrap="word", height=4)
        self.body_text.pack(fill="x", pady=(2, 4))
        fenced_row = ttk.Frame(artifacts_tab)
        fenced_row.pack(fill="x", pady=(0, 8))
        ttk.Checkbutton(
            fenced_row,
            text="Treat description as a fenced ```text prompt block",
            variable=self.is_fenced_var,
        ).pack(side="left")
        ttk.Label(
            fenced_row,
            text="(sent to the model verbatim)",
            foreground=gui_theme.COLOR_MUTED,
        ).pack(side="left", padx=(6, 0))

        file_view = ttk.Frame(artifacts_tab)
        file_view.pack(fill="both", expand=True, pady=(0, 8))
        file_view.columnconfigure(0, weight=1)
        file_view.rowconfigure(0, weight=1)
        self.file_canvas = tk.Canvas(
            file_view,
            background=gui_theme.COLOR_BG,
            borderwidth=0,
            highlightthickness=0,
        )
        file_scroll = ttk.Scrollbar(file_view, orient="vertical", command=self.file_canvas.yview)
        self.file_canvas.configure(yscrollcommand=file_scroll.set)
        self.file_canvas.grid(row=0, column=0, sticky="nsew")
        file_scroll.grid(row=0, column=1, sticky="ns")

        self.file_grid = ttk.Frame(self.file_canvas)
        self.file_grid_window = self.file_canvas.create_window(
            (0, 0), window=self.file_grid, anchor="nw"
        )
        for idx, label in enumerate(FILE_FIELD_LABELS):
            self._build_file_group(self.file_grid, label, idx // 2, idx % 2)
        self.file_canvas.bind("<Configure>", self._resize_file_view)
        self.file_grid.bind(
            "<Configure>",
            lambda _event: self.file_canvas.configure(scrollregion=self.file_canvas.bbox("all")),
        )

        mode_row = ttk.Frame(requirements_tab)
        mode_row.pack(fill="x", pady=(0, 8))
        ttk.Label(mode_row, text="Work mode:").pack(side="left")
        ttk.Combobox(
            mode_row,
            textvariable=self.work_mode_var,
            values=("",) + route_tasks.WORK_MODES,
            state="readonly",
            width=18,
        ).pack(side="left", padx=(6, 18))
        ttk.Label(mode_row, text="Execution mode:").pack(side="left")
        ttk.Combobox(
            mode_row,
            textvariable=self.execution_mode_var,
            values=(
                "",
                "human-judgment",
                "human-physical",
                "deterministic-tooling",
                "local-ai",
                "network-ai",
            ),
            state="readonly",
        ).pack(side="left", fill="x", expand=True, padx=(6, 0))
        judgment_row = ttk.Frame(requirements_tab)
        judgment_row.pack(fill="x", pady=(0, 8))
        ttk.Label(judgment_row, text="Execution size:").pack(side="left")
        ttk.Combobox(
            judgment_row,
            textvariable=self.execution_size_var,
            values=("", "Small", "Medium", "Large"),
            state="readonly",
            width=12,
        ).pack(side="left", padx=(6, 18))
        ttk.Label(judgment_row, text="Uncertainty:").pack(side="left")
        ttk.Combobox(
            judgment_row,
            textvariable=self.uncertainty_var,
            values=("", "Low", "Medium", "High"),
            state="readonly",
            width=12,
        ).pack(side="left", padx=(6, 0))
        requirements_lists = ttk.Frame(requirements_tab)
        requirements_lists.pack(fill="both", expand=True)
        requirements_lists.columnconfigure(0, weight=1, uniform="requirement")
        requirements_lists.columnconfigure(1, weight=1, uniform="requirement")
        for index, (label, attr) in enumerate(
            (
                ("Capabilities (one per line)", "capabilities_text"),
                ("Constraints (one per line)", "constraints_text"),
                ("Protected behavior (one per line)", "protected_behaviors_text"),
                ("Blocked by task IDs (one per line)", "dependencies_text"),
                ("Prefer after task IDs (one per line)", "preferred_after_text"),
                ("Parent task IDs (one per line)", "parents_text"),
                ("Supersedes task IDs (one per line)", "supersedes_text"),
                ("Related task IDs (one per line)", "related_text"),
            )
        ):
            row, column = divmod(index, 2)
            requirements_lists.rowconfigure(row, weight=1, uniform="requirement")
            box = ttk.LabelFrame(requirements_lists, text=label)
            box.grid(
                row=row,
                column=column,
                sticky="nsew",
                padx=(0 if column == 0 else 3, 3 if column == 0 else 0),
                pady=(0, 6),
            )
            widget = scrolledtext.ScrolledText(box, wrap="word", height=3)
            widget.pack(fill="both", expand=True, padx=4, pady=4)
            setattr(self, attr, widget)

    def _build_file_group(self, parent, label, row, col):
        box = ttk.LabelFrame(parent, text=FILE_FIELD_DISPLAY[label], padding=6)
        box.grid(row=row, column=col, sticky="nsew", padx=4, pady=4)
        self.file_group_boxes[label] = box

        lb_frame = ttk.Frame(box)
        lb_frame.pack(fill="both", expand=True)
        lb = tk.Listbox(lb_frame, selectmode="extended", height=4)
        vsb = ttk.Scrollbar(lb_frame, orient="vertical", command=lb.yview)
        lb.configure(yscrollcommand=vsb.set)
        lb.pack(side="left", fill="both", expand=True)
        vsb.pack(side="left", fill="y")
        self.listboxes[label] = lb

        btns = ttk.Frame(box)
        btns.pack(fill="x", pady=(4, 0))
        ttk.Button(btns, text="Add Files...", command=lambda: self._add_files(label)).pack(
            side="left"
        )
        ttk.Button(btns, text="Add Path...", command=lambda: self._add_path(label)).pack(
            side="left", padx=4
        )
        ttk.Button(btns, text="Remove Selected", command=lambda: self._remove_selected(label)).pack(
            side="left"
        )
        # Typed paths are entered inline here (shown by "Add Path..."), not in a popup.
        entry_row = ttk.Frame(box)
        path_var = tk.StringVar()
        entry = ttk.Entry(entry_row, textvariable=path_var)
        entry.pack(side="left", fill="x", expand=True)
        entry.bind("<Return>", lambda _e: self._commit_path(label))
        entry.bind("<Escape>", lambda _e: entry_row.pack_forget())
        ttk.Button(entry_row, text="Add", command=lambda: self._commit_path(label)).pack(
            side="left", padx=(4, 0)
        )
        self.path_entries[label] = (entry_row, path_var, entry)

    def _resize_file_view(self, event):
        self.file_canvas.itemconfigure(self.file_grid_window, width=event.width)
        self._reflow_file_groups(event.width)
        self.after_idle(self._sync_file_view)

    def _sync_file_view(self):
        if not self.file_canvas.winfo_exists():
            return
        width = max(1, self.file_canvas.winfo_width())
        height = max(self.file_canvas.winfo_height(), self.file_grid.winfo_reqheight())
        self.file_canvas.itemconfigure(self.file_grid_window, width=width, height=height)
        self.file_canvas.configure(scrollregion=(0, 0, width, height))

    def _reflow_file_groups(self, width):
        """Switch file selectors between two columns and one as usable width changes."""
        columns = 2 if width >= self.FILE_GROUP_BREAKPOINT else 1
        if columns == self._file_group_columns:
            return
        self._file_group_columns = columns
        rows = (len(FILE_FIELD_LABELS) + columns - 1) // columns
        for idx, label in enumerate(FILE_FIELD_LABELS):
            self.file_group_boxes[label].grid_configure(
                row=idx // columns,
                column=idx % columns,
            )
        for col in range(2):
            self.file_grid.columnconfigure(col, weight=1 if col < columns else 0)
        for row in range(len(FILE_FIELD_LABELS)):
            self.file_grid.rowconfigure(
                row,
                weight=1 if row < rows else 0,
                uniform="file_group" if row < rows else "",
            )
        self.after_idle(self._sync_file_view)

    # ── prefill (edit only) ──

    def _prefill(self, task: Task):
        block = self.app.roadmap_lines[task.start : task.end]
        fields = parse_task_fields(block)
        self.score_var.set(fields["score"] or "3")
        self.class_var.set(fields["task_class"] or "2")
        self.title_var.set(fields["title"])
        self.section_var.set(task.section or self.section_var.get())
        if fields["id"]:
            self.id_var.set(fields["id"])
        self.status_var.set(fields["status"] or "Draft")
        self.outcome_var.set(fields["outcome"])
        self.rationale_var.set(fields["rationale"])
        self.work_mode_var.set(fields["work_mode"])
        self.execution_mode_var.set(fields["execution_mode"])
        self.execution_size_var.set(fields["execution_size"])
        self.uncertainty_var.set(fields["uncertainty"])
        self.pack_override_var.set(bool(fields.get("pack_override")))
        self._set_lines(self.acceptance_text, fields["acceptance_conditions"])
        self._set_lines(self.acceptance_evidence_text, fields["acceptance_evidence"])
        self._set_lines(self.capabilities_text, fields["capabilities"])
        self._set_lines(self.constraints_text, fields["constraints"])
        self._set_lines(self.protected_behaviors_text, fields["protected_behaviors"])
        self._set_lines(self.dependencies_text, fields["dependencies"])
        self._set_lines(self.preferred_after_text, fields["preferred_after"])
        self._set_lines(self.parents_text, fields["parents"])
        self._set_lines(self.supersedes_text, fields["supersedes"])
        self._set_lines(self.related_text, fields["related"])
        self.body_text.delete("1.0", "end")
        self.body_text.insert("1.0", fields["body"])
        self.is_fenced_var.set(fields["is_fenced"])
        self.file_lists = {k: list(v) for k, v in fields["file_fields"].items()}
        self._manual_route = fields["manual_route"]
        for label in FILE_FIELD_LABELS:
            self._refresh_listbox(label)
        if fields["has_field_suffix"] and self.suffix_warning is not None:
            self.suffix_warning.config(
                text="This task uses a per-line class-suffix annotation (e.g. "
                '"Implement (Class 3 — ...):") that this editor does not support -- '
                "saving will drop it."
            )

    @staticmethod
    def _set_lines(widget, values):
        widget.delete("1.0", "end")
        widget.insert("1.0", "\n".join(values))

    @staticmethod
    def _get_lines(widget):
        return [line.strip() for line in widget.get("1.0", "end").splitlines() if line.strip()]

    # ── file-list helpers ──

    def _refresh_listbox(self, label):
        lb = self.listboxes[label]
        lb.delete(0, "end")
        for p in self.file_lists[label]:
            lb.insert("end", p)

    def _relativize(self, raw_path: str) -> str:
        try:
            return Path(raw_path).resolve().relative_to(self.app.root_dir.resolve()).as_posix()
        except ValueError:
            return Path(raw_path).as_posix()

    def _add_files(self, label):
        paths = filedialog.askopenfilenames(
            parent=self, title=f"Select {FILE_FIELD_DISPLAY[label]} files"
        )
        for p in paths:
            rel = self._relativize(p)
            if rel and rel not in self.file_lists[label]:
                self.file_lists[label].append(rel)
        self._refresh_listbox(label)
        self._refresh_context_load_preview()

    def _add_path(self, label):
        """Show this group's inline path entry (repo-relative, glob, or a new file)."""
        row, _var, entry = self.path_entries[label]
        row.pack(fill="x", pady=(4, 0))
        entry.focus_set()

    def _commit_path(self, label):
        row, var, _entry = self.path_entries[label]
        raw = var.get().strip()
        var.set("")
        row.pack_forget()
        if not raw:
            return
        if raw and raw not in self.file_lists[label]:
            self.file_lists[label].append(raw)
        self._refresh_listbox(label)
        self._refresh_context_load_preview()

    def _remove_selected(self, label):
        lb = self.listboxes[label]
        for idx in reversed(lb.curselection()):
            del self.file_lists[label][idx]
        self._refresh_listbox(label)
        self._refresh_context_load_preview()

    def _refresh_context_load_preview(self):
        load = compute_context_load(self.file_lists, self.app.root_dir)
        self.context_load_var.set(f"Context Load (auto-computed on save): ~{load}")

    # ── save ──

    def _collect_fields(self) -> dict:
        return {
            "id": self.id_var.get(),
            "status": self.status_var.get(),
            "score": self.score_var.get(),
            "task_class": self.class_var.get(),
            "title": self.title_var.get().strip(),
            "section": self.section_var.get(),
            "body": self.body_text.get("1.0", "end").strip(),
            "is_fenced": self.is_fenced_var.get(),
            "file_fields": self.file_lists,
            "manual_route": self._manual_route,
            "outcome": self.outcome_var.get().strip(),
            "rationale": self.rationale_var.get().strip(),
            "work_mode": self.work_mode_var.get(),
            "acceptance_conditions": self._get_lines(self.acceptance_text),
            "acceptance_evidence": self._get_lines(self.acceptance_evidence_text),
            "execution_mode": self.execution_mode_var.get(),
            "execution_size": self.execution_size_var.get(),
            "uncertainty": self.uncertainty_var.get(),
            "capabilities": self._get_lines(self.capabilities_text),
            "constraints": self._get_lines(self.constraints_text),
            "protected_behaviors": self._get_lines(self.protected_behaviors_text),
            "dependencies": self._get_lines(self.dependencies_text),
            "preferred_after": self._get_lines(self.preferred_after_text),
            "parents": self._get_lines(self.parents_text),
            "supersedes": self._get_lines(self.supersedes_text),
            "related": self._get_lines(self.related_text),
            "pack_override": bool(self.pack_override_var.get() or self._force_override),
        }

    def _candidate(self, force_override: bool = False):
        if self.app.roadmap_lines != self._base_lines:
            raise ValueError(
                "The task list was reloaded since this editor opened, so its position in "
                "roadmap.md may have moved. Close the editor and open the task again."
            )
        fields = self._collect_fields()
        if force_override:
            fields["pack_override"] = True
            if fields["status"] in ("Draft", "Legacy", "", None):
                fields["status"] = "Ready"

        lifecycle_lines = list(self.app.roadmap_lines)
        if self.app.SHIPPED_PATH.is_file():
            lifecycle_lines.extend(
                self.app.SHIPPED_PATH.read_text(encoding="utf-8").splitlines(keepends=True)
            )
        existing_ids = route_tasks.collect_task_ids(lifecycle_lines)
        if self.task is not None and fields["id"]:
            existing_ids.discard(fields["id"])
        # A Ready task without files is a readiness heads-up, not a validation error.
        err = validate_task_fields(fields, existing_ids, allow_empty_files=True)
        if err:
            raise ValueError(err)
        # Readiness gaps are heads-ups shown in the save preview, never a refusal: the
        # maintainer may mark a task Ready whenever they judge it is.
        gaps = readiness_diagnostics(fields, self.app.root_dir, task_statuses(lifecycle_lines))

        block = build_task_lines(fields)
        if self.task is None:
            result = insert_task_block(self.app.roadmap_lines, fields["section"], block)
        elif fields["section"] == self.task.section:
            result = replace_task_block(
                self.app.roadmap_lines, self.task.start, self.task.end, block
            )
        else:
            result = move_task_block(
                self.app.roadmap_lines,
                self.task.start,
                self.task.end,
                fields["section"],
                block,
            )
        # Preview the same fully routed bytes the post-save refresh would otherwise
        # derive afterward. The displayed diff is therefore the exact write, including
        # generated annotations for Ready tasks rather than an intermediate draft.
        result = route_tasks.process_roadmap(result, self.app.ROADMAP_PATH, root=self.app.root_dir)
        relationship_lines = list(result)
        if self.app.SHIPPED_PATH.is_file():
            relationship_lines.extend(
                self.app.SHIPPED_PATH.read_text(encoding="utf-8").splitlines(keepends=True)
            )
        relationship_errors = route_tasks.validate_task_relationships(relationship_lines)
        if relationship_errors:
            raise ValueError(
                "Relationship validation failed:\n\n"
                + "\n".join(f"- {error}" for error in relationship_errors)
            )
        return fields, gaps, result

    def _on_validate_clicked(self):
        try:
            fields, gaps, _result = self._candidate(force_override=self.pack_override_var.get())
        except ValueError as exc:
            self.app._notify_error("Validation failed", str(exc), parent=self)
            return
        if gaps and not fields.get("pack_override"):
            self.app._notify_info(
                "Valid Draft; not Ready",
                "The record is structurally valid and nothing was written. Readiness gaps:\n\n"
                + "\n".join(f"- {gap}" for gap in gaps),
                parent=self,
            )
        else:
            override_note = (
                " (Pack Override active — gaps bypassed)" if fields.get("pack_override") else ""
            )
            self.app._notify_info(
                "Validation passed",
                f"This {fields['status']} record is structurally valid and Ready-complete{override_note}. "
                "Nothing was written.",
                parent=self,
            )

    def _on_preview_clicked(self):
        try:
            _fields, gaps, result = self._candidate(force_override=self.pack_override_var.get())
        except ValueError as exc:
            self.app._notify_error("Cannot preview", str(exc), parent=self)
            return
        diff = roadmap_diff(self.app.roadmap_lines, result, self.app.ROADMAP_PATH.as_posix())
        DiffPreviewDialog(self, diff, gaps)

    def _on_save_clicked(self, force: bool = False):
        try:
            _fields, gaps, result = self._candidate(
                force_override=force or self.pack_override_var.get() or self._force_override
            )
        except ValueError as exc:
            self.app._notify_error("Cannot save", str(exc), parent=self)
            return
        diff = roadmap_diff(self.app.roadmap_lines, result, self.app.ROADMAP_PATH.as_posix())
        DiffPreviewDialog(self, diff, gaps, on_apply=lambda: self._apply_candidate(result))

    def _on_force_ready_clicked(self):
        """Mark ready without validation by enabling pack override."""
        self.app.messages.ask(
            "Mark Ready without validation? This sets Status to Ready and adds "
            "**Pack Override: true**, bypassing the Outcome, Acceptance, Evidence, Work mode "
            "and file checks, so the task shows in Ready View and can be packed as is.",
            [("Mark Ready", self._force_ready)],
        )

    def _force_ready(self):
        if not self.winfo_exists():
            return
        self._force_override = True
        self.pack_override_var.set(True)
        self.status_var.set("Ready")
        self._on_save_clicked(force=True)

    def _apply_candidate(self, result):
        try:
            current = self.app.ROADMAP_PATH.read_text(encoding="utf-8").splitlines(keepends=True)
            if current != self.app.roadmap_lines:
                self.app._notify_error(
                    "Roadmap changed",
                    "roadmap.md changed after this editor opened. Reload and preview again; "
                    "nothing was written.",
                    parent=self,
                )
                return False
            route_tasks.write_roadmap(self.app.ROADMAP_PATH, self.app.roadmap_lines, result)
        except (OSError, RuntimeError) as exc:
            self.app._notify_error("Save failed", str(exc), parent=self)
            return False
        self.app._load_tasks()
        self._close()
        return True


class DiffPreviewDialog(ttk.Frame):
    """Exact roadmap diff gate. Apply is available only when a save requested it."""

    def __init__(self, parent, diff, readiness_gaps, on_apply=None):
        # Shown in place of the editor, inside the same in-window panel; "Back to editing"
        # brings the editor back exactly as it was.
        super().__init__(parent.master)
        self._editor = parent
        self.on_apply = on_apply
        parent.pack_forget()
        self.pack(fill="both", expand=True)
        frame = ttk.Frame(self, padding=10)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Exact roadmap diff", font=gui_theme.FONT_BOLD).pack(anchor="w")
        if readiness_gaps:
            ttk.Label(
                frame,
                text="Readiness heads-up (saving anyway is fine): " + "; ".join(readiness_gaps),
                foreground="#a65b00",
                justify="left",
                wraplength=850,
            ).pack(fill="x", pady=(0, 6))
        view = scrolledtext.ScrolledText(frame, wrap="none")
        view.pack(fill="both", expand=True)
        view.insert("1.0", diff or "(no changes)")
        view.configure(state="disabled")
        actions = ttk.Frame(frame)
        actions.pack(fill="x", pady=(8, 0))
        ttk.Button(actions, text="Back to editing", command=self.close).pack(side="right")
        if on_apply is not None and diff:
            ttk.Button(actions, text="Apply This Diff", command=self._apply).pack(
                side="right", padx=(0, 6)
            )

    def close(self):
        if self.winfo_exists():
            self.destroy()
        if self._editor.winfo_exists():
            self._editor.pack(fill="both", expand=True)

    def _apply(self):
        # A successful apply closes the whole panel (editor and this preview with it).
        if self.on_apply and self.on_apply() and self.winfo_exists():
            self.close()


class SimpleTaskDialog(ttk.Frame):
    """Compact task creation dialog requiring only a Title.

    Defaults to Score 3 🥈, Class 1, Status Draft, and the current or first section.
    Allows quick note/outcome capture, and provides a "More Details…" button to
    transition into the full TaskEditorDialog if complex fields are desired.
    """

    SCORE_VALUES = ("1", "2", "3", "4", "5")
    CLASS_VALUES = ("1", "2", "3")
    STATUS_VALUES = (
        "Draft",
        "Defined",
        "Ready",
        "In Progress",
        "Blocked",
        "Held",
        "Deferred",
    )

    def __init__(self, app: "App", initial_section: str | None = None):
        sections = _section_headings(app.roadmap_lines)
        if not sections:
            super().__init__(app)  # never shown
            self.app = app
            app._notify_error(
                "No sections found", "roadmap.md has no ##/### sections to file a task under."
            )
            return
        super().__init__(app._show_panel("New Task"))
        self.pack(fill="both", expand=True)
        self.app = app

        default_section = (
            initial_section if initial_section and initial_section in sections else sections[0]
        )

        self.title_var = tk.StringVar()
        self.section_var = tk.StringVar(value=default_section)
        self.status_var = tk.StringVar(value="Draft")
        self.score_var = tk.StringVar(value="3")
        self.class_var = tk.StringVar(value="1")

        self._build_widgets(sections)

    def _build_widgets(self, sections):
        f = ttk.Frame(self, padding=12)
        f.pack(fill="both", expand=True)

        title_font = (
            ("Segoe UI", 10, "bold") if sys.platform == "win32" else ("sans-serif", 10, "bold")
        )
        ttk.Label(f, text="Title:", font=title_font).pack(anchor="w", pady=(0, 2))
        self.title_entry = ttk.Entry(f, textvariable=self.title_var)
        self.title_entry.pack(fill="x", pady=(0, 10))
        self.title_entry.focus_set()
        self.title_entry.bind("<Return>", lambda e: self._on_save_clicked())

        sec_frame = ttk.Frame(f)
        sec_frame.pack(fill="x", pady=(0, 8))
        ttk.Label(sec_frame, text="Section:", width=8).pack(side="left")
        ttk.Combobox(
            sec_frame,
            textvariable=self.section_var,
            values=sections,
            state="readonly",
        ).pack(side="left", fill="x", expand=True)

        meta_frame = ttk.Frame(f)
        meta_frame.pack(fill="x", pady=(0, 8))

        ttk.Label(meta_frame, text="Status:").pack(side="left")
        status_cb = ttk.Combobox(
            meta_frame,
            textvariable=self.status_var,
            values=self.STATUS_VALUES,
            width=12,
        )
        status_cb.pack(side="left", padx=(4, 12))

        ttk.Label(meta_frame, text="Score:").pack(side="left")
        ttk.Combobox(
            meta_frame,
            textvariable=self.score_var,
            values=self.SCORE_VALUES,
            state="readonly",
            width=4,
        ).pack(side="left", padx=(4, 12))

        ttk.Label(meta_frame, text="Class:").pack(side="left")
        ttk.Combobox(
            meta_frame,
            textvariable=self.class_var,
            values=self.CLASS_VALUES,
            state="readonly",
            width=4,
        ).pack(side="left", padx=(4, 0))

        ttk.Label(f, text="Outcome / Notes (optional):").pack(anchor="w", pady=(4, 2))
        self.notes_text = scrolledtext.ScrolledText(f, height=4, wrap="word")
        self.notes_text.pack(fill="both", expand=True, pady=(0, 12))

        bottom = ttk.Frame(f)
        bottom.pack(side="bottom", fill="x")

        ttk.Button(
            bottom,
            text="More Details…",
            command=self._on_more_details,
        ).pack(side="left")

        ttk.Button(bottom, text="Cancel", command=self.app._close_panel).pack(
            side="right", padx=(6, 0)
        )
        save_btn = ttk.Button(
            bottom,
            text="+ Add Task",
            command=self._on_save_clicked,
        )
        save_btn.pack(side="right")

    def _on_more_details(self):
        title = self.title_var.get().strip()
        section = self.section_var.get().strip()
        score = self.score_var.get().strip() or "3"
        task_class = self.class_var.get().strip() or "1"
        status = self.status_var.get().strip() or "Draft"
        outcome = self.notes_text.get("1.0", "end-1c").strip()

        app = self.app
        # Opening the full editor replaces this panel (and destroys this frame).
        dlg = TaskEditorDialog(app, task=None)
        if title:
            dlg.title_var.set(title)
        if section:
            dlg.section_var.set(section)
        dlg.score_var.set(score)
        dlg.class_var.set(task_class)
        dlg.status_var.set(status)
        if outcome:
            dlg.outcome_var.set(outcome)

    def _on_save_clicked(self):
        title = self.title_var.get().strip()
        if not title:
            self.app._notify_warning("Title required", "Please enter a task title.", parent=self)
            self.title_entry.focus_set()
            return

        section = self.section_var.get().strip()
        if not section:
            self.app._notify_warning("Section required", "Please choose a section.", parent=self)
            return

        outcome = self.notes_text.get("1.0", "end-1c").strip()
        task_id = f"task_{uuid.uuid4().hex}"
        score = self.score_var.get().strip() or "3"
        task_class = self.class_var.get().strip() or "1"
        status = self.status_var.get().strip() or "Draft"

        fields = {
            "score": score,
            "task_class": task_class,
            "title": title,
            "id": task_id,
            "status": status,
            "outcome": outcome,
            "rationale": "",
            "acceptance_conditions": [],
            "acceptance_evidence": [],
            "execution_mode": "",
            "work_mode": "",
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
            "file_fields": {"Implement": [], "Context": [], "Write": [], "Read": []},
            "manual_route": None,
            "body": "",
            "is_fenced": False,
            "pack_override": False,
        }

        block_lines = build_task_lines(fields)
        try:
            current = self.app.ROADMAP_PATH.read_text(encoding="utf-8").splitlines(keepends=True)
            if current != self.app.roadmap_lines:
                self.app._notify_error(
                    "Roadmap changed",
                    "roadmap.md changed on disk. Reloading; nothing was written.",
                    parent=self,
                )
                self.app._load_tasks()
                self.app._close_panel()
                return
            new_lines = insert_task_block(self.app.roadmap_lines, section, block_lines)
            route_tasks.write_roadmap(self.app.ROADMAP_PATH, self.app.roadmap_lines, new_lines)
        except (OSError, RuntimeError, ValueError) as exc:
            self.app._notify_error("Save failed", str(exc), parent=self)
            return

        self.app._load_tasks()
        # Find newly added task and select it in tree
        for iid in self.app.tree.get_children():
            idx = int(iid)
            if idx < len(self.app.filtered_tasks) and self.app.filtered_tasks[idx].id == task_id:
                self.app.tree.selection_set(iid)
                self.app.tree.focus(iid)
                self.app.tree.see(iid)
                break
        self.app._close_panel()
