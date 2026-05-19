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
- Skill memory: `record_learning`, `record_error`, `record_feature_request`, `record_policy_candidate`, `record_regression_test`, `classify_and_record_learning_signal`, `propose_memory_promotion`, `evaluate_evolution_candidate`, `summarize_skill_memory`, `list_skill_memory`
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
- `agent_loop` calls `classify_and_record_learning_signal` after a no-tool LLM response and after each LLM + tool round. If `should_record=true`, it calls the matching memory write method.
- Automatic attribution priority is: classifier `target_skill` when confidence is not low, explicit `skill_name` for tool-driven capture, recent successful `load_skill(name)`, then `self_improvement`. Low-confidence or missing classifier ownership is recorded under `self_improvement` with attribution review required.
- Every automatic memory write passes `Attribution Reason` and `Attribution Confidence`. Runtime code handles redaction, deduplication, attribution metadata, and markdown persistence.
- If `load_skill` is waiting for human approval and no successful load has occurred, automatic memory capture skips follow-up learning text rather than attributing it to that unloaded skill. Approval only marks the review approved; `/apply <review_id>` performs the reviewed skill load and updates `last_loaded_skill`. Repeating `load_skill` for the active skill returns `already loaded` without creating a duplicate review.
- When deduplication updates a memory record, `SkillMemoryManager` computes a lightweight Promotion Eligibility score. Memory records store occurrence count, transferability, impact, testability, user-correction strength, safety risk, attribution confidence, promotion score, promotion decision, reason, and eligible target.
- Promotion decisions are `promote`, `wait`, `reject`, and `policy_review`. Repeated low-risk transferable records can promote at three occurrences, strong reusable user corrections can promote at two occurrences when testable, and high-severity safety or policy candidates route to `policy_review` rather than `SKILL.md`. Low-confidence attribution waits for review, and prompt-injection, secret, approval-bypass, safety-disable, or ignore-system content is rejected for promotion.
- Promotion candidates are written to `.skills_memory/PROMOTION_CANDIDATES.md` with candidate id, source record id, target skill, proposed change summary, target files, expected improvement, risk type, severity, promotion score, promotion decision, reason, eligible target, created time, status, evaluation plan, and rollback plan.
- Older promotion candidates that lack promotion score, decision, or eligible target remain inspectable as `legacy`; they are not accepted by `/evolve-skill` until regenerated with eligibility metadata.
- `/evolve-skill` requires `promotion_decision=promote` and `eligible_target=skill_rule` before it creates regression or skill-promotion reviews. Only `learning`, `feature_request`, and recurring `error` source memories can enter the `SKILL.md` promotion path.
- `propose_memory_promotion(skill_name, record_id)` exposes the same candidate creation path through the OpenAI tool surface.
- Skill memory is exposed through the OpenAI tool surface, but applying long-term changes remains separate from recording.

## Web Chat Assistant

`web/server.py` exposes the local asset-governance API and a skill-aware Chat entry point at `POST /api/chat`. The older `/api/chat/send` path remains as a compatible alias.

Chat is not only a command console. It routes ordinary natural-language requests to the relevant workspace skill context, returns structured response types, and can read current workspace state including skills, memories, promotions, reviews, and versions. Deterministic routing currently covers writing/markdown requests, file editing advice, tool/error questions, and self-improvement workflows.

When Chat sees an explicit long-term preference or correction, it records a learning signal through `SkillMemoryManager.record_learning` and returns the resulting `LRN-*` id. Promotion candidates remain separate suggestions: Chat may surface a proposed promotion or evolution action, but it does not edit `SKILL.md`.

Conversational evolution operations stay behind existing APIs:

- Review generation is proposed or created through promotion evolution endpoints.
- Approve and apply actions are returned as confirmation-required actions.
- Apply responses include diff-preview data before the UI calls the review apply API.
- Rollback is routed through the version rollback API and creates a review only.

The Chat response shape includes `type`, `message`, `used_skill`, `memory_record_id`, `actions`, and `data`, allowing the UI to render normal answers, skill results, memory captures, proposed actions, tool results, approval-required states, and errors differently.

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
- `evolution_score >= 0.3` returns `approve`.
- Lower scores return `reject`.
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

The REPL exits on `q`, `exit`, or empty input. Local review commands are:

- `/reviews`: list pending human-review items.
- `/review <id>`: show review details.
- `/approve <id>`: mark a review approved and write a patch preview without applying any file change.
- `/apply <id>`: apply only supported approved review types. `load_skill` executes the reviewed skill load and updates active skill attribution; `skill.regression_case` writes reviewed eval cases; `skill.promotion` writes the reviewed `SKILL.md` rule only after matching positive and negative regression coverage exists.
- `/reject <id>`: reject a review.
- `/promotions`, `/promotion <id>`, `/propose-skill-patch <id>`, `/propose-regression-case <id>`, and `/evolve-skill <id>`: inspect promotion candidates and create pending reviews for skill-rule and regression-case changes. Review approval still only writes patch previews.
- `/skill-versions <skill>` and `/skill-version <skill> <version>`: inspect applied skill evolution records.
- `/rollback-skill <skill> <version>`: create a rollback review only; no file is modified by the command.

`/propose-skill-patch <id>` only creates `skill.promotion` reviews for concrete, source-memory-derived skill rules from `learning`, `feature_request`, or workflow-rule `error` records. `policy_candidate` records are refused with a policy-review message instead of being converted into `SKILL.md` rules. `/propose-regression-case <id>` uses the same concrete rule as `target_rule`, so regression cases do not inherit generic promotion-summary text.

`/evolve-skill <id>` is a non-mutating workflow guide. It checks whether regression coverage exists, creates or reuses the next required review, and prints the next `/review`, `/approve`, or `/apply` command. It never approves or applies a review.

`runtime/skill_evolution_registry.py` records successful `skill.promotion` applies after the reviewed patch has modified `skills/<skill>/SKILL.md`. Records live in `.skills_versions/<skill>/versions.jsonl`; each version directory stores the applied `SKILL.md` snapshot, the applied patch diff, and a minimal `eval_result.json`. Failed applies and missing regression coverage do not create version records.

## Design Constraints

- Keep local mode runnable.
- Keep OpenAI tool schema stable.
- Keep runtime infrastructure behind backend interfaces.
- Keep safety interception points in the tool execution chain.
- Do not store secrets in docs, logs, or committed files.
