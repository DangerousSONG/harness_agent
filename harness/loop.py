# harness/loop.py

import json
import uuid

from runtime.learning_signal import classify_and_record_learning_signal
from safety.decisions import BLOCK, REQUIRE_APPROVAL, SANITIZE
from safety.events import RuntimeEvent

MEMORY_RECORD_TOOLS = {
    "record_learning",
    "record_error",
    "record_feature_request",
    "record_policy_candidate",
    "record_regression_test",
    "propose_memory_promotion",
    "evaluate_evolution_candidate",
    "classify_and_record_learning_signal",
    "classify_learning_signal",
}

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


def _evaluate(policy_engine, audit_logger, event: RuntimeEvent, review_store=None):
    if not policy_engine:
        return None

    decision = policy_engine.evaluate(event)
    if decision.action == REQUIRE_APPROVAL:
        if review_store:
            try:
                _attach_review(
                    decision,
                    _create_review_for_decision(review_store, event, decision),
                )
            except Exception as e:
                decision = type(decision).block(
                    decision.risk_type,
                    decision.severity,
                    f"{decision.reason} Approval review creation failed: {e}",
                )
        else:
            decision = type(decision).block(
                decision.risk_type,
                decision.severity,
                f"{decision.reason} Approval queue is not configured.",
            )
    if audit_logger:
        audit_logger.log(event, decision)
    return decision


def _blocked_message(decision) -> str:
    return f"Blocked by SafeHarness policy: {decision.reason}"


def _approval_message(decision) -> str:
    review_id = getattr(decision, "review_id", "")
    review_item = getattr(decision, "review_item", {}) or {}
    tool_name = review_item.get("tool_name", "")
    target_files = ", ".join(review_item.get("target_files") or [])
    severity = review_item.get("severity") or decision.severity
    reason = review_item.get("reason") or decision.reason
    if review_id:
        return "\n".join(
            [
                "已暂停执行该工具调用，等待人工审批。目标文件未被修改。",
                "",
                f"review_id={review_id}",
                f"tool_name: {tool_name or '(unknown)'}",
                f"target_files: {target_files or '(none)'}",
                f"severity: {severity}",
                f"reason: {reason}"
                + (
                    f"\n\nload_skill is waiting for human approval. Run /approve {review_id} before treating this skill as loaded."
                    if tool_name == "load_skill"
                    else ""
                ),
                "",
                "下一步可输入：",
                f"/review {review_id}",
                f"/approve {review_id}",
                f"/reject {review_id}",
            ]
        )
    return f"需要人工审批；该操作尚未执行。原因：{decision.reason}"


def _target_files_for_tool(tool_name: str | None, args: dict) -> list[str]:
    if tool_name in {"write_file", "edit_file", "read_file"} and args.get("path"):
        return [str(args["path"])]
    return []


def _proposed_change_for_tool(tool_name: str | None, args: dict) -> str:
    if tool_name == "write_file":
        return f"Write {len(str(args.get('content', '')))} bytes to {args.get('path', '')}."
    if tool_name == "edit_file":
        return f"Replace one occurrence in {args.get('path', '')}."
    if tool_name == "bash":
        return f"Run shell command: {args.get('command', '')}"
    if tool_name:
        return f"Run tool {tool_name} with approval-gated arguments."
    return "Approval-gated runtime action."


def _create_review_for_decision(review_store, event: RuntimeEvent, decision) -> dict:
    if not review_store:
        return {}
    args = event.payload.get("arguments", {})
    if not isinstance(args, dict):
        args = {}
    target = event.target or ""
    item = review_store.create_review(
        type=event.event_type,
        source=event.source,
        target_skill=str(args.get("skill_name") or args.get("name") or ""),
        candidate_id=str(args.get("candidate_id") or ""),
        target_files=_target_files_for_tool(target, args),
        reason=decision.reason,
        risk_type=decision.risk_type,
        severity=decision.severity,
        proposed_change=_proposed_change_for_tool(target, args),
        evaluation_plan="Human reviews the request and smallest useful validation before any apply step.",
        rollback_plan="Do not apply automatically. If later applied and unsafe, revert only the reviewed change.",
        tool_name=target,
        tool_arguments=args,
        event_type=event.event_type,
        metadata={
            "event": event.to_dict(),
            "tool_name": target,
            "tool_arguments": args,
        },
    )
    return item


