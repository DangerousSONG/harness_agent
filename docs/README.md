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

## Automatic Learning Capture

The harness can automatically capture durable learning signals for skill memory. After each LLM response and after each tool round, `runtime.learning_signal.classify_learning_signal` receives recent conversation context, latest tool events, and latest LLM messages. The helper asks the LLM to return a structured classification with `should_record`, `record_type`, `target_skill`, `reason`, `attribution_confidence`, `title`, and `content`.

When `should_record=true`, the loop calls the matching `record_*` memory tool. Attribution is resolved in this order:

1. Explicit `skill_name` on a manual `record_*` call.
2. The most recent successful `load_skill(name)` in the current tool round.
3. The LLM-classified `target_skill`.
4. `self_improvement` when no owner can be determined.

Every automatic memory write includes `Attribution Reason` and `Attribution Confidence`. Automatic capture may write memory records only; it must not automatically edit `SKILL.md`, `AGENTS.md`, safety policy, tool schemas, tool handlers, or prompts.

## Memory Promotion Candidates

Skill memory deduplication promotes recurring patterns into reviewable candidates. When a memory record reaches `Occurrence Count >= 3`, the manager marks it `recurring`, creates or reuses a `PromotionCandidate`, and writes it to `.skills_memory/PROMOTION_CANDIDATES.md`.

Promotion candidates include the source `record_id`, `target_skill`, a proposed change summary, target files, expected improvement, risk type, severity, created time, status, and an initially empty evaluation plan. The `propose_memory_promotion(skill_name, record_id)` tool uses the same path for manual promotion requests.

Candidates are suggestions only. They do not edit README files, `.env.example`, skill instructions, safety policy, schemas, handlers, or prompts by themselves.

## Evolution Gate Evaluation

`evaluate_evolution_candidate(candidate_id)` runs the first-pass Evolution Gate over a promotion candidate. The gate loads the candidate from `.skills_memory/PROMOTION_CANDIDATES.md`, estimates `correctness_gain`, `safety_gain`, `regression_risk`, `overblocking_risk`, and `cost_increase`, then writes the decision to `.audit/evolution.jsonl`.

First-pass decisions are intentionally conservative: missing evaluation plans reject, guarded instruction or policy targets require human review after an evaluation plan exists, negative safety gain or high regression risk rejects, scores at or above the threshold return `propose_approve`, and everything else stays `keep_as_candidate`. Evaluation never applies patches automatically.

## Conflict Resolution

When documents disagree, use this order:

1. Code implementation + `CHANGELOG.md`
2. Design documents
3. Journal notes

Journal files are useful history, not the source of current truth.
