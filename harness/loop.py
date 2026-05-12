# harness/loop.py

import json
import uuid

from safety.decisions import BLOCK, REQUIRE_APPROVAL, SANITIZE
from safety.events import RuntimeEvent


def _event(
    *,
    run_id: str,
    event_type: str,
    actor: str,
    source: str,
    target: str | None = None,
    payload: dict | None = None,
    metadata: dict | None = None,
    parent_event_id: str | None = None,
) -> RuntimeEvent:
    return RuntimeEvent(
        run_id=run_id,
        parent_event_id=parent_event_id,
        event_type=event_type,
        actor=actor,
        source=source,
        target=target,
        payload=payload or {},
        metadata=metadata or {},
    )


def _evaluate(policy_engine, audit_logger, event: RuntimeEvent):
    if not policy_engine:
        return None

    decision = policy_engine.evaluate(event)
    if decision.action == REQUIRE_APPROVAL:
        decision = type(decision).block(
            decision.risk_type,
            decision.severity,
            f"{decision.reason} Approval queue is not implemented yet.",
        )
    if audit_logger:
        audit_logger.log(event, decision)
    return decision


def _blocked_message(decision) -> str:
    return f"Blocked by SafeHarness policy: {decision.reason}"


def _approval_message(decision) -> str:
    return f"Blocked by SafeHarness policy: {decision.reason}"


