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
- Review items include the guarded tool name, tool arguments, target files, event type, source, reason, risk type, severity, proposed change, evaluation plan, rollback plan, status, and creation time.
- Approving a review changes its status to `approved` and writes a patch preview. No patch is applied automatically.
- `/apply` is limited to approved `load_skill`, `skill.regression_case`, `skill.promotion`, `skill.creation`, and `file.write` reviews. `load_skill` apply executes the reviewed skill load and updates `last_loaded_skill`; it does not create a patch preview. Regression-case apply writes reviewed eval cases and records `.reviews/apply_audit.jsonl`; skill-promotion apply is refused until `skills/<skill>/eval/cases.yaml` contains both positive and negative cases for the same `source_promo_id`. Skill-creation apply writes the reviewed `SKILL.md` and eval placeholder files and records an initial skill version. File-write apply writes only the reviewed target and content.
- Guarded edits include `SKILL.md`, `AGENTS.md`, `safety/**`, `tools/**`, and `harness/prompt.py`.
- Approval-gated `load_skill` calls explicitly tell the user to approve and then apply the generated review before treating the skill as loaded. Automatic memory capture skips follow-up preference text while that load approval is pending, preventing unloaded-skill instructions from becoming durable rules. Once a skill is loaded, a repeated request to load the same skill returns `already loaded` and does not create a duplicate review.
- Automatic memory capture skips status-only `load_skill` turns, including successful load messages, already-loaded messages, and applied `load_skill` reviews. These print `auto_memory: skipped load_skill status message.` and do not update `LEARNINGS.md` or create promotion candidates.
- Automatic memory capture skips verification reads of review queue files, skill version snapshots, active `SKILL.md` files, and eval case files before calling the classifier. This covers `read_file`, `Get-Content`, and `Select-String` reads of `.reviews/**`, `.skills_versions/**`, `skills/*/SKILL.md`, and `skills/*/eval/cases.yaml`, and prints `auto_memory: skipped verification read_file result.` instead of writing memory.
- Successful `skill.promotion` applies also write a skill evolution audit event to `.audit/events.jsonl`, after recording the version snapshot, patch diff, eval result, source promotion, skill review, and regression review linkage.
- Successful `skill.creation` applies write an initial skill-version snapshot so the created skill can participate in version browsing and rollback review creation.

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
- Add an explicit apply confirmation step for approved review items.
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
