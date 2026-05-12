# harness/subagent.py
# === SECTION: subagent (s04) ===
import json


def build_subagent_tools(agent_type: str = "Explore") -> list[dict]:
    tools = [
        {
            "type": "function",
            "function": {
                "name": "bash",
                "description": "Run command.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string"}
                    },
                    "required": ["command"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Read file.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"}
                    },
                    "required": ["path"]
                }
            }
        },
    ]

    if agent_type != "Explore":
        tools += [
            {
                "type": "function",
                "function": {
                    "name": "write_file",
                    "description": "Write file.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                            "content": {"type": "string"}
                        },
                        "required": ["path", "content"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "edit_file",
                    "description": "Edit file.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                            "old_text": {"type": "string"},
                            "new_text": {"type": "string"}
                        },
                        "required": ["path", "old_text", "new_text"]
                    }
                }
            },
        ]

    return tools


def run_subagent(
    *,
    prompt: str,
    agent_type: str,
    client,
    model: str,
    run_bash,
    run_read,
    run_write,
    run_edit,
    max_rounds: int = 30,
) -> str:
    sub_tools = build_subagent_tools(agent_type)

    sub_handlers = {
        "bash": lambda **kw: run_bash(kw["command"]),
        "read_file": lambda **kw: run_read(kw["path"]),
        "write_file": lambda **kw: run_write(kw["path"], kw["content"]),
        "edit_file": lambda **kw: run_edit(
            kw["path"],
            kw["old_text"],
            kw["new_text"]
        ),
    }

    sub_messages = [
        {
            "role": "system",
            "content": (
                "You are a focused subagent. "
                "Work independently on the given task. "
                "Use tools when needed. "
                "Return a concise summary of findings or changes."
            )
        },
        {
            "role": "user",
            "content": prompt
        }
    ]

    last_content = ""

    for _ in range(max_rounds):
        response = client.chat.completions.create(
            model=model,
            messages=sub_messages,
            tools=sub_tools,
            tool_choice="auto",
            max_tokens=8000,
        )

        msg = response.choices[0].message

        if not msg.tool_calls:
            if msg.content:
                last_content = msg.content
            break

        sub_messages.append({
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

        for tool_call in msg.tool_calls:
            tool_name = tool_call.function.name

            try:
                tool_args = json.loads(tool_call.function.arguments or "{}")
            except json.JSONDecodeError as e:
                output = f"Error: invalid tool arguments JSON: {e}"
            else:
                handler = sub_handlers.get(tool_name)

                try:
                    output = (
                        handler(**tool_args)
                        if handler
                        else f"Unknown tool: {tool_name}"
                    )
                except Exception as e:
                    output = f"Error: {e}"

            sub_messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": str(output)[:50000],
            })

    return last_content or "(no summary)"