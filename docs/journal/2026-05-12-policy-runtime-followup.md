# 2026-05-12 Policy Runtime Follow-Up

## Why another pass

The first policy-config pass made guards configuration-driven, but there were still a few mismatches with the intended runtime behavior:

- policy selection was not yet driven by `SAFETY_POLICY`
- `PolicyEngine` still knew about paths instead of just loaded policy data
- `require_approval` was not yet normalized into a runtime block when no approval queue exists
- high security shell behavior needed an allowlist-based default block mode

## What changed

- Added `safety/policy_config.py` as the public entrypoint for policy selection.
- Moved runtime policy selection to `agent_harness.py`.
- Kept `PolicyEngine(policy=...)` focused on evaluation only.
- Converted `require_approval` into a blocked runtime outcome inside `harness/loop.py` so audit and user-visible behavior match.
- Tightened high security policy semantics around shell, file edits, and teammate restrictions.

## Remaining gaps

- There is still no interactive approval queue.
- Tool registry validation and memory guard are still future work.
- README still needs to be kept in sync whenever policy switching or mode semantics change.
