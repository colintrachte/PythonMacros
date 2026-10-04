# AI Harness — Multi-Model Routing & Fusion (template)

> **Instantiation note:** copy this file to `docs/ai-harness.md` in the target project and
> replace every `[FILL IN: ...]` marker. Everything else — the model roster, the routing
> mechanics, the `pack_task.py` workflow, the fusion protocol — is reusable as written.
> This doc pairs with `REVIEW_TIERS.template.md` (defines the project's top review tier,
> referenced below as "your top tier") and `ROADMAP.template.md` (the task-list format
> `helper_scripts/PMT/route_tasks.py` and `helper_scripts/PMT/pack_task.py` parse).

This doc exists because most of what a coding assistant does is bounded, well-specified work
that a free-tier AI model can do just as well as a paid one — if the task is packaged
correctly. The workflow: send bounded, self-contained tasks out to free-tier models via the
`pack_task.py` Quest Board, then use a stronger model's judgment to verify, reconcile, and
fuse the results back into the codebase. This doc formalizes that workflow so it doesn't have
to be reinvented per project.

**The core constraint, stated plainly:** a free-tier model with no repo access only knows what
fits in the files or text you hand it. Every delegation is therefore a packaging problem
first and a prompting problem second. If the file set doesn't fit the model's budget, no
prompt fixes that — split the task or pick a different model.

---

## 1. The model roster

| Model                                             | Intelligence                        | Hard limits                                                                                                                                                                                                                                                                                                                                                                                                                                                     | Output capture                                                                                        |
| ------------------------------------------------- | ----------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| **[FILL IN: your primary/strongest model]** (you) | High                                | Full repo access via tools                                                                                                                                                                                                                                                                                                                                                                                                                                      | Edits files directly                                                                                  |
| **Gemini**                                        | Low                                 | Up to **10 files per prompt**, 100 MB each (Google-documented); a signed-out web-composer test preserved **32,000 characters** but silently truncated 32,001+ to exactly 32,000. Google publishes no signed-in/plan-specific composer cap, so treat >32k as unsafe                                                                                                                                                                                             | Paste back; verify carefully — low intelligence means check correctness, not just plausibility        |
| **ChatGPT** (free tier)                           | Domain depends on custom GPT used   | ~4 user messages/session; free-tier upload cap **3 files per day** (OpenAI-documented). On Plus, Pro, and Business, pasting over **5,000 characters** automatically becomes a file attachment (OpenAI-documented); OpenAI does not document whether the same conversion applies to Free                                                                                                                                                                    | If converted/uploaded, attach context and paste the task separately                                  |
| **Kimi**                                          | Medium                              | 20 files per session; ~35,000 chars per paste (single observed data point — refine if more data comes in)                                                                                                                                                                                                                                                                                                                                                       | Paste back                                                                                            |
| **Meta.ai**                                       | High                                | No file export — text in, text out only; no reported message-length cap. Observed to sometimes act on an in-prompt "search for it yourself" instruction by attempting its own lookup rather than working only from pasted context — treat anything it claims to have found this way as unverified until checked, same as any other citation (§5.1)                                                                                                              | Paste back; you re-apply as a diff yourself, since it can't hand you a file                           |
| **Perplexity**                                    | Medium, deep research/manual corpus | Perplexity documents **4,000 tokens inline** (~16,000 chars for planning); longer pasted text becomes a file. Its file FAQ lists 4 files at once and 3 uploads/day on Free. Observed to **hard-refuse the entire task**, not just degrade, when an instructed lookup fails — pair lookup instructions with an explicit fallback ("if that fails, don't refuse — answer from what you know and mark it `[UNVERIFIED]`")                                                       | If converted/uploaded, attach context and paste the task separately; verify citations                |
| **Qwen (LM Studio)**                              | Medium                              | No file-count limit; programmatic — see §8                                                                                                                                                                                                                                                                                                                                                                                                                      | `query_model.py` captures response to file; the senior model runs the fusion protocol before applying |
| **OpenRouter (free)**                             | Varies by model                     | Rate limits apply; programmatic — see §8                                                                                                                                                                                                                                                                                                                                                                                                                        | `query_model.py` captures response to file; the senior model runs the fusion protocol before applying |

Free-tier constraints shift with provider policy — if a model's behavior stops matching this
table, update it; don't silently work around a stale assumption. _Roster last re-verified
2026-07-14 (in the kit itself); Kimi's single-paste threshold remains an author
observation, while the Gemini boundary was measured directly while signed out (the signed-in
cap is unpublished) and the ChatGPT/Perplexity conversion rules are provider-documented.
Re-verify when instantiating if it has been a while._

