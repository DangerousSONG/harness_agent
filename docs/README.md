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

Every automatic memory write includes `Attribution Reason` and `Attribution Confidence`. The shared `classify_and_record_learning_signal` runtime path redacts secrets before classification/recording and blocks prompt-injection or approval-bypass text from becoming long-term learning. Automatic capture may write memory records only; it must not automatically edit `SKILL.md`, `AGENTS.md`, safety policy, tool schemas, tool handlers, or prompts.

For a deterministic local walkthrough, run `python .\scripts\debug_self_improvement.py`. It creates a test-only `markdown_writer` skill if needed, records three similar corrections, prints classification and attribution details, and checks that memory and promotion candidate files were written.

## Memory Promotion Candidates

Skill memory deduplication promotes recurring patterns into reviewable candidates. When a memory record reaches `Occurrence Count >= 3`, the manager marks it `recurring`, creates or reuses a `PromotionCandidate`, and writes it to `.skills_memory/PROMOTION_CANDIDATES.md`.

Promotion candidates include the source `record_id`, `target_skill`, a proposed change summary, target files, expected improvement, risk type, severity, created time, status, evaluation plan, and rollback plan. The `propose_memory_promotion(skill_name, record_id)` tool uses the same path for manual promotion requests.

Candidates are suggestions only. They do not edit README files, `.env.example`, skill instructions, safety policy, schemas, handlers, or prompts by themselves.

## Evolution Gate Evaluation

`evaluate_evolution_candidate(candidate_id)` runs the first-pass Evolution Gate over a promotion candidate. The gate loads the candidate from `.skills_memory/PROMOTION_CANDIDATES.md`, estimates `correctness_gain`, `safety_gain`, `regression_risk`, `overblocking_risk`, and `cost_increase`, then writes the decision to `.audit/evolution.jsonl`.

First-pass decisions are intentionally conservative: missing evaluation plans reject, guarded instruction or policy targets require human review after an evaluation plan exists, negative safety gain or high regression risk rejects, scores at or above the threshold return `approve`, and low scores reject. Evaluation never applies patches automatically.

When a candidate needs human review, the tool creates a pending item in `.reviews/`. Use `/reviews` to list pending items, `/review <id>` to inspect one, `/approve <id>` to mark it approved and generate `.reviews/patches/<id>.diff`, and `/reject <id>` to reject it. Approval is still preview-only; applying a patch requires a separate explicit confirmation step.

## Conflict Resolution

When documents disagree, use this order:

1. Code implementation + `CHANGELOG.md`
2. Design documents
3. Journal notes

Journal files are useful history, not the source of current truth.
