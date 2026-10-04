# [Project] — Roadmap (template)

> **Instantiation note:** copy this file to `docs/roadmap.md` (or `TODO.md` if the project
> is small enough that one flat file is enough — the format below works at either scale) in
> the target project. This exact path and format is what `helper_scripts/PMT/route_tasks.py`
> and `helper_scripts/PMT/pack_task.py` parse — keep new items matching the convention below, or
> the tooling can't route/pack them. Completed items move to `shipped.md` in the same format
> (minus the generated annotations, which no longer matter once an item is done).

`[FILL IN: one line on how this roadmap relates to any upstream/parent priorities — e.g.
"re-prioritized against our own use cases, not upstream's issue labels"]`

---

> the tooling can't route/pack them. Completed items move to `shipped.md` in the same format
> (minus the generated annotations, which no longer matter once an item is done).

`[FILL IN: one line on how this roadmap relates to any upstream/parent priorities — e.g.
"re-prioritized against our own use cases, not upstream's issue labels"]`

---

## Format convention

`helper_scripts/PMT/route_tasks.py` parses this file; `helper_scripts/PMT/context_pack.py` and
`helper_scripts/PMT/pack_task.py` consume the file lists you write into it. Any checkbox line
under a heading — `- [ ] **your idea**` or just `- [ ] your idea` — is already a complete
task, and PMT adds its permanent ID for you. Capture first, add detail later. Everything
below is optional structure that unlocks more help (routing, readiness, packing,
prioritizing):

- **Header line:** `- [ ] **Score <1-5> <medal> · Class <1-3> — <title>**`. When you record
  a class, put `Class <n>` in the header line itself — routing reads it only there — see
  `REVIEW_TIERS.template.md` for what your tiers mean.
- **`**ID:**`** is permanent identity: `task_` plus 32 lowercase hexadecimal characters.
  Quest Board assigns one to new and cloned tasks. For legacy roadmaps, preview
  `python helper_scripts/PMT/route_tasks.py --migrate-ids --dry-run`, then run it without
  `--dry-run`; migration inserts only ID lines and never regenerates an existing ID.
- **`**Status:**`** is one of `Draft`, `Defined`, `Ready`, `In Progress`, `Blocked`,
  `Held`, `Deferred`, `Verification`, or `Shipped`. Status text may be free-form; a canonical
  word followed by a delimiter (` — `, ` - `, or `: `) like `Deferred — revisit in v2` or
  `Blocked: waiting on upstream PR` is normalized to drive routing and dependency-unblocking.
  Generated Route/Context Load/Chars annotations remain available for every open task; status
  controls workflow state, and only `Ready` tasks enter the derived Ready queue. Adding
  `**Pack Override:** true` (or clicking "Mark Ready Without Validation" in Quest Board) bypasses
  gap checks and allows packing an incomplete task.
- The full authored record may also contain one-line `**Outcome:**`, `**Rationale:**`,
  `**Work mode:**`, `**Execution mode:**`, and repeated `**Acceptance:**`, `**Expected evidence:**`,
  `**Execution size:**`, `**Uncertainty:**`, `**Capability:**`, `**Constraint:**`,
  `**Protected behavior:**`, `**Blocked by:**`, `**Prefer after:**`, `**Parent:**`, `**Supersedes:**`,
  relationships are derived rather than stored twice. Quest Board is the preferred editor
  because it validates the full graph and previews the exact diff before any write.
- `**Work mode:**` is optional but useful for substantial tasks: `Forge` explores an uncertain
  approach, `Steward` preserves and improves known behavior, and `Forge + Steward` names both
  boundaries. A combined task must include at least one `**Protected behavior:**` line.