**Manual paste is the primary path.** The programmatic tier (§8, Qwen/OpenRouter via
`query_model.py`) is a convenience for when it's reachable, not the baseline workflow — the
fallback that always works is pasting a context pack into a chat window and copying the
response back out.

**Preference order within free tier vs. paid:** §2's routing rules pick a model by _task
type_. Within whichever tier that lands you in:

- **Free-tier:** start with the most intelligent model available for that task type and step
  down only when you actually hit a limitation (message/file cap reached, or the answer is
  wrong/low-confidence) — don't pre-emptively downgrade.
- **Paid subscriptions:** the reverse. Use the paid model last, or only when every free-tier
  option has failed or is unsuitable for the task.

---

## 2. Routing rules

Task meaning is expressed first as an authored execution mode: `human-judgment`,
`human-physical`, `deterministic-tooling`, `local-ai`, or `network-ai`. Optional durable
`Capability` and `Constraint` fields then narrow the eligible roster (for example
`web-access`, `privacy`, `large-context`, `visual-inspection`, `multi-project-synthesis`,
`paid-only-execution`, or `high-stakes-review`). `helper_scripts/PMT/executor_registry.json`
is the single owner of volatile names, budgets, availability facts, and paid-tier members.
The `paid-ai` route is a capability pool resolved to an eligible roster entry, not vendor
identity embedded in the task. Named `Route: ... (manual)` overrides and tasks without the
new requirement fields retain the legacy behavior below during migration.

For legacy tasks, work through these in order; the first match wins. `[FILL IN: your top tier]` refers to
whatever `REVIEW_TIERS.template.md` names as this project's highest-consequence surface
(safety-critical firmware, financial ledger code, data-loss-risk migrations, etc. — every
project has _some_ candidate for this, even a "boring" one; if truly none applies, say so
explicitly rather than leaving the placeholder).

1. **Is it [FILL IN: your top tier]?** No free-tier model writes top-tier code, ever —
   unattended or not. Free-tier models may produce _read-only research_ that feeds a
   top-tier decision, but the implementation is the senior model + author review only.
2. **Does it require synthesizing multiple projects?** → **Paid AI (`paid-ai`)** in a sandbox
   containing this project and every named external project. Codex and Claude are current
   eligible executors from the model roster, not persisted task identity. The router
   derives this mechanically when a task's file lists span more than one project scope: this
   project when a local artifact is listed, plus each distinct `<name>/...` external reference.
   A task containing only one external project is still single-scope and follows the remaining
   rules.
3. **Is it an external-knowledge lookup** — a library's documented behavior, a vendor
   errata note, an API's actual contract? → **Perplexity** first (it cites sources). A
   domain-specific gut check second, in one shot, if a specialized assistant is available.
4. **Is it a fully-specified, mechanical change confined to ≤3 files** (fill in doc
   comments, a boilerplate function, a single well-specified refactor)? → **Gemini.** Don't
   send it anything that requires judgment calls — low intelligence means ambiguity produces
   confident-sounding wrong answers.
   - **...unless the pack's total size exceeds `context_pack.py`'s `DEFAULT_MAX_CHARS`**
     (100,000 chars — the point a pack needs splitting into multiple paste-sized chunks).
     That much back-and-forth no longer fits "one bounded session" → bump to **Kimi**.
5. **Is it bounded to one component (≤20 files)** — a research task, a refactor proposal, a
   bug analysis scoped to one module/folder? → **Kimi**, using the prompt template in §4.
   - **...unless the pack exceeds `DEFAULT_MAX_CHARS`** → bump to the senior model.
   - **[Programmatic alternative — §8]** Replace Kimi with Qwen for any task that would
     otherwise hit this rule, if a local/networked inference endpoint is reachable. Same
     ≤20-file budget; no paste round-trip.
   - **[Programmatic alternative — §8]** OpenRouter as fallback when Qwen is unreachable.
6. **Is it an architecture or tradeoff judgment call** — "is this overcomplicated,"
   disambiguating a vague spec, a second opinion on a design before committing? → **Meta.ai.**
   It's the free-tier model best suited to judgment calls, not mechanical execution.
7. **Does it span more than ~20 files or cross multiple components with real coupling?** →
   No free-tier model can hold it. This goes to the senior model directly — and the fact
   that one task needed >20 files is itself worth flagging: high fan-out is a "god object"
   smell worth naming, not just powering through.

