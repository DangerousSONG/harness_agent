# 2026-05-12 Docs Governance

## Context

The project has moved through two large architecture steps:

1. Runtime Backend refactor: local files/threads/dicts moved behind backend interfaces.
2. SafeHarness minimal runtime: safety events, policy decisions, guard evaluation, and audit logging were added.

The next risk is knowledge drift. A single README is not enough to explain current state, historical reasoning, hard constraints, and future work without becoming stale.

## Decision

Create a sustainable documentation structure:

- `AGENTS.md` for required agent entry rules and hard constraints.
- `docs/README.md` as the documentation index.
- `docs/CHANGELOG.md` as the first place to inspect current implementation state.
- Focused design docs for Harness, Runtime Backend, and SafeHarness.
- `docs/journal/` for process notes and historical snapshots.

## Current Priority Rules

Documentation conflict priority:

1. Code implementation + `docs/CHANGELOG.md`
2. Design documents
3. Journal notes

This means journal entries may become stale. They should preserve reasoning, not override current implementation.

## Follow-Up

- Future code changes should keep changelog entries small but explicit.
- Runtime Backend changes should update `RUNTIME_BACKEND_DESIGN.md`.
- Safety changes should update `SAFEHARNESS_DESIGN.md`.
- If a change spans multiple subsystems, update all affected design docs and add a journal note when useful.
