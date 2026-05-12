# SafeHarness Design

## Purpose

SafeHarness upgrades the Agent Harness into a policy-mediated runtime. Instead of checking only user input, it emits `RuntimeEvent` objects at key intermediate states and evaluates them through a unified `PolicyEngine`.

## Current Minimal Implementation

Implemented in `safety/`:

- `events.py`: `RuntimeEvent`
- `decisions.py`: `PolicyDecision`
- `risk_types.py`: risk type constants
- `policy_engine.py`: guard orchestration
- `audit.py`: `.audit/events.jsonl` writer with basic secret redaction
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

## Guards

### InputGuard

Detects direct prompt injection phrases such as:

- `ignore previous instructions`
- `忽略之前的指令`
- `忽略系统提示`
- `reveal system prompt`
- `泄露系统提示词`
- `bypass policy`
- `绕过安全策略`
- `disable safety`
- `关闭安全检查`

Suspicious overrides can warn; explicit system-prompt disclosure or safety bypass attempts block.

### ToolCallGuard

Checks high-risk tool usage:

- dangerous shell/background commands
- protected file writes or edits, including `.env`, tool schema, prompt, and safety policy paths
- outbound message content that appears to contain secrets or system prompt content
- unsafe teammate prompts that request bypass, stealth, or hidden behavior

### ToolResultGuard

Treats all tool results as untrusted. Before returning a tool result to the model, it wraps the result:

```xml
<untrusted_tool_result tool="tool_name">
...
</untrusted_tool_result>
```

If prompt-injection phrases are detected in the tool output, the result is sanitized.

### PermissionGuard

Defines tool capabilities:

- `shell.execute`
- `file.read`
- `file.write`
- `file.edit`
- `task.manage`
- `message.send`
- `teammate.spawn`
- `background.run`
- `skill.load`
- `memory.write`

Each tool maps to required capabilities. The current lead run receives `DEFAULT_LEAD_CAPABILITIES`. Teammate-specific reduced permissions are reserved for the next stage.

## Audit

`AuditLogger` writes `.audit/events.jsonl`. Records include:

- event
- decision
- timestamp
- actor
- tool
- risk type
- severity
- reason
- redacted payload summary

Do not commit `.audit/`.

## Policy Files

`safety/policies/default_policy.yaml` and `high_security_policy.yaml` are placeholders. Current rules are coded in guards. Future work should load YAML policy configuration into `PolicyEngine`.

## Future Work

- Add `ToolRegistryGuard` for tool allowlist, schema hash, handler matching, and malicious descriptions.
- Add `MemoryGuard` for `memory.write.before` and skill-content safety scanning.
- Add explicit `skill.load.before` event before skill body injection.
- Add `task.create.before`, `message.send.before`, and `teammate.spawn.before` manager-level events.
- Add LLM Judge as a second-pass classifier for ambiguous cases.
- Add enterprise policy-center integration for centrally managed allowlists and deny rules.

## Change Rules

- Any change to events, decisions, guards, permissions, audit, or policy behavior must update this document.
- Keep tool results untrusted by default.
- Keep `.audit/` ignored.
- Do not weaken block rules without recording the reason in `docs/CHANGELOG.md`.