---

## 3. Building the context pack

A context pack is the exact, minimal file set a model needs to do one task — nothing it has
to go looking for, nothing irrelevant padding out its budget.

**Two sources, prefer the first:**

- **The roadmap's `Context:` / `Implement:` lines** (see `ROADMAP.template.md`). Every
  roadmap item names its required files up front. If the task is a roadmap item, the file
  list already exists — use it.
- **A per-component `CONTEXT.md` file**, when the task is scoped to one module. A short
  orientation file (purpose, owned state, public API, doc pointers) lets a model dropped
  into just that folder self-orient without the whole repo's docs.

**Unit-test context rule:** When creating a task for another AI, do not include code
unit-test files in its exported file lists or context pack unless the task is specifically
about unit tests. Tests that may be needed for an implementation task belong to the later
fusion pass, after the reviewing AI has decided which proposal to implement.

**Assembling the pack:** use `helper_scripts/PMT/context_pack.py` to concatenate the chosen
files into one paste-ready block with a file-count/line-count summary, and a warning if the
set exceeds the target model's budget from §1. By default the bundle is written to
`scratch.txt`; pass `--stdout` to print it instead:

```sh
python helper_scripts/PMT/context_pack.py --model kimi path/to/CONTEXT.md path/to/file.c path/to/file.h
```

**The Quest Board (`pack_task.py`) does all of this for you** — pick tasks from a
sortable/filterable table, preview the assembled pack, page through chunks, edit the
prompt, and either copy/save for manual paste or send straight to a programmatic model
(§8). Its page-2 preview collapses only consecutive completely empty lines in the
transmitted copy; comments, docstrings, whitespace-bearing lines, source files, and CLI
packs stay intact. Run it with:

```sh
python helper_scripts/PMT/pack_task.py
```

The portable pack is always the default and remains available on the pack screen. For an
explicit handoff to an executor whose registry entry advertises `repository-access`, the
maintainer may instead select **Repository-aware** and name that executor. That compact JSON
handoff includes the complete task record and every artifact role/path but no repository file
bodies. Capability validates the choice; price, route name, and vendor never activate it.
Ineligible programmatic targets fall back to the complete portable pack.

For a fresh (non-roadmap) ad-hoc task, write the `Context:` / `Implement:` lines yourself
before picking up the phone to a free-tier model — the discipline of naming the file set up
front is what makes the task portable at all.

### 3.1 Chunking a pack across multiple pastes

`--max-chars` bins whole files into paste-sized chunks. Its CLI default is a generic
100,000 characters (~25k tokens) for model-less use; chat-UI limits are smaller and vary
by provider. Quest Board automatically uses the routed model's tighter known budget. For
the CLI, pass a provider-appropriate `--max-chars`, or `0` to force a single block.