def _attach_review(decision, item: dict):
    setattr(decision, "review_id", item.get("review_id", ""))
    setattr(decision, "review_item", item)
    return decision


def _recent_context(messages: list, limit: int = 6) -> list[dict]:
    recent = []
    for message in messages[-limit:]:
        item = {
            "role": message.get("role"),
            "content": str(message.get("content", ""))[:1200],
        }
        if message.get("name"):
            item["name"] = message.get("name")
        recent.append(item)
    return recent


def _auto_record_learning_signal(
    *,
    client,
    model: str,
    messages: list,
    tool_handlers: dict,
    latest_tool_events: list[dict],
    latest_llm_messages: list[dict],
) -> None:
    if not latest_tool_events and not latest_llm_messages:
        return

    try:
        result = classify_and_record_learning_signal(
            client=client,
            model=model,
            skill_memory=tool_handlers.get("__skill_memory__"),
            raw_content=json.dumps(
                {
                    "latest_tool_events": latest_tool_events,
                    "latest_llm_messages": latest_llm_messages,
                },
                ensure_ascii=False,
            ),
            conversation_context=_recent_context(messages),
            latest_tool_events=latest_tool_events,
            latest_llm_messages=latest_llm_messages,
        )
    except Exception as e:
        print(f"> auto_memory skipped: {e}")
        return
    if not result.get("classification", {}).get("should_record"):
        record_result = str(result.get("record_result", ""))
        if record_result.startswith(
            (
                "approval_required event skipped",
                "skipped post-approval assistant message",
            )
        ):
            print(f"> auto_memory: {record_result[:200]}")
        return

    print("> auto_memory:")
    print(str(result.get("record_result", ""))[:200])


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
    review_store=None,
    run_id: str | None = None,
    actor: str = "lead",
    allowed_capabilities: set[str] | None = None,
):
    rounds_without_todo = 0
    run_id = run_id or str(uuid.uuid4())
    allowed_capabilities = allowed_capabilities or set()

    while True:
        latest_tool_events = []
        latest_llm_messages = []
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
            decision = _evaluate(policy_engine, audit_logger, event, review_store)
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
        decision = _evaluate(policy_engine, audit_logger, request_event, review_store)
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
        _evaluate(policy_engine, audit_logger, response_event, review_store)
        latest_llm_messages.append({
            "content": msg.content or "",
            "tool_calls": [
                tool_call.function.name
                for tool_call in (msg.tool_calls or [])
            ],
        })

        if not msg.tool_calls:
            if msg.content:
                print(msg.content)
                messages.append({
                    "role": "assistant",
                    "content": msg.content,
                })
            _auto_record_learning_signal(
                client=client,
                model=model,
                messages=messages,
                tool_handlers=tool_handlers,
                latest_tool_events=latest_tool_events,
                latest_llm_messages=latest_llm_messages,
            )
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

        tool_calls = msg.tool_calls or []
        for tool_index, tool_call in enumerate(tool_calls):
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
                decision = _evaluate(policy_engine, audit_logger, malformed_event, review_store)
                if decision and decision.action in {BLOCK, REQUIRE_APPROVAL}:
                    output = (
                        _blocked_message(decision)
                        if decision.action == BLOCK
                        else _approval_message(decision)
                    )
                latest_tool_events.append({
                    "tool": tool_name,
                    "status": "malformed_arguments",
                    "error": str(e),
                    "result": output,
                })
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
            decision = _evaluate(policy_engine, audit_logger, call_event, review_store)
            if decision and decision.action in {BLOCK, REQUIRE_APPROVAL}:
                output = (
                    _blocked_message(decision)
                    if decision.action == BLOCK
                    else _approval_message(decision)
                )
                if tool_name not in MEMORY_RECORD_TOOLS:
                    latest_tool_events.append(
                        _tool_event_for_policy_stop(tool_name, decision, output)
                    )
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": output,
                })
                if decision.action == REQUIRE_APPROVAL:
                    _append_skipped_tool_results(
                        messages,
                        tool_calls[tool_index + 1 :],
                        "Skipped because another tool call is waiting for human approval.",
                    )
                    print(output)
                    messages.append({"role": "assistant", "content": output})
                    return
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
            decision = _evaluate(policy_engine, audit_logger, execution_event, review_store)
            if decision and decision.action in {BLOCK, REQUIRE_APPROVAL}:
                output = (
                    _blocked_message(decision)
                    if decision.action == BLOCK
                    else _approval_message(decision)
                )
                if tool_name not in MEMORY_RECORD_TOOLS:
                    latest_tool_events.append(
                        _tool_event_for_policy_stop(tool_name, decision, output)
                    )
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": output,
                })
                if decision.action == REQUIRE_APPROVAL:
                    _append_skipped_tool_results(
                        messages,
                        tool_calls[tool_index + 1 :],
                        "Skipped because another tool call is waiting for human approval.",
                    )
                    print(output)
                    messages.append({"role": "assistant", "content": output})
                    return
                continue
            if decision and decision.action == SANITIZE:
                tool_args = execution_event.payload.get("arguments", tool_args)

            try:
                output = handler(**tool_args) if handler else f"Unknown tool: {tool_name}"
            except Exception as e:
                output = f"Error: {e}"
            if tool_name not in MEMORY_RECORD_TOOLS:
                latest_tool_events.append({
                    "tool": tool_name,
                    "arguments": tool_args,
                    "status": "error" if str(output).startswith("Error:") else "ok",
                    "result": str(output)[:2000],
                })

            after_event = _event(
                run_id=run_id,
                event_type="tool.execution.after",
                actor=actor,
                source="tool",
                target=tool_name,
                payload={"result": str(output)},
                parent_event_id=execution_event.event_id,
            )
            _evaluate(policy_engine, audit_logger, after_event, review_store)

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
            decision = _evaluate(policy_engine, audit_logger, result_event, review_store)
            if decision and decision.action in {BLOCK, REQUIRE_APPROVAL}:
                output = (
                    _blocked_message(decision)
                    if decision.action == BLOCK
                    else _approval_message(decision)
                )
                if tool_name not in MEMORY_RECORD_TOOLS:
                    event = _tool_event_for_policy_stop(tool_name, decision, output)
                    if decision.action == BLOCK:
                        event["status"] = "blocked_result"
                    latest_tool_events.append(event)
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

        _auto_record_learning_signal(
            client=client,
            model=model,
            messages=messages,
            tool_handlers=tool_handlers,
            latest_tool_events=latest_tool_events,
            latest_llm_messages=latest_llm_messages,
        )

        if manual_compress:
            print("[manual compact]")
            messages[:] = auto_compact(
                messages=messages,
                client=client,
                model=model,
                transcript_dir=transcript_dir,
            )
            return


def _tool_event_for_policy_stop(tool_name: str, decision, output: str) -> dict:
    if decision.action == REQUIRE_APPROVAL:
        review_id = getattr(decision, "review_id", "")
        return {
            "tool": tool_name,
            "status": "approval_required",
            "action": REQUIRE_APPROVAL,
            "review_id": review_id,
            "review_created": bool(review_id),
            "reason": decision.reason,
            "result": output,
        }
    return {
        "tool": tool_name,
        "status": "blocked",
        "action": BLOCK,
        "reason": decision.reason,
        "result": output,
    }


def _append_skipped_tool_results(messages: list, tool_calls: list, reason: str) -> None:
    for tool_call in tool_calls:
        messages.append({
            "role": "tool",
            "tool_call_id": tool_call.id,
            "content": reason,
        })
