# harness/background.py
# === SECTION: background (s08) ===

from runtime.backends import JobQueue


class BackgroundManager:
    def __init__(self, queue: JobQueue):
        self.queue = queue

    def run(self, command: str, timeout: int = 120) -> str:
        task_id = self.queue.enqueue_shell(command, timeout)
        return f"Background task {task_id} started: {command[:80]}"

    def check(self, task_id: str | None = None) -> str:
        result = self.queue.check(task_id)

        if task_id:
            if not result:
                return f"Unknown: {task_id}"
            return f"[{result['status']}] {result.get('result') or '(running)'}"

        tasks = result or []
        return "\n".join(
            f"{task['id']}: [{task['status']}] {task['command'][:60]}"
            for task in tasks
        ) or "No bg tasks."

    def drain(self) -> list:
        return self.queue.drain_notifications()
