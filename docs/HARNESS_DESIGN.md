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
