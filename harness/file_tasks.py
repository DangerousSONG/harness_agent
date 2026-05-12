# === SECTION: file_tasks (s07) ===
# harness/file_tasks.py

import json

from runtime.backends import TaskStore


class TaskManager:
    def __init__(self, store: TaskStore):
        self.store = store

    def create(self, subject: str, description: str = "") -> str:
        task = self.store.create(subject, description)
        return json.dumps(task, indent=2, ensure_ascii=False)

    def get(self, task_id: int) -> str:
        return json.dumps(
            self.store.get(task_id),
            indent=2,
            ensure_ascii=False,
        )

    def update(
        self,
        task_id: int,
        status: str | None = None,
        add_blocked_by: list | None = None,
        remove_blocked_by: list | None = None,
    ) -> str:
        task = self.store.update(
            task_id,
            status,
            add_blocked_by,
            remove_blocked_by,
        )

        if task is None:
            return f"Task {task_id} deleted"

        return json.dumps(task, indent=2, ensure_ascii=False)

    def list_all(self) -> str:
        tasks = self.store.list()

        if not tasks:
            return "No tasks."

        lines = []

        for task in tasks:
            marker = {
                "pending": "[ ]",
                "in_progress": "[>]",
                "completed": "[x]",
            }.get(task.get("status"), "[?]")

            owner = f" @{task['owner']}" if task.get("owner") else ""
            blocked = (
                f" (blocked by: {task['blockedBy']})"
                if task.get("blockedBy")
                else ""
            )

            lines.append(
                f"{marker} #{task['id']}: {task['subject']}{owner}{blocked}"
            )

        return "\n".join(lines)

    def claim(self, task_id: int, owner: str) -> str:
        self.store.claim(task_id, owner)
        return f"Claimed task #{task_id} for {owner}"

    def list_unclaimed(self) -> list[dict]:
        return self.store.list_unclaimed()
