# harness/background.py
# === SECTION: background (s08) ===
import subprocess
import threading
import uuid
from pathlib import Path
from queue import Queue


class BackgroundManager:
    def __init__(self, workdir: Path):
        self.workdir = workdir
        self.tasks = {}
        self.notifications = Queue()

    def run(self, command: str, timeout: int = 120) -> str:
        task_id = str(uuid.uuid4())[:8]

        self.tasks[task_id] = {
            "status": "running",
            "command": command,
            "result": None,
        }

        threading.Thread(
            target=self._exec,
            args=(task_id, command, timeout),
            daemon=True,
        ).start()

        return f"Background task {task_id} started: {command[:80]}"

    def _exec(self, task_id: str, command: str, timeout: int):
        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=self.workdir,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )

            stdout = result.stdout or ""
            stderr = result.stderr or ""

            output = (stdout + stderr).strip()[:50000]

            self.tasks[task_id].update({
                "status": "completed",
                "result": output or "(no output)",
            })

        except Exception as e:
            self.tasks[task_id].update({
                "status": "error",
                "result": str(e),
            })

        self.notifications.put({
            "task_id": task_id,
            "status": self.tasks[task_id]["status"],
            "result": self.tasks[task_id]["result"][:500],
        })

    def check(self, task_id: str | None = None) -> str:
        if task_id:
            task = self.tasks.get(task_id)

            if not task:
                return f"Unknown: {task_id}"

            return f"[{task['status']}] {task.get('result') or '(running)'}"

        return "\n".join(
            f"{k}: [{v['status']}] {v['command'][:60]}"
            for k, v in self.tasks.items()
        ) or "No bg tasks."

    def drain(self) -> list:
        notifications = []

        while not self.notifications.empty():
            notifications.append(self.notifications.get_nowait())

        return notifications