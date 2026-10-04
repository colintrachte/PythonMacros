# Forge and Steward

> **Instantiation note:** copy this file to `FORGE_AND_STEWARD.md` and tailor the examples,
> evidence, and protected contracts to the project. The project's own rulebook, charter, and
> review tiers remain authoritative, especially for scope, safety, and change classification.

Use this guide to choose how to approach work before selecting an executor or implementation.
Forge and Steward are reasoning postures, not lifecycle statuses or model-routing labels.

## Decide before applying a stage

Before each stage, record a short decision:

1. **Does this stage apply?** Mark it **required**, **preferred**, or **not applicable**. A
   not-applicable decision needs a reason; silence is not a decision.
2. **What does it depend on?** A **hard prerequisite** means proceeding would make the result
   invalid, unsafe, or knowingly stale. A **soft preference** means the order improves evidence,
   reuse, or synergy but can be overridden deliberately.
3. **What must survive?** Name existing behavior, compatibility, evidence, or safety properties
   that the work must preserve.
4. **What closes the stage?** Name the decision or evidence produced. Do not advance merely
   because an activity was performed.

Use the lightest decision record proportional to the task. One sentence can cover an obvious
stage. Consequential or disputed choices belong in the task record or fusion artifact.

## Choose the work mode

Use **Forge** when the problem or mechanism is still uncertain. Typical cases:

- a new capability or user workflow;
- an experiment serving a concrete project goal;
- a component whose current design has proved inadequate;
- a decision with two or more credible implementations and meaningful tradeoffs.

Use **Steward** when the intended behavior is already known. Typical cases:

- a bug, regression, or performance problem;
- maintenance of an existing contract or subsystem;
- a focused refactor that must preserve behavior;
- documentation, dependency, or build upkeep.

Choose **Forge + Steward** when a new or uncertain capability must be developed while an
existing feature or contract remains protected. Name the boundary explicitly: what is being
forged, what is being stewarded, and which regression evidence protects it. Split the task only
when the two slices can be completed independently without losing that protection.

State the selected work mode before substantial work. Re-evaluate it at stage boundaries:
evidence may turn a Forge question into known Steward work, or reveal that a supposed repair
needs a bounded return to Forge.

Work mode does not determine the review class. Classify every proposed change under the
project's review tiers; the highest-risk surface touched controls the review and merge bar.

## Forge: prove a new approach

### 1. Scope

Write down:

- the user, milestone, or concrete use case being served;
- the problem, constraints, and relevant non-goals;
- the smallest observable result that would count as success;
- assumptions that need evidence.

Reframe or reject the task if it solves the wrong problem. Do not design a general subsystem
when one concrete use case can establish the need first.

### 2. Diverge when it matters

Produce two or three approaches that differ in mechanism, not wording. Compare them against the
project charter, compatibility contracts, risk boundaries, and implementation cost.

Skip divergence for obvious or low-risk work. Use parallel people or AI models only when
independent approaches are likely to change the decision. Follow `docs/ai-harness.md` when using
external models.

### 3. Fuse

Select or synthesize one approach. Record:

- why it is the simplest credible option;
- what was rejected and why;
- what evidence could reverse the decision;
- the resulting fused response or decision.

Resolve architectural tradeoffs before implementation when the change crosses module boundaries
or touches more than two files.

### 4. Temper

Review the candidate from two angles:

- **Correctness:** failure modes, constraints, compatibility, cleanup, and the applicable
  high-risk checklist.
- **Usefulness:** whether it makes a real workflow easier to operate, verify, or maintain without
  speculative complexity.

These can be separate reviews when the change is consequential. A top-tier change always
requires the project's named human review; AI agreement never substitutes for that gate.

### 5. Prove

Implement the smallest vertical slice that can fail honestly. Define the check before building,
then run it on the real code and, when relevant, the real target environment. A design document
or mock alone is not proof.

Record the command, test, measurement, or observed behavior. If the result fails, revise the
chosen approach or return to divergence.

### 6. Keep only what earned reuse

After the result works, capture a reusable pattern only if another concrete use case needs it.
Otherwise leave it as a focused implementation.

Forge is complete when the result exists, its success check passes, and the change meets its
review-class bar.

## Steward: preserve and improve known behavior

### 1. Guard

Identify the contract that must remain true:

- expected behavior and public interfaces;
- safety properties or protected boundaries;
- resource, timing, or compatibility constraints;
- the current known-good test or reproduction.

Classify the change before editing. Do not broaden the task while diagnosing it.

### 2. Measure

Reproduce the problem or establish a baseline with available evidence: tests, logs, traces,
size, timing, resource use, or direct observation. If a useful measurement is unavailable, say
what proxy is being used.

### 3. Audit

Find the root cause. Distinguish between:

- an implementation defect in a sound design; and
- evidence that the design or contract no longer fits the project.

Do not patch a symptom when the failure can be reproduced below it.

### 4. Repair or prune

Make the smallest change that fixes the measured cause. Preserve existing behavior outside the
stated scope and remove only waste made obsolete by this change.

Before removing apparent redundancy, determine whether it is resilience. Documentation, a
known-good fallback, recovery capacity, and safety margin are not waste merely because the common
path does not use them.

### 5. Lock

Run the relevant regression checks and compare them with the baseline. Update tests, contracts,
and documentation needed to make the known-good state repeatable. Report anything that could not
be verified.

Steward is complete when the original problem is reproduced or measured, the root cause is
addressed, regressions are checked, and the change meets its review-class bar.

## Escalate from Steward to Forge

Move only the affected component back to Forge when evidence shows the design itself is the
problem. Triggers include:

- the same root cause returning after a verified repair;
- two consecutive measurements showing unacceptable drift;
- a required use case that cannot be supported without repeatedly breaking the current boundary.

Do not use escalation as permission for a repository-wide redesign.

## Sequence roadmap work

Roadmap order is an engineering input, not just display order. The authored order in
`docs/roadmap.md` is the default recommended sequence. Use permanent task relationships when that
order carries additional meaning:

- **`Blocked by` — hard prerequisite.** Use when starting early would be unsafe, invalid,
  knowingly stale, or require redoing artifacts after the predecessor lands. Quest Board must
  not package the task until every blocker is Shipped.
- **`Prefer after` — soft ordering preference.** Use when later work benefits from the
  predecessor's decisions, files, fixtures, or context, but can still produce a valid result
  alone. Quest Board warns and requires an intentional override.
- **No relation.** Use only when either order produces equally valid work. Similar topic or
  shared files alone do not prove a dependency.

Do not place dependent tasks in one parallel execution pack. When a task changes a contract,
generated artifact, file layout, or architectural decision, review downstream tasks that name
those inputs before marking the predecessor Shipped.

## Task prompt

Use this at the start of substantial work:

> Work mode: Forge, Steward, or Forge + Steward, and why?
>
> Change class: what review tier applies?
>
> Outcome: what observable result must exist?
>
> Scope: what files, subsystem, or use case is involved?
>
> Constraints: what must not change?
>
> Order: what is hard-blocking, what is merely preferred, and why?
>
> Stage decisions: which stages are required, preferred, or not applicable?
>
> Evidence: what test or measurement will prove the result?

Classify changes to this guide by their practical effect. Wording-only clarification is normally
low risk; changes that redirect future engineering work take the class warranted by that blast
radius; changes to high-risk gates take the project's highest class.
