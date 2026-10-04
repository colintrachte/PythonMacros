# Contributing to [FILL IN: project name] (template)

> **Instantiation note:** copy to `CONTRIBUTING.md` and fill in the markers. Skip entirely
> for a solo, closed project with no external contributors — this file earns its keep once
> someone other than you (human or AI, in a fresh session with no memory of past decisions)
> needs to ramp up from scratch.

Thanks for helping improve `[FILL IN: project name]`.

`[FILL IN: one or two sentences — what this project is and what contributions should
preserve: clarity, modularity, maintainability, whatever this project's actual priorities
are per its CLAUDE.md/charter.]`

## Project goals

When contributing, optimize for the following:

- `[FILL IN: 3-6 concrete priorities — e.g. "clear separation between X and Y," "small,
reusable components with well-defined responsibilities," "long-term maintainability by
both humans and AI," "strong debug visibility," "minimal duplication and safe defaults,"
"preserved existing behavior unless a change is explicitly intended."]`

## Before you start

Before opening an issue or pull request, read:

- `[FILL IN: the project's core docs — README, architecture doc, protocol/API doc, roadmap]`

If your change affects behavior, wiring, boot flow, protocol details, or build
configuration, update the relevant docs in the same change set.

## What to contribute

Helpful contributions include:

- Bug fixes.
- `[FILL IN: project-specific categories — e.g. "board support additions," "new platform
targets," "protocol/API changes with matching documentation"]`
- Diagnostics, logging, and troubleshooting enhancements.
- Doc-comment and documentation cleanup.
- Refactoring that improves modularity without changing behavior.

## Architecture expectations

- `[FILL IN: this project's specific structural conventions — module layout, minimal public
interfaces, separation of concerns, whatever CLAUDE.md §8 already establishes]`
- Reuse existing helpers before introducing new abstractions.
- Avoid duplicated logic.
- Keep public interfaces small and stable.

## Code style

Follow the project's style rules — see `CLAUDE.md` §6. If touching shared code, make the
implementation easy to read, debug, and extend.

## Documentation rules

Documentation is part of the codebase. See `CLAUDE.md` §6 for the comment-style contract
(short-lived inline notes vs. durable API doc blocks) and how thorough documentation should
be for this project.

## Development setup

`[FILL IN: toolchain, how to clone/build/run, common editor/IDE shortcuts if this project
has a standardized setup]`

## Testing expectations

Before submitting changes, verify them locally. At minimum, test:

- `[FILL IN: this project's actual smoke-test list — build succeeds, the thing it does
still works end to end, whatever "still works" means concretely here]`

For timing, memory, concurrency, or anything hard to unit-test, call those out explicitly
in the pull request notes.

## Bug reports

When reporting a bug, include:

- `[FILL IN: environment/version info relevant to this project]`
- Clear reproduction steps.
- Logs, stack traces, or screenshots.

The more specific your report, the easier it is to reproduce and fix.

## Pull requests

A good pull request should include:

- A short summary of the change and why it's needed.
- What you tested and how.
- Any documentation updates.
- Relevant logs, screenshots, or traces if helpful.

## Commit messages

Write commit messages that describe the actual change clearly. Conventional Commits
(`type(scope): summary`) works well if this project doesn't already have its own
convention: imperative summary under ~72 chars, no trailing period, body explains "why"
when useful. Commit in small, logical chunks. Never commit secrets, build artifacts, or
dependencies.

## License

By contributing to this repository, you agree that your contributions will be licensed
under `[FILL IN: project license]`.
