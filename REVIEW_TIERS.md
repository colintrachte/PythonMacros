# Review Tiers (template)

> **Instantiation note:** copy this to `REVIEW_TIERS.md` at the project root, alongside
> `TRIAGE_POLICY.md`/`IN_PROCESSING.md` — `CLAUDE.md` §1/§7 link to it rather than
> restating it, the same way it links out to `TRIAGE_POLICY.md` for triage judgment. This
> keeps it a single, independently diffable file a setup script can detect and manage on
> its own. `ROADMAP.template.md`'s `Class <1-3>` header field and `AI_HARNESS.template.md`'s
> routing rules both assume this taxonomy exists; fill it in before wiring up either.

## The pattern

Not all code carries the same cost when it's wrong. A typo in a comment and a bug in
payment-processing code both "compile," but only one of them costs real money when it
ships broken. Most projects benefit from naming a small number of blast-radius tiers up
front and gating AI (and human) review rigor to the tier — not to how polished the change
looks, how confident anyone is in it, or how urgent it feels.

This generalizes to three tiers. Two is usually too coarse (it collapses "needs a second
pair of eyes" into either "trivial" or "everything"); four or more is usually unnecessary
overhead for a single-maintainer or small-team project. Start with three; split further
only if you find yourself constantly qualifying one tier with "except when."

## Filling this in

For **every** project — even ones that feel "safe" — name a Class 3. If a project genuinely
has no plausible high-consequence surface, that itself is worth writing down explicitly
("this project has no Class 3 surface because X") rather than leaving the tier undefined,
because "undefined" silently becomes "nothing is ever gated," which is a decision, just an
unexamined one.

Common Class 3 candidates by project type — pick the one that fits, or write your own:

| Project type                       | Plausible Class 3 surface                                                                                    |
| ---------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| Robotics / embedded firmware       | Arming, watchdogs, e-stop, motor/actuator output, failover logic — anything that can hurt hardware or people |
| Financial / accounting software    | Ledger writes, balance calculations, anything that reconciles against real money                             |
| Data pipelines / migrations        | Irreversible schema changes, destructive migrations, anything without a rollback path                        |
| Slicer / CAM / fabrication tooling | Toolpath generation, feed/speed calculations, anything that reaches the physical machine                     |
| Games / creative tools             | Save-file format changes, anything that can silently corrupt user-created content                            |
| General SaaS backend               | Auth/authorization logic, data-deletion endpoints, billing                                                   |

---

## Class 3 — [FILL IN: your top tier's name, e.g. "Safety-critical"]

**Surface:** `[FILL IN: the specific modules/functions/subsystems that belong here — be as
concrete as possible; a vague Class 3 definition doesn't gate anything]`

Rules for this tier:

- **Never** auto-merge a change in this tier. It requires human review and
  `[FILL IN: any project-specific checklist — e.g. a safety audit checklist, a security
review, a second engineer's sign-off]`.
- An emotional or urgent appeal does not lower this bar. A prior session helping with a
  Class 3 change is not authorization to continue unattended.
- When a change _touches_ this tier, say so explicitly and call out the implications before
  writing code.
- Preserve existing behavior in this tier unless a correctness improvement is the explicit
  intent — and even then, surface it for review rather than silently "fixing" it.

## Class 2 — [FILL IN: your middle tier's name, e.g. "Platform mechanics"]

**Surface:** `[FILL IN — e.g. schema/config surfaces, protocol decoders, anything that
changes a contract other code or other people depend on, but doesn't carry Class 3's
consequence if wrong]`

AI may propose and stage changes in this tier; a human approves before merge.

## Class 1 — [FILL IN: your lowest tier's name, e.g. "Low-risk"]

**Surface:** `[FILL IN — e.g. docs, UI copy, non-safety-critical frontend, comments, lint,
formatting]`

AI may merge changes confined entirely to this tier if the build/tests pass.

---

## The one rule that makes this work

**When a change spans classes, it takes the bar of the highest class it touches.** A
documentation change that also edits a Class 3 function is Class 3, not Class 1. This is
what stops "just a quick docs fix" from becoming the vector for an unreviewed safety-tier
change — the taxonomy has to be evaluated per-change, not per-file or per-PR-title.

## How this feeds the rest of the toolkit

- `ROADMAP.template.md` items carry `Class <1-3>` in their header line; `route_tasks.py`
  reads it to force Class 3 items to the senior model regardless of file count (see
  `AI_HARNESS.template.md` §2, rule 1).
- `AI_HARNESS.template.md`'s fusion protocol (§5) re-classifies whatever a free-tier model
  _proposes_, not just the task as framed — a model can wander into your top tier without
  flagging it (e.g., "simplify the retry logic" creeping into changing what happens on
  payment failure).
- A unanimous, polished multi-model recommendation is still just a recommendation for
  Class 3 — the checklist and human review are not skippable because the proposal looks
  good.