- Chunk boundaries always fall **between** files — a file is never split mid-content. A
  single file bigger than `--max-chars` becomes its own oversized chunk (the script warns;
  that's expected, not an error).
- Chunks land as `scratch.part1of3.txt`, `scratch.part2of3.txt`, etc. With `--stdout`,
  chunks print in order instead, each wrapped in a `CONTEXT PACK — CHUNK i of N` banner.
- Paste chunks in order, in the same chat, one per message. Chunk banners tell the model to
  acknowledge and wait rather than start working on a partial context. Send the §4 prompt
  as the final message, after the last chunk is confirmed received.

### 3.2 Packing a task, step by step

1. Find the item in the roadmap; note its **review tier** and its `Context:`/`Implement:`
   file lists (or write them yourself for an ad-hoc task).
2. Route it: apply §2's rules, or run `python helper_scripts/PMT/route_tasks.py` to (re)stamp
   the roadmap's `**Route:**` annotations so this doesn't have to be re-derived by hand.
3. Assemble the pack via `pack_task.py` (recommended) or `context_pack.py` directly.
4. If manual paste: paste chunk(s) in order first (if any), then the §4 prompt template as
   the closing message.
5. Copy the model's full response back into that task's AI inbox file — don't apply
   anything from memory or a partial copy. The Quest Board's pack screen has a "Save to
   Inbox" button that appends the paste to
   `helper_scripts/PMT/ai_inbox/<ID-fragment>-<title-fragment>.md` for identified tasks (or a
   short title slug for a legacy task; auto-created, gitignored). Names are capped at 20
   characters and the full task ID is recorded at the top of the file; pasting into that
   file by hand works identically
   if you're not using the GUI. Each GUI save can be `Off (verbatim)` or `Conservative`:
   the latter removes only
   excess blank lines outside code fences and whitelisted exact chat/UI boilerplate;
   it never summarizes or paraphrases, and its marker records the character reduction.
   Responses accumulate here across separate chat sessions — nothing is fused until you
   run step 6, so it's fine to collect several models' takes before touching the code.
6. Run the §5 fusion protocol on the inbox file's accumulated response(s) before anything
   touches the codebase. Treat every inbox response as a proposal: verify its claims against
   the current project, think critically about its tradeoffs, and implement only the best
   ideas that serve the actual task. Never apply an inbox response verbatim merely because it
   is polished or unanimous.
7. After the fused implementation is verified and the task is finished, move its inbox file
   from `helper_scripts/PMT/ai_inbox/` to `helper_scripts/PMT/assimilated/`. This records that the
   proposal has been consumed while keeping working and completed material distinct. Both
   folders are local working state and should be gitignored unless the project deliberately
   chooses otherwise.

---

## 4. The task prompt template

The project-specific `helper_scripts/PMT/system_prompt.txt` carries durable identity,
constraints, evidence rules, and review boundaries. This task prompt carries only the
changing assignment. Reuse the structure for code, documents, research, design, data, or
physical-project preparation; replace artifact-location examples with the most precise
locator the project supports.

```text
OUTCOME:
<One observable result this task must produce.>

USE:
<Exact supplied artifacts and what each contributes. Do not search or read beyond these
unless the task explicitly authorizes discovery.>

DO:
1. <Specific bounded operation.>
2. <Any required comparison, validation, or decision.>
3. <Where the deliverable goes: respond inline or name an output artifact.>

ACCEPT WHEN:
- <Falsifiable completion condition.>
- <Required evidence or verification.>

OUTPUT:
Return only <exact deliverable and format>. Support factual claims with the most precise
available artifact location (`path:line`, page, sheet/cell, timestamp, or object name).
Write [NOT FOUND] when supplied evidence is absent. Label inferences. Do not invent facts,
results, or missing context; do not widen scope, add dependencies, or modify artifacts
unless explicitly authorized.
```

**Per-model adjustments:**

- **Gemini:** spell out the exact expected output format; it will not infer one. State the
  file(s) to change explicitly — don't make it figure out which file owns the change.
- **ChatGPT:** the entire template goes in message 1, including the full context pack
  inline (not as an attachment, given the upload cap). Budget remaining messages for
  follow-up questions _it_ asks, not ones you initiate.
- **Kimi:** can take a full component folder via `CONTEXT.md` + every source file; ask for
  a structured finding list (severity/location/current/proposed) so it's easy to triage.
- **Meta.ai:** since it can't return files, explicitly ask for unified-diff-style output
  (`-`/`+` lines) rather than a full rewritten file — much faster to re-apply by hand.
- **Perplexity:** ask explicitly for source citations/links, not just an answer.

---

## 5. The fusion protocol (senior model's job)

When responses come back from one or more free-tier models, do not paste them into the
codebase. Run them through the same scrutiny as any unverified claim:

1. **Verify citations.** A `file:line` claim is checked with a real search/read, not
   trusted because it looks specific. `[NOT FOUND]` markers are honest; confident-sounding
   fabricated line numbers are not — and low-intelligence models produce these more often.
2. **Classify before merging.** Apply this project's review-tier taxonomy
   (`REVIEW_TIERS.template.md`) to whatever the response _proposes_, not to the task as
   originally framed — a free-tier model can wander into the top tier without flagging it.
3. **Reconcile disagreement, don't average it.** If two models propose conflicting
   approaches, that's a signal to think about the tradeoff yourself, not to split the
   difference. State which one you're taking and why in the commit/PR description.
4. **Surgical application still applies.** A free-tier model's output is a _proposal_, not
   a diff to apply verbatim — pull only what answers the actual task; don't import its
   incidental reformatting or unrelated "improvements."
5. **Set up needed unit tests at fusion.** When implementing an inbox proposal, the
   reviewing AI adds or updates any unit tests needed to verify the accepted change. Those
   tests are fusion work, not context exported to the proposing AI, unless the original
   task was specifically about unit tests.
6. **A free-tier model never gets the last word on your top tier.** Even a unanimous
   three-model recommendation on top-tier code is still "AI may analyze and propose" —
   author review (and any checklist your top tier requires) is not skippable because the
   proposal looks polished.

---

## 6. Worked example

Task: "Implement `<some bounded function>`" — a real open roadmap item, mid review tier,
scoped to one file.

1. **Route it:** mid tier, single-component, well under 20 files → Kimi (rule 5).
2. **Pack it:** the roadmap already lists `Implement:` and `Context:` file lines. Add the
   component's `CONTEXT.md` as the orientation file, then run `pack_task.py` (or
   `context_pack.py` directly for the same result from the command line).