def agent_loop(
    *,
    messages: list,
    client,
    model: str,
    system: str,
    tools: list,
    tool_handlers: dict,
    todo,
    bg,
    bus,
    token_threshold: int,
    transcript_dir,
    estimate_tokens,
    microcompact,
    auto_compact,
    policy_engine=None,
    audit_logger=None,
    run_id: str | None = None,
    actor: str = "lead",
    allowed_capabilities: set[str] | None = None,
):
    rounds_without_todo = 0
    run_id = run_id or str(uuid.uuid4())
    allowed_capabilities = allowed_capabilities or set()

    while True:
        microcompact(messages)

        if estimate_tokens(messages) > token_threshold:
            print("[auto-compact triggered]")
            messages[:] = auto_compact(
                messages=messages,
                client=client,
                model=model,
                transcript_dir=transcript_dir,
            )

        notifs = bg.drain()
        if notifs:
            txt = "\n".join(
                f"[bg:{n['task_id']}] {n['status']}: {n['result']}"
                for n in notifs
            )
            messages.append({
                "role": "user",
                "content": f"<background-results>\n{txt}\n</background-results>",
            })

        inbox = bus.read_inbox("lead")
        if inbox:
            messages.append({
                "role": "user",
                "content": f"<inbox>{json.dumps(inbox, indent=2, ensure_ascii=False)}</inbox>",
            })

        last_user = next(
            (m for m in reversed(messages) if m.get("role") == "user"),
            None,
        )
        if last_user:
            event = _event(
                run_id=run_id,
                event_type="user_input.received",
                actor="user",
                source="user_input",
                payload={"content": last_user.get("content", "")},
            )
            decision = _evaluate(policy_engine, audit_logger, event)
            if decision and decision.action in {BLOCK, REQUIRE_APPROVAL}:
                output = (
                    _blocked_message(decision)
                    if decision.action == BLOCK
                    else _approval_message(decision)
                )
                print(output)
                messages.append({"role": "assistant", "content": output})
                return

        request_event = _event(
            run_id=run_id,
            event_type="llm.request.before",
            actor=actor,
            source="runtime",
            target=model,
            payload={"message_count": len(messages)},
            metadata={"allowed_capabilities": sorted(allowed_capabilities)},
        )
        decision = _evaluate(policy_engine, audit_logger, request_event)
        if decision and decision.action in {BLOCK, REQUIRE_APPROVAL}:
            output = (
                _blocked_message(decision)
                if decision.action == BLOCK
                else _approval_message(decision)
            )
            print(output)
            messages.append({"role": "assistant", "content": output})
            return

        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                *messages,
            ],
            tools=tools,
            tool_choice="auto",
            max_tokens=8000,
        )

        msg = response.choices[0].message
        response_event = _event(
            run_id=run_id,
            event_type="llm.response.after",
            actor=actor,
            source="llm",
            target=model,
            payload={
                "has_tool_calls": bool(msg.tool_calls),
                "content": msg.content or "",
                "tool_names": [
                    tool_call.function.name
                    for tool_call in (msg.tool_calls or [])
                ],
            },
            parent_event_id=request_event.event_id,
        )
        _evaluate(policy_engine, audit_logger, response_event)

        if not msg.tool_calls:
            if msg.content:
                print(msg.content)
                messages.append({
                    "role": "assistant",
                    "content": msg.content,
                })
            return

        messages.append({
            "role": "assistant",
            "content": msg.content or "",
            "tool_calls": [
                {
                    "id": tool_call.id,
                    "type": "function",
                    "function": {
                        "name": tool_call.function.name,
                        "arguments": tool_call.function.arguments,
                    },
                }
                for tool_call in msg.tool_calls
            ],
        })

        used_todo = False
        manual_compress = False

        for tool_call in msg.tool_calls:
            tool_name = tool_call.function.name

            try:
                tool_args = json.loads(tool_call.function.arguments or "{}")
            except json.JSONDecodeError as e:
                output = f"Error: invalid tool arguments JSON: {e}"
                malformed_event = _event(
                    run_id=run_id,
                    event_type="tool.call.before",
                    actor=actor,
                    source="llm",
                    target=tool_name,
                    payload={
                        "malformed_arguments": True,
                        "raw_arguments": tool_call.function.arguments or "",
                        "error": str(e),
                    },
                    metadata={"allowed_capabilities": sorted(allowed_capabilities)},
                    parent_event_id=response_event.event_id,
                )
                decision = _evaluate(policy_engine, audit_logger, malformed_event)
                if decision and decision.action in {BLOCK, REQUIRE_APPROVAL}:
                    output = (
                        _blocked_message(decision)
                        if decision.action == BLOCK
                        else _approval_message(decision)
                    )
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": output,
                })
                continue

            call_event = _event(
                run_id=run_id,
                event_type="tool.call.before",
                actor=actor,
                source="llm",
                target=tool_name,
                payload={"arguments": tool_args},
                metadata={"allowed_capabilities": sorted(allowed_capabilities)},
                parent_event_id=response_event.event_id,
            )
            decision = _evaluate(policy_engine, audit_logger, call_event)
            if decision and decision.action in {BLOCK, REQUIRE_APPROVAL}:
                output = (
                    _blocked_message(decision)
                    if decision.action == BLOCK
                    else _approval_message(decision)
                )
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": output,
                })
                continue
            if decision and decision.action == SANITIZE:
                tool_args = call_event.payload.get("arguments", tool_args)

            if tool_name == "compress":
                manual_compress = True

            handler = tool_handlers.get(tool_name)

            execution_event = _event(
                run_id=run_id,
                event_type="tool.execution.before",
                actor=actor,
                source="runtime",
                target=tool_name,
                payload={"arguments": tool_args},
                metadata={"allowed_capabilities": sorted(allowed_capabilities)},
                parent_event_id=call_event.event_id,
            )
            decision = _evaluate(policy_engine, audit_logger, execution_event)
            if decision and decision.action in {BLOCK, REQUIRE_APPROVAL}:
                output = (
                    _blocked_message(decision)
                    if decision.action == BLOCK
                    else _approval_message(decision)
                )
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": output,
                })
                continue
            if decision and decision.action == SANITIZE:
                tool_args = execution_event.payload.get("arguments", tool_args)

            try:
                output = handler(**tool_args) if handler else f"Unknown tool: {tool_name}"
            except Exception as e:
                output = f"Error: {e}"

            after_event = _event(
                run_id=run_id,
                event_type="tool.execution.after",
                actor=actor,
                source="tool",
                target=tool_name,
                payload={"result": str(output)},
                parent_event_id=execution_event.event_id,
            )
            _evaluate(policy_engine, audit_logger, after_event)

            print(f"> {tool_name}:")
            print(str(output)[:200])

            result_event = _event(
                run_id=run_id,
                event_type="tool.result.before_model",
                actor=actor,
                source="runtime",
                target=tool_name,
                payload={"result": str(output)},
                parent_event_id=after_event.event_id,
            )
            decision = _evaluate(policy_engine, audit_logger, result_event)
            if decision and decision.action in {BLOCK, REQUIRE_APPROVAL}:
                output = (
                    _blocked_message(decision)
                    if decision.action == BLOCK
                    else _approval_message(decision)
                )
            elif decision and decision.action == SANITIZE:
                output = result_event.payload.get("result", output)

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": str(output),
            })

            if tool_name == "TodoWrite":
                used_todo = True

        rounds_without_todo = 0 if used_todo else rounds_without_todo + 1

        if todo.has_open_items() and rounds_without_todo >= 3:
            messages.append({
                "role": "user",
                "content": "<reminder>Update your todos.</reminder>",
            })

        if manual_compress:
            print("[manual compact]")
            messages[:] = auto_compact(
                messages=messages,
                client=client,
                model=model,
                transcript_dir=transcript_dir,
            )
            return
