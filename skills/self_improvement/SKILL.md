---
name: self_improvement
description: Cross-skill learning manager for structured skill memory records and improvement candidates.
---

# self_improvement

This skill is a cross-skill learning manager. Its job is to help record meaningful learning signals into the correct skill memory files, without turning ordinary conversation into permanent memory.

## Core Rules

1. Do not automatically record every conversation.
2. Record only when there is a clear learning signal.
3. Never store raw secrets, tokens, API keys, passwords, private keys, or credentials.
4. Do not automatically modify any `SKILL.md`.
5. Do not automatically modify `AGENTS.md`.
6. Do not automatically modify safety policy files.
7. Do not automatically modify `tools/schemas.py`, `tools/handlers.py`, or `harness/prompt.py`.
8. First record memory or create a candidate suggestion.
9. Any long-term rule change requires explicit user confirmation before editing source instructions, policies, schemas, handlers, or prompts.

## Learning Signals

Treat the following as possible learning signals:

- `command_failed`: a command, validation step, script, or local workflow failed in a way that may recur.
- `user_correction`: the user corrected behavior, assumptions, process, or output.
- `missing_capability`: a needed tool, skill, API, permission, or workflow capability is absent.
- `external_api_failed`: an external API, service, package registry, or remote dependency failed.
- `stale_knowledge`: existing knowledge, docs, examples, model assumptions, or API usage appear outdated.
- `better_method_found`: a safer, simpler, faster, or more reliable method was found.
- `safeharness_event`: a SafeHarness guard, policy decision, permission check, audit event, or blocked action produced reusable learning.
- `recurring_pattern`: the same issue, correction, or workaround appears repeatedly.

## Classification Before Recording

Before writing memory, classify the signal as one of:

- `noise`: too local, too vague, accidental, or not reusable. Do not record.
- `local_tip`: useful only for the current repository or current workflow. Record as a learning only if it will likely help later.
- `transferable_learning`: reusable across tasks or skills. Record as a learning.
- `missing_capability`: record as a feature request or capability gap.
- `safety_policy_candidate`: record as a policy candidate, not as an active policy change.
- `regression_case`: record as a regression test candidate.

## Routing

Use the target skill that owns the domain of the learning. If ownership is unclear, record under the most specific related skill and mention the uncertainty in the content.

- `transferable_learning` or useful `local_tip`: use `record_learning`.
- `command_failed` or `external_api_failed`: use `record_error`.
- `missing_capability`: use `record_feature_request`.
- `safety_policy_candidate` or reusable SafeHarness rule ideas: use `record_policy_candidate`.
- `regression_case`: use `record_regression_test`.
- `noise`: do nothing.

## Record Quality

Each memory entry should be concise and structured:

- Explain what happened.
- Include evidence or a short reproduction when useful.
- State the domain and source.
- Prefer actionable wording over broad conclusions.
- Redact sensitive values before writing.
- If the record implies a long-term behavior change, phrase it as a candidate recommendation until the user confirms it.

## Safety Boundaries

This skill can propose improvements, but it must not directly install permanent rules into skills, repository instructions, safety policies, tool schemas, tool handlers, or system prompts. Those changes must remain user-approved code or document changes.