3. **Prompt it** using the §4 template with the specific, bounded task description.
4. **Fuse it:** read the model's proposed change, verify it actually compiles/type-checks
   against the existing surrounding code (don't trust the paste), confirm it doesn't touch
   your top tier, then apply it yourself.

---

## 7. Keeping this system from rotting

- If a component's `CONTEXT.md` drifts from the code (new files, new owned state), fix it
  in the same change that caused the drift.
- If a model's actual constraints turn out to differ from §1 (a session takes more files
  than expected, a message limit is tighter or looser), update the table — don't let the
  document quietly become fiction.
- `helper_scripts/PMT/executor_registry.json` is canonical for per-executor budgets and
  eligibility facts. Keep §1 as an explanatory snapshot; when behavior changes, update the
  registry and refresh the prose in the same commit.
- The scripts intentionally take an explicit file list only — no directory or glob
  expansion. That's not a missing feature; it's the same discipline as the
  `Context:`/`Implement:` lines in the roadmap. Auto-expanding a directory would silently
  widen a pack past what was actually scoped for the task.

---

## 8. The programmatic tier (Qwen + OpenRouter)

Rule 5's programmatic alternatives route tasks to models called via
`helper_scripts/PMT/query_model.py`, eliminating the manual paste round-trip. Everything else —
the context pack, the prompt template, the fusion protocol — stays the same.

**The two models:**

- **Qwen via LM Studio** — a local (or Tailscale-reachable) LM Studio instance. No
  per-token cost; no auth key required by default. The script queries `/v1/models` to
  discover the currently loaded model automatically. Set `QWEN_LM_STUDIO_URL` to the
  network address of the machine running LM Studio when away from home; the default
  `http://localhost:1234/v1` works on the same machine/network.
- **OpenRouter (free tier)** — `https://openrouter.ai/api/v1` with `$OPENROUTER_API_KEY`.
  Only free-tier models are authorized; no spend permitted for an automated process.

**What `query_model.py` does:** assembles the file list into the same fenced context pack
as `context_pack.py`, prepends the task text, POSTs to the model's OpenAI-compatible
endpoint, and writes the raw response to `--out` or stdout. Run the §5 fusion protocol on
that file before any change touches the codebase.

**System prompt:** `query_model.py` and `pack_task.py` both load a project-specific system
prompt from `helper_scripts/PMT/system_prompt.txt` if that file exists, falling back to a
generic guardrail prompt otherwise. Create `helper_scripts/PMT/system_prompt.txt` for this
project with the same hard constraints named in §4's template (language/runtime, forbidden
patterns, dependency policy) — see `helper_scripts/PMT/README.md`.

**What does NOT change:**

- Your top tier is off-limits to both models, programmatic or not.
- The fusion protocol (§5) still applies in full — the script output is a proposal, not a
  commit.

**Example usage:**

```sh
python helper_scripts/PMT/query_model.py \
  --model qwen \
  --task-file task.txt \
  --out response.md \
  path/to/CONTEXT.md path/to/file.c path/to/file.h

# Same task via OpenRouter if the local endpoint is down
python helper_scripts/PMT/query_model.py \
  --model meta-llama/llama-3.3-70b-instruct:free \
  --task-file task.txt \
  --out response.md \
  path/to/CONTEXT.md path/to/file.c path/to/file.h
```

**Environment variables:**

| Variable             | Required for          | Default                    |
| -------------------- | --------------------- | -------------------------- |
| `QWEN_LM_STUDIO_URL` | `qwen` model          | `http://localhost:1234/v1` |
| `OPENROUTER_API_KEY` | OpenRouter models     | (none — required)          |

**Quest Board conveniences:** on the Configure & Send screen you can enter the OpenRouter
key directly instead of via the env var, and tick _Remember on this machine_ (off by
default) to save it to `~/.pmt_openrouter_key` — plaintext, but kept outside any repo so it
can't be committed. The _Fetch free models_ button pulls OpenRouter's live `:free` list
into the model dropdown, so the built-in fallback list never has to be hand-verified. (The
`query_model.py` CLI still reads `OPENROUTER_API_KEY` only.)