- Quest Board's Ready view contains explicit `Ready` tasks with complete definitions and no open
  hard blockers. Completing a
  prerequisite removes its `Blocked by`/legacy `Dependency` edge from dependent tasks and changes
  a `Blocked` dependent to `Ready` when no blocker remains. Its derived Warnings column explains
  why an incomplete task is excluded; a Draft or Defined task with no mechanical gap is identified
  as ready to promote. `**Prefer after:**` records a soft sequence: Quest Board
  shows a heads-up but never refuses to pack or send. Parentage
  does not imply blocking. Missing targets, self-references, and cycles in blocking, preferred,
  parent, or supersession relationships are invalid. Multiple IDs may share one relationship
  line when separated by `·`.
- **File-list fields** are their own line(s), starting with `  **Implement:**`,
  `  **Context:**`, `  **Write:**`, `  **Read:**`, or `  **Evidence:**` (parenthetical suffixes like
  `**Implement (Class 3 — motor output):**` are fine when one item spans tiers), each a
  `·`-separated list of backtick-quoted paths. They're optional: without one the task still
  works everywhere, routing just has no files to size or pack.
- **`**Route:**`** is a generated annotation, not hand-authored — stamped by
  `route_tasks.py` per `AI_HARNESS.template.md` §2. Re-run the script after adding or
  editing items rather than filling it in by hand. To pin a route the script can't
  auto-detect (a judgment call or external-knowledge lookup — §2 rules 2 and 5), append
  ` (manual)` to the value, e.g. `**Route:** perplexity (manual)`. A Route line ending in
  that suffix is a human override and `route_tasks.py` never re-stamps it (Context Load/Chars
  still get re-derived around it, since those stay mechanical either way).
- **`**Context Load:**`** is likewise generated, stamped right after `**Route:**` — a
  packaging-burden score (`max(1, round(total_files * total_text_chars / 1000))`), not
  labor, duration, or implementation difficulty. Legacy `**Effort:**` lines are accepted
  and replaced without changing the numeric value's formula.
- **`**Chars:**`** reports text character counts and separately names non-text artifacts
  that require a preview or visual inspection. Binary bytes are never presented as text
  characters or execution effort.
- **`**Execution size:**`** (`Small`, `Medium`, or `Large`) and **`**Uncertainty:**`**
  (`Low`, `Medium`, or `High`) are authored judgments. They remain separate from generated
  Context Load and are not silently inferred from file size.
- Authored roadmap order is the default recommended execution sequence. Score expresses value,
  not permission to start. `Blocked by` (strong) and `Prefer after` (soft) relationships are
  warnings shown when you pack or send — PMT never refuses to do what you ask because of them —
  and Context Load only helps compare otherwise equivalent tasks.
- When you know which project files or folders a task needs (or would help as context), list
  them — that is what lets PMT package the task for another model or person.
