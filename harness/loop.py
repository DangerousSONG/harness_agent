# harness/loop.py

import json


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
):
    rounds_without_todo = 0

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
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": output,
                })
                continue

            if tool_name == "compress":
                manual_compress = True

            handler = tool_handlers.get(tool_name)

            try:
                output = handler(**tool_args) if handler else f"Unknown tool: {tool_name}"
            except Exception as e:
                output = f"Error: {e}"

            print(f"> {tool_name}:")
            print(str(output)[:200])

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