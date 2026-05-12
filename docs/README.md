# Developer Docs

This directory is the documentation home for harness_agent. It is intentionally split into small, living documents rather than one large document.

## Start Here

- `CHANGELOG.md`: current implementation state and iteration history. Read this first when judging what changed most recently.
- `HARNESS_DESIGN.md`: core Agent Harness architecture.
- `RUNTIME_BACKEND_DESIGN.md`: runtime backend abstraction and production replacement plan.
- `SAFEHARNESS_DESIGN.md`: safety events, policy decisions, guards, permission model, and audit design.
- `journal/`: process notes, temporary plans, and historical snapshots.

## Documentation Governance

- Update `CHANGELOG.md` for every larger code change.
- Update the matching design document when architecture changes.
- Update `SAFEHARNESS_DESIGN.md` when changing safety events, guards, policy decisions, permissions, or audit behavior.
- Update `RUNTIME_BACKEND_DESIGN.md` when changing backend interfaces or LocalBackend behavior.
- Put investigation notes and staged plans in `journal/YYYY-MM-DD-topic.md`.

## Conflict Resolution

When documents disagree, use this order:

1. Code implementation + `CHANGELOG.md`
2. Design documents
3. Journal notes

Journal files are useful history, not the source of current truth.
