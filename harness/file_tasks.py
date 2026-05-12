# === SECTION: file_tasks (s07) ===
# harness/file_tasks.py

import json
from pathlib import Path


class TaskManager:
    def __init__(self, tasks_dir: Path):
        self.tasks_dir = tasks_dir
        self.tasks_dir.mkdir(parents=True, exist_ok=True)

    def _task_path(self, task_id: int) -> Path:
        return self.tasks_dir / f"task_{task_id}.json"

    def _next_id(self) -> int:
        ids = []

        for f in self.tasks_dir.glob("task_*.json"):
            try:
                ids.append(int(f.stem.split("_")[1]))
            except (IndexError, ValueError):
                continue

        return max(ids, default=0) + 1

    def _load(self, task_id: int) -> dict:
        path = self._task_path(task_id)

        if not path.exists():
            raise ValueError(f"Task {task_id} not found")

        return json.loads(path.read_text(encoding="utf-8"))

    def _save(self, task: dict):
        path = self._task_path(task["id"])
        path.write_text(
            json.dumps(task, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def create(self, subject: str, description: str = "") -> str:
        task = {
            "id": self._next_id(),
            "subject": subject,
            "description": description,
            "status": "pending",
            "owner": None,
            "blockedBy": [],
        }

        self._save(task)

        return json.dumps(task, indent=2, ensure_ascii=False)

    def get(self, task_id: int) -> str:
        return json.dumps(
            self._load(task_id),
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
        task = self._load(task_id)

        if status:
            task["status"] = status

            if status == "completed":
                self._unblock_completed_task(task_id)

            if status == "deleted":
                self._task_path(task_id).unlink(missing_ok=True)
                return f"Task {task_id} deleted"

        if add_blocked_by:
            task["blockedBy"] = sorted(
                set(task.get("blockedBy", []) + add_blocked_by)
            )

        if remove_blocked_by:
            task["blockedBy"] = [
                x for x in task.get("blockedBy", [])
                if x not in remove_blocked_by
            ]

        self._save(task)

        return json.dumps(task, indent=2, ensure_ascii=False)

    def _unblock_completed_task(self, completed_task_id: int):
        for f in self.tasks_dir.glob("task_*.json"):
            task = json.loads(f.read_text(encoding="utf-8"))

            if completed_task_id in task.get("blockedBy", []):
                task["blockedBy"].remove(completed_task_id)
                self._save(task)

    def list_all(self) -> str:
        tasks = [
            json.loads(f.read_text(encoding="utf-8"))
            for f in sorted(self.tasks_dir.glob("task_*.json"))
        ]

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
        task = self._load(task_id)
        task["owner"] = owner
        task["status"] = "in_progress"
        self._save(task)

        return f"Claimed task #{task_id} for {owner}"