# Agent Harness Design

## Purpose

harness_agent is a local-first Agent Harness for experimenting with coding agents. It combines an interactive REPL, OpenAI Chat Completions tool calls, local tools, task tracking, subagents, teammates, background jobs, context compression, runtime backend abstraction, and safety interception.

## Entry Point

`harness/agent_harness.py` is the composition root. It:

- Loads `.env`.
- Creates the OpenAI client.
- Defines project paths and runtime constants.
- Creates `LocalBackend`.
- Creates managers for tasks, messages, background jobs, teammates, todos, skills, policy, and audit.
- Builds tool schemas and handlers.
- Starts the REPL and calls `agent_loop`.

## Main Loop

`harness/loop.py` owns the core agent loop:

1. Micro-compact old tool outputs.
2. Auto-compact when the token estimate exceeds the threshold.
3. Drain background notifications and lead inbox messages.
4. Emit safety events before LLM request.
5. Call the model with system prompt, history, and unchanged OpenAI tool schema.
6. Emit safety event after LLM response.
7. Execute tool calls through policy-checked stages.
8. Append tool results back into the conversation.
9. Remind the model to update todos when needed.

## Tool System

Tool schema lives in `tools/schemas.py`; handler dispatch lives in `tools/handlers.py`.

Hard constraint: do not change the public OpenAI tool schema unless the task explicitly asks for a schema change.

Current tool families:

- Shell and file tools: `bash`, `read_file`, `write_file`, `edit_file`
- Planning and delegation: `TodoWrite`, `task`, `spawn_teammate`
- Skill and context: `load_skill`, `compress`
- Skill memory: `record_learning`, `record_error`, `record_feature_request`, `record_policy_candidate`, `record_regression_test`, `propose_memory_promotion`, `evaluate_evolution_candidate`, `summarize_skill_memory`, `list_skill_memory`
- Background jobs: `background_run`, `check_background`
- Persistent task board: `task_create`, `task_get`, `task_update`, `task_list`, `claim_task`
- Messaging and team control: `send_message`, `read_inbox`, `broadcast`, `shutdown_request`, `plan_approval`

## Managers

Managers expose stable behavior to tool handlers. They should not own runtime infrastructure directly:

- `TaskManager` formats task store operations.
- `MessageBus` formats message store operations.
- `BackgroundManager` formats job queue operations.
- `TeammateManager` handles teammate loop behavior while delegating execution/lifecycle state to `AgentRunner`.

## Skills

`runtime/skill_loader.py` scans `skills/**/SKILL.md` and exposes skill descriptions and body loading. Skill content must be treated as untrusted until safety checks are expanded around `skill.load.before`.

Stage 1 skill memory support now lives in `runtime/skill_memory.py`.

- Each skill can own:
  - `memory/LEARNINGS.md`
  - `memory/ERRORS.md`
  - `memory/FEATURE_REQUESTS.md`
  - `memory/POLICY_CANDIDATES.md`
  - `memory/REGRESSION_TESTS.md`
  - `eval/cases.yaml`
