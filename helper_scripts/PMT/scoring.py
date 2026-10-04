"""
scoring.py — Headless task scoring, effort calculation, and sorting logic for PMT.

This module is 100% standard library and has ZERO dependencies on Tkinter or any GUI.
It can be safely imported and run by automated scripts, AI sessions, and headless
CLI tools to deterministically rank and sort tasks.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from task_records import Task

import contextlib

from task_records import split_header

DEFAULT_CEILING_DIR = Path(__file__).resolve().parent
CONTEXT_LOAD_CEILING_PATH = DEFAULT_CEILING_DIR / "context_load_ceiling.txt"
LEGACY_EFFORT_CEILING_PATH = DEFAULT_CEILING_DIR / "effort_ceiling.txt"


def score_int(t: Task) -> int:
    """Extract numeric priority score (1-5) from task header."""
    score, _ = split_header(t.header)
    return int(score) if score.isdigit() else 0


def effort_int(t: Task) -> int | None:
    """Extract numeric Context Load (effort) from task record."""
    return int(t.effort) if t.effort.isdigit() else None


def read_effort_ceiling(ceiling_dir: Path | None = None) -> int:
    """Read persisted context load ceiling, migrating legacy file if present."""
    base = ceiling_dir or DEFAULT_CEILING_DIR
    cur_path = base / "context_load_ceiling.txt"
    leg_path = base / "effort_ceiling.txt"

    for path in (cur_path, leg_path):
        try:
            value = max(1, int(path.read_text(encoding="utf-8").strip()))
        except (FileNotFoundError, ValueError, OSError):
            continue
        if path == leg_path and not cur_path.exists():
            with contextlib.suppress(OSError):
                cur_path.write_text(str(value), encoding="utf-8")
        return value
    return 1


def update_effort_ceiling(tasks: list[Task], ceiling_dir: Path | None = None) -> int:
    """Raise the persisted ceiling if any open task's Context Load exceeds it; never
    lowers it. Returns the effective ceiling to normalize against."""
    stored = read_effort_ceiling(ceiling_dir)
    seen_max = max((effort_int(t) or 0 for t in tasks), default=0)
    ceiling = max(stored, seen_max)
    if ceiling != stored:
        base = ceiling_dir or DEFAULT_CEILING_DIR
        cur_path = base / "context_load_ceiling.txt"
        with contextlib.suppress(OSError):
            cur_path.write_text(str(ceiling), encoding="utf-8")
    return ceiling


def combined_score(t: Task, effort_ceiling: int) -> float:
    """Value-density, with Context Load normalized onto the same 1-5 scale as score
    (the persisted ceiling maps to 5) before dividing. Squared to penalize non-linear
    complexity growth. Returns 0.0 when unrouted/effort unknown."""
    effort = effort_int(t)
    score = score_int(t)
    if effort is None or score == 0 or effort_ceiling <= 0:
        return 0.0
    effort_scaled = 1 + 4 * (min(effort, effort_ceiling) / effort_ceiling) ** 2
    return score / effort_scaled


def model_breakdown(t: Task) -> bool:
    """True when task was bumped to Claude purely for size (too many files/chars),
    not because it is Class 3."""
    return t.task_class != "3" and t.route == "claude"


def default_sort_key(t: Task) -> tuple[int, int]:
    """Preserve the roadmap author's recommended sequence by default."""
    return (t.roadmap_order, 0)


# Backward-compatibility aliases matching original private names in pack_task.py
_score_int = score_int
_effort_int = effort_int
_read_effort_ceiling = read_effort_ceiling
_update_effort_ceiling = update_effort_ceiling
_combined_score = combined_score
_model_breakdown = model_breakdown
_default_sort_key = default_sort_key
