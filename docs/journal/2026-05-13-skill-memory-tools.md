# 2026-05-13 Skill Memory Tools

## Context

Skill memory existed as a runtime manager and markdown file structure, but the agent could not write or inspect it through the OpenAI tool surface.

## Change

The following tools were added:

- `record_learning`
- `record_error`
- `record_feature_request`
- `record_policy_candidate`
- `record_regression_test`
- `summarize_skill_memory`
- `list_skill_memory`

`SkillMemoryManager` is initialized in `harness/agent_harness.py` and passed into `build_tool_handlers`.

## Safety Notes

The new record tools require `memory.write`. Read-like memory summary/list tools require `skill.load`. Default and high-security policies include these tools explicitly so SafeHarness does not block them as unknown tools.

## Follow-Up

The next step is to add a proper `MemoryGuard` around `memory.write.before` so content can be inspected for long-term memory poisoning before markdown writes.
