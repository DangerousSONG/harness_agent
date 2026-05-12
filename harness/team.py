# harness/team.py

import json
import threading
import time
from pathlib import Path


def build_team_tools() -> list[dict]:
    return [
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
        {
            "type": "function",
            "function": {
                "name": "send_message",
                "description": "Send message.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "to": {"type": "string"},
                        "content": {"type": "string"}
                    },
                    "required": ["to", "content"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "idle",
                "description": "Signal no more work.",
                "parameters": {
                    "type": "object",
                    "properties": {}
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "claim_task",
                "description": "Claim task by ID.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "integer"}
                    },
                    "required": ["task_id"]
                }
            }
        },
    ]


class TeammateManager:
    def __init__(
        self,
        *,
        bus,
        task_mgr,
        team_dir: Path,
        tasks_dir: Path,
        workdir: Path,
        client,
        model: str,
        run_bash,
        run_read,
        run_write,
        run_edit,
        idle_timeout: int,
        poll_interval: int,
    ):
        self.bus = bus
        self.task_mgr = task_mgr
        self.team_dir = team_dir
        self.tasks_dir = tasks_dir
        self.workdir = workdir
        self.client = client
        self.model = model
        self.run_bash = run_bash
        self.run_read = run_read
        self.run_write = run_write
        self.run_edit = run_edit
        self.idle_timeout = idle_timeout
        self.poll_interval = poll_interval

        self.team_dir.mkdir(parents=True, exist_ok=True)

        self.config_path = self.team_dir / "config.json"
        self.config = self._load()
        self.threads = {}

    def _load(self) -> dict:
        if self.config_path.exists():
            return json.loads(self.config_path.read_text(encoding="utf-8"))

        return {
            "team_name": "default",
            "members": [],
        }

    def _save(self):
        self.config_path.write_text(
            json.dumps(self.config, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _find(self, name: str) -> dict | None:
        for member in self.config["members"]:
            if member["name"] == name:
                return member

        return None

    def spawn(self, name: str, role: str, prompt: str) -> str:
        member = self._find(name)

        if member:
            if member["status"] not in ("idle", "shutdown"):
                return f"Error: '{name}' is currently {member['status']}"

            member["status"] = "working"
            member["role"] = role
        else:
            member = {
                "name": name,
                "role": role,
                "status": "working",
            }
            self.config["members"].append(member)

        self._save()

        thread = threading.Thread(
            target=self._loop,
            args=(name, role, prompt),
            daemon=True,
        )
        thread.start()

        self.threads[name] = thread

        return f"Spawned '{name}' (role: {role})"

    def _set_status(self, name: str, status: str):
        member = self._find(name)

        if member:
            member["status"] = status
            self._save()

    def _dispatch_tool(self, name: str, tool_name: str, tool_args: dict) -> tuple[str, bool]:
        idle_requested = False

        if tool_name == "idle":
            idle_requested = True
            output = "Entering idle phase."

        elif tool_name == "claim_task":
            output = self.task_mgr.claim(tool_args["task_id"], name)

        elif tool_name == "send_message":
            output = self.bus.send(
                name,
                tool_args["to"],
                tool_args["content"],
            )

        else:
            dispatch = {
                "bash": lambda **kw: self.run_bash(kw["command"]),
                "read_file": lambda **kw: self.run_read(kw["path"]),
                "write_file": lambda **kw: self.run_write(
                    kw["path"],
                    kw["content"],
                ),
                "edit_file": lambda **kw: self.run_edit(
                    kw["path"],
                    kw["old_text"],
                    kw["new_text"],
                ),
            }

            handler = dispatch.get(tool_name)

            if not handler:
                output = f"Unknown tool: {tool_name}"
            else:
                output = handler(**tool_args)

        return str(output), idle_requested

    def _loop(self, name: str, role: str, prompt: str):
        team_name = self.config["team_name"]

        system_prompt = (
            f"You are '{name}', role: {role}, team: {team_name}, at {self.workdir}. "
            f"Use idle when done with current work. You may auto-claim tasks."
        )

        messages = [
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": prompt,
            },
        ]

        tools = build_team_tools()

        while True:
            # -- WORK PHASE --
            for _ in range(50):
                inbox = self.bus.read_inbox(name)

                for msg in inbox:
                    if msg.get("type") == "shutdown_request":
                        self._set_status(name, "shutdown")
                        return

                    messages.append({
                        "role": "user",
                        "content": json.dumps(msg, ensure_ascii=False),
                    })

                try:
                    response = self.client.chat.completions.create(
                        model=self.model,
                        messages=messages,
                        tools=tools,
                        tool_choice="auto",
                        max_tokens=8000,
                    )
                except Exception:
                    self._set_status(name, "shutdown")
                    return

                msg = response.choices[0].message

                if not msg.tool_calls:
                    if msg.content:
                        messages.append({
                            "role": "assistant",
                            "content": msg.content,
                        })
                    break

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

                idle_requested = False

                for tool_call in msg.tool_calls:
                    tool_name = tool_call.function.name

                    try:
                        tool_args = json.loads(
                            tool_call.function.arguments or "{}"
                        )
                    except json.JSONDecodeError as e:
                        output = f"Error: invalid tool arguments JSON: {e}"
                    else:
                        try:
                            output, one_idle = self._dispatch_tool(
                                name,
                                tool_name,
                                tool_args,
                            )
                            idle_requested = idle_requested or one_idle
                        except Exception as e:
                            output = f"Error: {e}"

                    print(f"  [{name}] {tool_name}: {str(output)[:120]}")

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": str(output)[:50000],
                    })

                if idle_requested:
                    break

            # -- IDLE PHASE --
            self._set_status(name, "idle")

            resume = False
            wait_rounds = self.idle_timeout // max(self.poll_interval, 1)

            for _ in range(wait_rounds):
                time.sleep(self.poll_interval)

                inbox = self.bus.read_inbox(name)

                if inbox:
                    for msg in inbox:
                        if msg.get("type") == "shutdown_request":
                            self._set_status(name, "shutdown")
                            return

                        messages.append({
                            "role": "user",
                            "content": json.dumps(msg, ensure_ascii=False),
                        })

                    resume = True
                    break

                unclaimed = self._find_unclaimed_tasks()

                if unclaimed:
                    task = unclaimed[0]
                    self.task_mgr.claim(task["id"], name)

                    if len(messages) <= 3:
                        messages.insert(0, {
                            "role": "user",
                            "content": (
                                f"<identity>You are '{name}', role: {role}, "
                                f"team: {team_name}.</identity>"
                            ),
                        })
                        messages.insert(1, {
                            "role": "assistant",
                            "content": f"I am {name}. Continuing.",
                        })

                    messages.append({
                        "role": "user",
                        "content": (
                            f"<auto-claimed>Task #{task['id']}: {task['subject']}\n"
                            f"{task.get('description', '')}</auto-claimed>"
                        ),
                    })

                    messages.append({
                        "role": "assistant",
                        "content": f"Claimed task #{task['id']}. Working on it.",
                    })

                    resume = True
                    break

            if not resume:
                self._set_status(name, "shutdown")
                return

            self._set_status(name, "working")

    def _find_unclaimed_tasks(self) -> list[dict]:
        unclaimed = []

        for f in sorted(self.tasks_dir.glob("task_*.json")):
            task = json.loads(f.read_text(encoding="utf-8"))

            if (
                task.get("status") == "pending"
                and not task.get("owner")
                and not task.get("blockedBy")
            ):
                unclaimed.append(task)

        return unclaimed

    def list_all(self) -> str:
        if not self.config["members"]:
            return "No teammates."

        lines = [f"Team: {self.config['team_name']}"]

        for member in self.config["members"]:
            lines.append(
                f"  {member['name']} ({member['role']}): {member['status']}"
            )

        return "\n".join(lines)

    def member_names(self) -> list:
        return [
            member["name"]
            for member in self.config["members"]
        ]