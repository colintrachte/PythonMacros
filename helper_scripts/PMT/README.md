# helper_scripts

The mechanical half of the AI harness described in `templates/AI_HARNESS.template.md`. Copy
the `*.py` files into a new project's repo (alongside the instantiated `docs/roadmap.md`
and `CLAUDE.md`) and they work with no code changes for the common case — see "One-time setup
per project" below for the one file you should add. Prefer `setup_wizard.py`, which does
this for you; if copying by hand, take pristine `external_refs.json`/`context_load_ceiling.txt`
from `templates/seed.*` and do **not** copy `system_prompt.txt` — those three are this
kit's own live per-project state (see the root README's "Self-hosting: which copy is
which").

## What's here

| File                                                    | What it does                                                                                                                                                                                                                                                                                                                                                  |
| ------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `context_pack.py`                                       | Assembles an explicit file list into one paste-ready block for a free-tier model, with per-model budget warnings and automatic chunking. Fully generic — no per-project edits needed.                                                                                                                                                                         |
| `route_tasks.py`                                        | Parses `docs/roadmap.md`, stamps `**Route:**`/`**Context Load:**`/`**Chars:**` on every open item per the routing rules, self-heals the score→medal mapping. Fully generic.                                                                                                                                                                                         |
| `executor_registry.json` / `executor_registry.py`       | Canonical volatile executor roster plus deterministic mode/capability/constraint matching.                                                                                                                                                                                                                                                                    |
| `query_model.py`                                        | Sends a context pack + task to a programmatic endpoint (local LM Studio / OpenRouter free tier) and captures the raw response. Reads `system_prompt.txt` (see below) for its guardrail prompt.                                                                                                                                                                |
| `pack_task.py`                                          | The Quest Board's stable runnable entry point and GUI controller: pick roadmap tasks from a sortable/filterable table; preview the assembled pack; paste a model's response into that task's AI inbox; copy/save for manual paste or send straight to a programmatic model. Run with `python helper_scripts/PMT/pack_task.py`. |
| `scoring.py`                                            | Headless, stdlib-only task scoring, effort ceiling, value-density calculation, and roadmap sequence sorting (zero GUI dependencies). |
| `task_records.py`                                       | Quest Board's task record, roadmap parser, relationship derivation, and readiness views. |
| `task_editor.py`                                        | Quest Board's task-editor mechanics and diff-gated editor dialogs; roadmap writes still pass through `route_tasks.py`'s guarded path. |
| `pack_delivery.py`                                      | Quest Board's model-facing prompt/chunk preparation, delivery-key helpers, response filtering, and AI inbox mechanics. |
| `doctor.py`                                             | Read-only installation, roadmap, artifact, dependency, inbox, and routing checks. `--json` emits the documented schema described in its module header. |
| `pmt_version.json`                                      | Canonical installed kit version and mechanics hash catalog. Its `schema_version` describes this catalog only; the manifest schema is never a kit version. |
| `execution_receipts.py` / `execution_receipts.json`     | Records compact local execution facts keyed by task ID and produces deterministic calibration reports. The JSON file is per-project data, not a second task database. |
| `context_load_ceiling.txt`                              | Persisted high-water mark for generated Context Load, so the picker's value-density column stays on a stable scale across sessions. Legacy `effort_ceiling.txt` is read once during migration.                                                                                                                                                                  |
| `external_refs.json`                                    | `name -> search hint` for roadmap file-list entries that point outside this repo (a reference implementation, a vendor SDK, a spec doc). Starts empty in this template.                                                                                                                                                                                       |
| `external_ref_paths.txt` (not committed — gitignore it) | `name=local/path` — when set, an external reference resolves straight from a local clone instead of only being described to a model as something to search for. Machine-specific, not a project fact.                                                                                                                                                         |
| `ai_inbox/` and `assimilated/` (not committed — gitignore them) | Pack Task creates both beside the helper scripts when missing. The inbox holds one growing Markdown file per task. Identified tasks use a short `<ID-fragment>-<title-fragment>.md` name (20 characters maximum) and record the full ID at the top of the file; legacy tasks use a short title slug. After fusion, move the finished task's file to `assimilated/`. Each save can be verbatim or use the conservative, non-summarizing slop filter. |

## One-time setup per project

1. Copy this folder into the project alongside `docs/roadmap.md` (from
   `templates/ROADMAP.template.md`) and `CLAUDE.md` (from `templates/CLAUDE.template.md`,
   which should already have this project's review tiers filled in).
2. **Create `helper_scripts/PMT/system_prompt.txt`** with this project's identity, artifact
   types, hard constraints, evidence rules, and review boundary. Keep durable project rules
   here; the individual task prompt supplies the changing outcome and output shape.
   `query_model.py` and `pack_task.py` both read this file and fall back to a generic
   guardrail prompt if it doesn't exist yet. Example:

   ```text
   You are a bounded contributor to <project>, <one-line purpose and audience>.
   Use only the supplied task and artifacts; do not silently widen scope.

   Return exactly the requested deliverable. Support factual claims with the most precise
   available artifact location (`path:line`, page, sheet/cell, timestamp, or object name).
   Write [NOT FOUND] when evidence is absent, label inferences, and never invent project facts.

   Project artifacts include <code, documents, datasets, images, CAD, research, etc.>.
   Hard constraints: <runtime, tools, safety, privacy, dependency, style, or process rules>.
   Local project files are canonical. Network or cloud services are <allowed uses or forbidden>.

   Do not modify or propose implementation for <top review tier>; provide analysis and a
   verification plan only. Do not add dependencies, services, or scope without explicit
   task authority.
   ```

3. If this project forks/tracks an upstream with reference material you'll want to pull
   into context packs, add entries to `external_refs.json` as you discover them.
4. Add `helper_scripts/PMT/ai_inbox/` and `helper_scripts/PMT/assimilated/` (and
   `external_ref_paths.txt` if you'll use one) to this project's own
   `.gitignore` — `setup_wizard.py` doesn't manage a target project's `.gitignore`, so this
   is the one manual step for keeping machine-local/working files out of commits.
5. That's it — `route_tasks.py` and `pack_task.py` default to `docs/roadmap.md` and need no
   further configuration.
