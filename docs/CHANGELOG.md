# Changelog

This file records meaningful project iterations. When judging current state, read this before older design notes.

## 2026-05-15

### Review Queue Safety Follow-up

- Skipped `approval_required` / `require_approval` / `review_created` tool events in automatic error memory capture so approval gates are not recorded as ordinary `edit_file` failures.
- Added review metadata for `edit_file` approvals with empty `old_text`, marking them as requiring a better anchor.
- Changed `edit_file` patch previews with empty `old_text` to emit an explicit invalid-anchor warning instead of a unified diff that could look safely applicable.
- Kept `/approve` behavior preview-only; approved reviews still do not modify target files.
- Made approval-required tool stops print a structured waiting-for-approval message with the review id, guarded tool, target files, severity, reason, and `/review` / `/approve` / `/reject` commands.
- Skipped automatic memory capture for assistant explanations that only restate a pending approval requirement, preventing approval flow from becoming `tool_usage` errors, `tool_modification` feature requests, or policy candidates.

## 2026-05-14

### Human Review Queue

- Added a local `ReviewQueue` backed by `.reviews/REV-*.json`.
- Changed SafeHarness `require_approval` handling to create a pending review item and return its `review_id` instead of converting the decision to a block.
- Added REPL commands `/reviews`, `/review <id>`, `/approve <id>`, and `/reject <id>`.
- Approval marks a review as `approved` and writes a patch preview; it does not apply changes to target files.
- `evaluate_evolution_candidate` now creates a pending review item when the Evolution Gate returns `needs_human_review`.
- Expanded approval-gated paths so `SKILL.md`, `AGENTS.md`, `safety/**`, `tools/**`, and `harness/prompt.py` changes require human review.

### Self Improvement Learning Loop

- Added a shared `classify_and_record_learning_signal` runtime path for post-turn learning capture and tool-driven capture.
- Updated automatic attribution to prefer the classifier's target skill, use low confidence as an attribution-review signal, and avoid routing everything to the last loaded skill.
- Added runtime redaction and prompt-injection/memory-poisoning blocking before any automatic memory write.
- Promotion candidates now include both `Evaluation Plan` and `Rollback Plan` when generated.
- Tightened Evolution Gate decisions to advice-only `approve`, `reject`, or `needs_human_review`; no patch application is performed.
- Added `scripts/debug_self_improvement.py` for a deterministic local walkthrough of correction classification, skill attribution, memory writes, duplicate merging, and promotion candidate creation.
- Added minimal unittest coverage for redaction, target-skill routing, low-confidence review, duplicate occurrence increments, promotion creation, sensitive-target review, and prompt-injection filtering.

### Evolution Gate Evaluation

- Extended `EvolutionGate` to load `PromotionCandidate` records from `.skills_memory/PROMOTION_CANDIDATES.md` by `candidate_id`.
- Added first-pass metric estimation for `correctness_gain`, `safety_gain`, `regression_risk`, `overblocking_risk`, and `cost_increase`.
- Updated gate decisions to reject missing evaluation plans, route guarded instruction/policy candidates to human review, reject negative safety or high regression risk, propose approval when score meets threshold, and otherwise keep candidates.
- Added `evaluate_evolution_candidate(candidate_id)` and wired it to `.audit/evolution.jsonl`; the tool only evaluates and never applies patches.
- Added SafeHarness capability entries for `evaluate_evolution_candidate`.

### Memory Promotion Candidates

- Added `PromotionCandidate` as the memory-side candidate shape for recurring patterns.
- Repeated memory records now create or reuse a promotion candidate when deduplication reaches `Occurrence Count >= 3`.
- Promotion candidates are written to `.skills_memory/PROMOTION_CANDIDATES.md` with structured fields, including source record id, target skill, proposed change summary, target files, expected improvement, risk type, severity, status, and evaluation plan.
- Added the `propose_memory_promotion` tool for manual candidate creation from `skill_name` and `record_id`.
- Added SafeHarness capability entries for `propose_memory_promotion`.

### Automatic Learning Signal Capture

- Added `runtime/learning_signal.py` with an LLM-backed `classify_learning_signal` helper that accepts conversation context, latest tool events, and latest LLM messages, then normalizes the result into a structured classification object.
- Wired the agent loop to call the classifier after each LLM response and after each tool round, then automatically call the matching `record_*` memory tool when `should_record=true`.
- Enforced automatic attribution priority: low confidence routes to `self_improvement` review; otherwise classifier `target_skill`, explicit `skill_name`, recent `load_skill(name)`, then `self_improvement`.
- Automatic memory writes now always pass `Attribution Reason` and `Attribution Confidence`.
- Kept automatic capture limited to memory writes; it does not modify `SKILL.md`, `AGENTS.md`, safety policy, tool schemas, tool handlers, or prompts.

