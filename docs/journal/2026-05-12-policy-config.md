# 2026-05-12 Policy Configuration

## Context

SafeHarness initially had policy YAML placeholders, while the real rules lived inside guard classes. That made behavior harder to inspect and harder to tune for different environments.

## Decision

Move the first layer of guard rules into `safety/policies/default_policy.yaml` and `safety/policies/high_security_policy.yaml`, then load them through `PolicyEngine`.

Because the project should stay dependency-light, the first implementation uses a tiny YAML parser in `safety/policy.py` that supports the repository's policy shape: nested mappings and lists of scalar strings/booleans. If the file is missing, malformed, or incomplete, the loaded policy is merged with built-in safe defaults.

## Current Behavior

- Default local mode gives the lead broad capabilities.
- High-risk tools such as `bash`, `background_run`, and `spawn_teammate` are approval-gated by policy.
- High security mode removes shell/background/team-spawn capabilities from the lead unless explicitly changed.
- Tool result injection phrases are configured under `prompt_injection.indirect`.
- Direct prompt injection phrases are configured under `prompt_injection.direct`.

## Follow-Up

- Add environment or CLI policy selection.
- Replace the lightweight parser with PyYAML only if the project accepts a dependency file.
- Add schema validation and clearer startup diagnostics for malformed policy files.
