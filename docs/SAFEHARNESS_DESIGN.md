# SafeHarness Design

## Purpose

SafeHarness upgrades the Agent Harness into a policy-mediated runtime. Instead of checking only user input, it emits `RuntimeEvent` objects at key intermediate states and evaluates them through a unified `PolicyEngine`.

## Current Implementation

Implemented in `safety/`:

- `events.py`: `RuntimeEvent`
- `decisions.py`: `PolicyDecision`
- `risk_types.py`: risk type constants
- `policy.py`: safe defaults, lightweight YAML parsing, and merge helpers
- `policy_config.py`: policy selection, `SAFETY_POLICY` resolution, and public loader API
- `policy_engine.py`: guard orchestration
- `audit.py`: audit writer with basic secret redaction
- `guards/input_guard.py`
- `guards/tool_call_guard.py`
- `guards/tool_result_guard.py`
- `guards/permission_guard.py`
- `policies/default_policy.yaml`
- `policies/high_security_policy.yaml`

## RuntimeEvent

Each event includes:

- `event_id`
- `run_id`
- `parent_event_id`
- `event_type`
- `actor`
- `source`
- `target`
- `payload`
- `metadata`
- `created_at`

Currently wired event types:

- `user_input.received`
- `llm.request.before`
- `llm.response.after`
- `tool.call.before`
- `tool.execution.before`
- `tool.execution.after`
- `tool.result.before_model`

Reserved event types:

- `prompt.build.before`
- `task.create.before`
- `task.update.before`
- `message.send.before`
- `teammate.spawn.before`
- `memory.write.before`
- `skill.load.before`
- `tool.registry.load`

## PolicyDecision

Policy decisions support:

- `allow`: continue.
- `warn`: record risk and continue.
- `sanitize`: mutate payload and continue.
- `require_approval`: stop the current action and return an approval-required message.
- `block`: stop the action.

## Policy Loading

`PolicyEngine` accepts an already loaded policy dictionary. Policy selection and loading live in `safety/policy_config.py`.

Current selection behavior:

- `SAFETY_POLICY=default` -> `safety/policies/default_policy.yaml`
- `SAFETY_POLICY=high_security` -> `safety/policies/high_security_policy.yaml`
- unset `SAFETY_POLICY` -> default policy

If the selected file is missing or malformed, loading falls back to built-in safe defaults.

The loaded policy is a deep merge of:

1. `SAFE_POLICY_DEFAULT`
2. the YAML file contents

This means missing fields keep safe defaults instead of becoming permissive.

Current YAML support is intentionally lightweight and dependency-free. It supports the repository policy format: nested mappings, scalar values, booleans, and lists of scalars.

## Policy Files

`safety/policies/default_policy.yaml` is the local development policy. It gives the lead actor broad local capabilities, while approval-gating high-risk operations such as shell execution, background jobs, and teammate spawning.

`safety/policies/high_security_policy.yaml` is the locked-down policy. It keeps a narrower capability set, blocks unknown tools, blocks shell by default unless the command matches an allowlist, requires approval for edits to `AGENTS.md`, `docs/**`, `harness/**`, `safety/**`, and `tools/**`, and blocks more exfiltration and prompt-injection patterns.

Policy schema sections:

- `policy_name`, `mode`, `version`
- `defaults`
- `risk_thresholds`
- `capabilities`
- `tools`
- `prompt_injection`
- `memory`
- `audit`

## Guards

Guards are configuration-driven. `PolicyEngine` loads the policy and passes it into each guard.

### InputGuard

Reads:

- `prompt_injection.direct.warn_patterns`
- `prompt_injection.direct.block_patterns`

Suspicious instruction override text can warn. Explicit system-prompt disclosure, safety bypass, or safety disabling attempts block according to policy.

### ToolCallGuard

Reads per-tool configuration from `tools.<tool>`:

- `blocked_patterns`
- `require_approval_patterns`
- `blocked_paths`
- `require_approval_paths`
- `blocked_content_patterns`
- `blocked_prompt_patterns`
- `default_action`
- `risk`

This guard handles command risk, protected paths, outbound secret patterns, and unsafe teammate prompts.

### ToolResultGuard

Reads:

- `prompt_injection.indirect.sanitize_patterns`
- `prompt_injection.indirect.block_patterns`

All tool results are treated as untrusted. Before returning a tool result to the model, SafeHarness wraps it:

```xml
<untrusted_tool_result tool="tool_name">
...
</untrusted_tool_result>
```

If policy patterns match, the result is sanitized or blocked.

### PermissionGuard

Reads:

- `capabilities.<actor>`
- `tools.<tool>.capability`
- `defaults.unknown_tool`
- `tools.<tool>.default_action`

Unknown tools block by default. Missing actor capabilities block. Approval-gated tools warn for the lead and require approval for non-lead actors unless a stricter guard blocks first.

Skill memory tool capability mapping:

- `record_learning`, `record_error`, `record_feature_request`, `record_policy_candidate`, `record_regression_test`, `classify_and_record_learning_signal`, `propose_memory_promotion`, and `evaluate_evolution_candidate` require `memory.write`.
- `summarize_skill_memory` and `list_skill_memory` require `skill.load`.

Current runtime behavior:

- `require_approval` creates a pending item in the local review queue and stops the current action.
- The user-facing response includes the `review_id`, and the guarded tool call is not executed.
- Approving a review writes `.reviews/patches/<review_id>.diff` as a preview only. No patch is applied until a later explicit confirmation path exists.
- Guarded edits include `SKILL.md`, `AGENTS.md`, `safety/**`, `tools/**`, and `harness/prompt.py`.

## Audit

`AuditLogger` writes the configured audit path. In the default policy this is:

```text
.audit/events.jsonl
```

Records include:

- event
- decision
- timestamp
- actor
- tool
- risk type
- severity
- reason
- redacted payload summary capped by `audit.max_payload_chars`

Do not commit `.audit/`.

## Future Work

- Add policy selection through environment variable or CLI flag.
- Add a real approval queue so `require_approval` can pause instead of converting to `block`.
- Add `ToolRegistryGuard` for tool allowlist, schema hash, handler matching, and malicious descriptions.
- Add `MemoryGuard` for `memory.write.before` and skill-content safety scanning.
- Add explicit `skill.load.before` event before skill body injection.
- Add `task.create.before`, `message.send.before`, and `teammate.spawn.before` manager-level events.
- Add LLM Judge as a second-pass classifier for ambiguous cases.
- Add enterprise policy-center integration for centrally managed allowlists and deny rules.
- Add formal policy schema validation and startup diagnostics.

## Change Rules

- Any change to events, decisions, guards, permissions, audit, or policy behavior must update this document.
- Keep tool results untrusted by default.
- Keep `.audit/` ignored.
- Do not weaken block rules without recording the reason in `docs/CHANGELOG.md`.