- When a todo item is marked complete `[x]`, move it to `shipped.md` — do this
  mechanically via `python helper_scripts/PMT/route_tasks.py --complete "<task ID>"`
  (or the Quest Board's "Mark Complete" button) rather than hand-editing both files. It
  flips the checkbox, strips the now-irrelevant `Route`/`Context Load`/`Chars` lines, updates dependent
  blocker lists and statuses, and moves the block for you.
- `route_tasks.py --check` exits non-zero if this file's `Route`/`Context Load`/`Chars`
  annotations are stale or a task still needs its permanent ID, without writing anything —
  useful as a pre-commit gate so a hand-edited roadmap never merges un-routed (running the
  script without `--check` fixes both). Opt-in example:
  `templates/pre-commit-config.yaml.example`.

### Writing task descriptions

The prose under each header is what `pack_task.py` drops straight into the model-facing
prompt box (or, for a fenced ` ```text ` block, IS the prompt verbatim) — write it as an
instruction to the model, not a spec written about the model:

- Lead with an imperative verb — Implement, Fix, Add, Refactor, Investigate, Research,
  Compare, Test, Verify, Migrate, Document — not a noun phrase. "A stdlib-only test
  harness that..." reads as a description of a thing; "Write a stdlib-only test harness
  that..." reads as an instruction to carry it out.
- State what "done" looks like and any hard constraint up front, not buried at the end.
- If the task has multiple ordered steps, write them as a numbered list — order-dependent
  instructions packed into one paragraph get skipped or done out of order.
- Say plainly if you want the model to act rather than propose ("Change X to do Y", not
  "Could X be improved?") — models default to suggesting when asked a question instead of
  given a command.
- State the _why_ when a constraint isn't obvious ("...so free-tier chatgpt sessions don't
  silently truncate") — the reason generalizes to edge cases the instruction didn't spell
  out.

## Scoring

### Score (1–5)

5 = highest priority.

- **5** — strengthens the foundation, unblocks a headline goal, or protects your Class 3
  surface
- **3** — expands real capability or improves a real workflow
- **1** — polish, or serves a deferred/secondary audience

The medal glyph next to the score is always mechanically derived, never hand-typed:
`route_tasks.py` re-derives it from the score on every run (≥4 → 🥇, =3 → 🥈, ≤2 → 🥉) and
corrects the header token if it's stale or wrong. The score is the single source of truth;
the medal never drifts independently.

### Class (1–3)

See `REVIEW_TIERS.template.md` for the full definitions this project settled on. Summarized
for roadmap context:

- **Class 3** — your top tier. Never unattended; human review (+ any project checklist)
  mandatory.
- **Class 2** — AI may propose and stage; a human approves before merge.
- **Class 1** — AI may merge if the build/tests pass and the change stays confined to this
  class.

When a change spans classes, it takes the bar of the highest class it touches.

### Context Load (generated, not hand-typed)

```
context_load = max(1, round(total_files * total_text_chars / 1000))
```

Reuses the file list and text character counts already resolved for `**Chars:**`. It
describes packaging burden only; author Execution size and Uncertainty separately.

---

## How this roadmap is organized

`[FILL IN: your own grouping — e.g. by subsystem, by milestone, by "what it serves." Thorax
grouped by: Foundation & Safety spine → target builds → platform mechanics → deferred. A
fork-and-maintain project might instead group by: Critical (crashes/data loss) → High
(major bugs) → Medium (quality of life) → Low (cosmetic) — see TRIAGE_POLICY.template.md's
categories, which map directly onto this if that's the project type.]`

---

## 1. [FILL IN: first section]

_[FILL IN: what this section is for and why it's ordered first]_

- [ ] **Score 5 🥇 · Class 2 — Example: fix a bounded, well-understood bug** — One or two
      sentences on what's wrong and why it matters. Include enough detail that a model with no
      other context could still scope the fix from this description alone.

  **ID:** task_0123456789abcdef0123456789abcdef
  **Status:** Ready
  **Outcome:** The observed failure no longer occurs under the documented reproduction.
  **Work mode:** Steward
  **Acceptance:** The reproduction passes without the previous failure.
  **Expected evidence:** Test output showing the regression case passes.
  **Implement:** `path/to/file.ext`
  **Context:** `path/to/related_header.ext` · `docs/relevant-doc.md`

  <!-- Route/Context Load/Chars are stamped here by route_tasks.py after you run it — don't
       hand-type them. -->

- [ ] **Score 3 🥈 · Class 1 — Example: a small, well-specified task with a ready-made prompt**
      — A task simple enough to hand a free-tier model verbatim.

  **Context:** `path/to/reference_file.ext`
  **Write:** `path/to/new_file.ext`

  ```text
  CONTEXT: <one or two sentences of project context>

  TASK:
  1. Read <the exact files>.
  2. <the specific, bounded thing to do>
  3. <where the output goes>

  Output ONLY <the deliverable>. No preamble, no explanation.
  Every claim must include file:line. If you cannot find it, write [NOT FOUND].
  ```

---

## Notes

- **Shipped**: Completed items live in `shipped.md` — moved there via
  `route_tasks.py --complete` (see the format-convention section above), not by hand.
- **Parent repo** (if a fork): `[FILL IN]`
- **Do NOT touch**: `[FILL IN: vendored deps, generated assets, anything managed outside
this project's normal workflow]`
- **Build**: `[FILL IN]`
- **Test framework**: `[FILL IN]`
- **CI**: `[FILL IN]`