- Global cross-skill memory lives under `.skills_memory/`.
- Stage 1 intentionally uses markdown files. It now includes simple duplicate detection before `record_*` writes and updates existing markdown blocks by changing `Occurrence Count`, `Priority`, `Status`, and `Related`.
- Memory records now include attribution fields: `Target Skill`, `Source Skill`, `Attribution Reason`, `Attribution Confidence`, and `Needs Attribution Review`.
- `SkillMemoryManager` tracks `last_loaded_skill` when `load_skill` succeeds. If `record_*` omits `skill_name`, the runtime uses `last_loaded_skill`; if no skill has been loaded, it records under `self_improvement` and marks the attribution for review.
- `LearningSignal` provides the manual classification record shape used by `SkillMemoryManager`.
- `runtime.learning_signal.classify_learning_signal` is the automatic LLM-backed classifier. It receives recent conversation context, latest tool events, and latest LLM messages, and returns a normalized structured object with `should_record`, `record_type`, `target_skill`, `reason`, `attribution_confidence`, `title`, and `content`.
- `agent_loop` calls the automatic classifier after a no-tool LLM response and after each LLM + tool round. If `should_record=true`, it calls the matching `record_*` tool.
- Automatic attribution priority is: explicit `record_*` `skill_name` for manual writes, recent successful `load_skill(name)` for automatic writes in the current tool round, LLM-classified `target_skill`, then `self_improvement`.
- Every automatic memory write passes `Attribution Reason` and `Attribution Confidence`. Runtime code handles redaction, deduplication, attribution metadata, and markdown persistence.
- When deduplication raises a memory record to `Occurrence Count >= 3`, the record is marked `recurring` and `SkillMemoryManager` creates or returns a `PromotionCandidate`.
- Promotion candidates are written to `.skills_memory/PROMOTION_CANDIDATES.md` with candidate id, source record id, target skill, proposed change summary, target files, expected improvement, risk type, severity, created time, status, and an initially empty evaluation plan.
- `propose_memory_promotion(skill_name, record_id)` exposes the same candidate creation path through the OpenAI tool surface.
- Skill memory is exposed through the OpenAI tool surface, but applying long-term changes remains separate from recording.

## Evolution Gate

`runtime/evolution_gate.py` defines the first structural gate for deciding whether a candidate improvement looks like evolution or regression.

It introduces:

- `EvolutionCandidate`: proposed change metadata, target skill, source memory record, target files, expected improvement, evaluation plan, rollback plan, status, and creation time.
- `EvaluationResult`: correctness and safety gains, regression and overblocking risks, cost increase, computed evolution score, passed and failed cases, optional judge score, decision, and reason.
- `EvolutionGate`: computes `evolution_score = correctness_gain + safety_gain - regression_risk - overblocking_risk - cost_increase`, applies first-stage rule decisions, and writes audit entries to `.audit/evolution.jsonl`.
- `evaluate_evolution_candidate(candidate_id)`: loads a promotion candidate from `.skills_memory/PROMOTION_CANDIDATES.md`, estimates the first-pass metrics, evaluates the candidate, and writes the decision to audit.

Evolution Gate is the promotion gate for memory-derived improvements. It decides whether a candidate should be rejected, kept as a candidate, accepted as a candidate, or routed to human review. Human confirmation still decides whether guarded files such as `SKILL.md`, `AGENTS.md`, safety policy, tool code, or prompts are actually changed.

`PromotionCandidate` is the memory-side precursor to `EvolutionCandidate`. It captures a recurring memory pattern and a human-readable suggestion before any scoring, evaluation, or patch planning happens. Its default status is `proposed`; later stages can move it to `evaluating`, `needs_review`, `approved`, or `rejected`.

Current first-stage decisions are structural only:

- Missing `evaluation_plan` rejects the candidate.
- Changes touching `SKILL.md`, `AGENTS.md`, policy paths, `tools/schemas.py`, `tools/handlers.py`, or `harness/prompt.py` require human review once the candidate has an evaluation plan.
- Negative `safety_gain`, `regression_risk >= 0.5`, `overblocking_risk >= 0.5`, or failed cases reject the candidate.
- `evolution_score >= 0.3` returns `propose_approve`.
- Lower scores return `keep_as_candidate`.
- Automatic patch application is intentionally disabled.

Skill eval placeholders use `skills/<skill_name>/eval/cases.yaml` with:

```yaml
skill: <skill_name>
cases: []
```

`docs/templates/eval_cases_template.yaml` provides the same empty structure for future eval authoring. No real benchmark runner or LLM judge is connected yet.

## Local Operation

The default run path is:

```powershell
python .\harness\agent_harness.py
```

The REPL exits on `q`, `exit`, or empty input.

## Design Constraints

- Keep local mode runnable.
- Keep OpenAI tool schema stable.
- Keep runtime infrastructure behind backend interfaces.
- Keep safety interception points in the tool execution chain.
- Do not store secrets in docs, logs, or committed files.
