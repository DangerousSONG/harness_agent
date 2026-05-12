# Changelog

This file records meaningful project iterations. When judging current state, read this before older design notes.

## 2026-05-12

### SafeHarness Policy Configuration

- Added `safety/policy.py` with built-in safe defaults, lightweight YAML parsing, deep-merge fallback behavior, and actor capability lookup.
- Added `safety/policy_config.py` and connected policy selection to `SAFETY_POLICY`.
- Changed `PolicyEngine` to accept a loaded policy dictionary.
- Updated `InputGuard`, `ToolCallGuard`, `ToolResultGuard`, and `PermissionGuard` to read policy configuration.
- Filled `safety/policies/default_policy.yaml` for local development mode.
- Filled `safety/policies/high_security_policy.yaml` for stricter locked-down mode.
- Connected audit path, enabled flag, and payload summary length to the loaded policy.
- Current `require_approval` decisions are converted to `block` at runtime because an approval queue is not implemented yet.
- Added `scripts/safety_smoke_test.py`.
- Added `requirements.txt` with the current minimal runtime dependencies.

### Policy Validation

- `python -m compileall harness runtime tools safety`
- `"q" | python .\harness\agent_harness.py`
- `python .\scripts\safety_smoke_test.py`
- Policy loading smoke test for default policy and bash approval behavior.
- Missing policy fallback smoke test.
- High-security direct prompt injection block smoke test.

### Added

- Created documentation governance structure:
  - `AGENTS.md`
  - `docs/README.md`
  - `docs/HARNESS_DESIGN.md`
  - `docs/RUNTIME_BACKEND_DESIGN.md`
  - `docs/SAFEHARNESS_DESIGN.md`
  - `docs/journal/2026-05-12-docs-governance.md`
- Documented rules for changelog updates, design document ownership, journal usage, and validation.

### Current Architecture Snapshot

- The project is a SafeHarness-style Agent Harness built around OpenAI Chat Completions tool calling.
- Runtime state is routed through backend abstractions under `runtime/backends`.
- Local mode uses `LocalBackend` and remains the default runtime.
- Safety interception is implemented through `safety/` and wired into `harness/loop.py`.
- OpenAI tool schema compatibility remains a hard constraint.

### Validation

- Documentation-only change. Runtime validation should still use:

```powershell
python -m compileall harness runtime tools safety
"q" | python .\harness\agent_harness.py
```

## Earlier 2026-05-12 Iterations

### Runtime Backend Refactor

- Added `runtime/backends` abstraction layer.
- Introduced `TaskStore`, `MessageStore`, `JobQueue`, `AgentRunner`, and `ReviewStore`.
- Migrated file, message, background, and teammate infrastructure into `LocalBackend`.
- Refactored managers to depend on backend interfaces instead of direct filesystem/threading primitives.

### SafeHarness Minimal Runtime

- Added `safety/` with `RuntimeEvent`, `PolicyDecision`, `PolicyEngine`, guards, risk types, and audit logging.
- Wired safety evaluation into `harness/loop.py` around LLM request/response and tool execution.
- Added `.audit/` ignore rule.
- Updated system prompt to treat tool results as untrusted data.