### Skill Memory Signal Attribution

- Added `LearningSignal` and `classify_learning_signal` as the first learning signal classification entry point.
- Added active skill attribution through `last_loaded_skill` after successful `load_skill`.
- Made `record_*` tools able to omit `skill_name`; missing attribution falls back to the active skill or `self_improvement` with review required.
- Added attribution metadata fields to new memory records: `Target Skill`, `Source Skill`, `Attribution Reason`, `Attribution Confidence`, and `Needs Attribution Review`.
- Documented that the LLM judges learning signal ownership, runtime code handles redaction/deduplication/persistence, Evolution Gate handles promotion decisions, and humans confirm guarded long-term changes.

## 2026-05-13

### README 中文统一

- 将顶层 `README.md` 中新增的英文说明段落统一改为中文。
- 保留必要的技术名词、路径、命令和环境变量名称。
- 将 `self_improvement` 说明从 README 开头移至 Skill 相关章节，并改为更正式的项目文档表述。

### self_improvement Benchmark Skeleton

- Added static eval cases for `self_improvement` under `skills/self_improvement/eval/cases.yaml`.
- Added `skills/self_improvement/eval/README.md` documenting benchmark scope and case shape.
- Added `docs/templates/skill_eval_cases_template.yaml` for future skill eval authoring.
- Covered trigger detection, noise filtering, deduplication, memory poisoning, secret redaction, indirect prompt injection, and Evolution Gate decisions.
- No runner, benchmark framework, LLM judge, business logic, or new dependency was added.

### Evolution Gate Structure

- Added `runtime/evolution_gate.py` with `EvolutionCandidate`, `EvaluationResult`, and `EvolutionGate`.
- Implemented first-stage evolution scoring, reject/keep/review decisions, and `.audit/evolution.jsonl` audit writes.
- Added `docs/templates/eval_cases_template.yaml`.
- Updated new skill eval placeholders to include `skill: <skill_name>` with empty `cases`.
- No benchmark runner, LLM judge, or automatic patch application is connected in this stage.
- Validation: `python -m compileall harness runtime tools safety scripts` and `"q" | python .\harness\agent_harness.py`.

### Skill Memory Deduplication

- Added simple markdown-based duplicate detection before `record_*` writes.
- Similar records now update the existing block instead of appending duplicates.
- Duplicate updates increment `Occurrence Count`, raise `Priority` from `P3` to `P2` to `P1`, add `Related`, and mark third occurrences as `recurring`.
- Third occurrences return a promotion-candidate hint for recurring patterns.
- Validation: `python -m compileall harness runtime tools safety scripts` and `"q" | python .\harness\agent_harness.py`.

### self_improvement Skill

- Added `skills/self_improvement/SKILL.md` as a cross-skill learning manager.
- Documented clear learning signals, pre-write classification, memory routing, secret redaction, and long-term rule confirmation requirements.
- Updated README with the new skill purpose and safety boundaries.

### Skill Memory Tool Integration

- Added OpenAI tools for skill memory writes and reads:
  - `record_learning`
  - `record_error`
  - `record_feature_request`
  - `record_policy_candidate`
  - `record_regression_test`
  - `summarize_skill_memory`
  - `list_skill_memory`
- Wired `SkillMemoryManager` into `tools/schemas.py`, `tools/handlers.py`, and `harness/agent_harness.py`.
- Added SafeHarness policy and capability entries so the new memory tools are not treated as unknown tools.
- Improved `summarize_memory` to include recent record titles per memory category.

### Validation

- `python -m compileall harness runtime tools safety scripts`
- `"q" | python .\harness\agent_harness.py`

## 2026-05-12

### Skill Memory Phase 1

- Added `runtime/skill_memory.py` with `SkillMemoryManager`.
- Added skill-scoped markdown memory structure under `skills/<skill_name>/memory/`.
- Added placeholder skill eval structure under `skills/<skill_name>/eval/cases.yaml`.
- Added global markdown memory directory `.skills_memory/`.
- Added Stage 1 APIs:
  - `ensure_memory`
  - `record_learning`
  - `record_error`
  - `record_feature_request`
  - `record_policy_candidate`
  - `record_regression_test`
  - `list_memory`
  - `summarize_memory`
  - placeholder `find_similar_records`
- Added secret redaction before markdown writes.

### Skill Memory Validation

- `python -m compileall harness runtime tools safety scripts`
- `"q" | python .\harness\agent_harness.py`

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
