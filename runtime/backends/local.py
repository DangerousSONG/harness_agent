from __future__ import annotations

import json
import subprocess
import threading
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from queue import Queue
from typing import Any

from .base import AgentRunner, JobQueue, MessageStore, ReviewStore, TaskStore


class LocalTaskStore(TaskStore):
    """File-backed task store for local development."""

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

    def _save(self, task: dict) -> None:
        self._task_path(task["id"]).write_text(
            json.dumps(task, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def create(self, subject: str, description: str = "") -> dict:
        task = {
            "id": self._next_id(),
            "subject": subject,
            "description": description,
            "status": "pending",
            "owner": None,
            "blockedBy": [],
        }
        self._save(task)
        return task

    def get(self, task_id: int) -> dict:
        path = self._task_path(task_id)
        if not path.exists():
            raise ValueError(f"Task {task_id} not found")
        return json.loads(path.read_text(encoding="utf-8"))

    def update(
        self,
        task_id: int,
        status: str | None = None,
        add_blocked_by: list[int] | None = None,
        remove_blocked_by: list[int] | None = None,
    ) -> dict | None:
        task = self.get(task_id)

        if status:
            task["status"] = status
            if status == "completed":
                self._unblock_completed_task(task_id)
            if status == "deleted":
                self._task_path(task_id).unlink(missing_ok=True)
                return None

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
        return task

    def _unblock_completed_task(self, completed_task_id: int) -> None:
        for task in self.list():
            if completed_task_id in task.get("blockedBy", []):
                task["blockedBy"].remove(completed_task_id)
                self._save(task)

    def list(self) -> list[dict]:
        return [
            json.loads(f.read_text(encoding="utf-8"))
            for f in sorted(self.tasks_dir.glob("task_*.json"))
        ]

    def claim(self, task_id: int, owner: str) -> dict:
        task = self.get(task_id)
        task["owner"] = owner
        task["status"] = "in_progress"
        self._save(task)
        return task

    def list_unclaimed(self) -> list[dict]:
        return [
            task for task in self.list()
            if (
                task.get("status") == "pending"
                and not task.get("owner")
                and not task.get("blockedBy")
            )
        ]


class LocalMessageStore(MessageStore):
    """JSONL mailbox store for local development."""

    def __init__(self, inbox_dir: Path):
        self.inbox_dir = inbox_dir
        self.inbox_dir.mkdir(parents=True, exist_ok=True)

    def _inbox_path(self, name: str) -> Path:
        return self.inbox_dir / f"{name}.jsonl"

    def send(
        self,
        sender: str,
        to: str,
        content: str,
        msg_type: str = "message",
        extra: dict | None = None,
    ) -> dict:
        msg = {
            "type": msg_type,
            "from": sender,
            "content": content,
            "timestamp": time.time(),
        }
        if extra:
            msg.update(extra)

        with open(self._inbox_path(to), "a", encoding="utf-8") as f:
            f.write(json.dumps(msg, ensure_ascii=False) + "\n")

        return msg

    def drain_inbox(self, name: str) -> list[dict]:
        path = self._inbox_path(name)
        if not path.exists():
            return []

        text = path.read_text(encoding="utf-8").strip()
        if not text:
            return []

        messages = [
            json.loads(line)
            for line in text.splitlines()
            if line.strip()
        ]
        path.write_text("", encoding="utf-8")
        return messages

    def broadcast(self, sender: str, content: str, names: list[str]) -> int:
        count = 0
        for name in names:
            if name != sender:
                self.send(sender, name, content, "broadcast")
                count += 1
        return count


class LocalJobQueue(JobQueue):
    """Thread-backed background queue for local development."""

    def __init__(self, workdir: Path):
        self.workdir = workdir
        self.tasks = {}
        self.notifications = Queue()

    def enqueue_shell(self, command: str, timeout: int = 120) -> str:
        task_id = str(uuid.uuid4())[:8]
        self.tasks[task_id] = {
            "id": task_id,
            "status": "running",
            "command": command,
            "result": None,
        }

        thread = threading.Thread(
            target=self._exec,
            args=(task_id, command, timeout),
            daemon=True,
        )
        thread.start()
        return task_id

    def _exec(self, task_id: str, command: str, timeout: int) -> None:
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
            output = ((result.stdout or "") + (result.stderr or "")).strip()
            self.tasks[task_id].update({
                "status": "completed",
                "result": output[:50000] or "(no output)",
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

    def check(self, task_id: str | None = None) -> dict | list[dict] | None:
        if task_id:
            return self.tasks.get(task_id)
        return list(self.tasks.values())

    def drain_notifications(self) -> list[dict]:
        notifications = []
        while not self.notifications.empty():
            notifications.append(self.notifications.get_nowait())
        return notifications


class LocalAgentRunner(AgentRunner):
    """Thread-backed teammate runner for local development."""

    def __init__(self, team_dir: Path):
        self.team_dir = team_dir
        self.team_dir.mkdir(parents=True, exist_ok=True)
        self.config_path = self.team_dir / "config.json"
        self.config = self._load()
        self.threads = {}

    def _load(self) -> dict:
        if self.config_path.exists():
            return json.loads(self.config_path.read_text(encoding="utf-8"))
        return {"team_name": "default", "members": []}

    def _save(self) -> None:
        self.config_path.write_text(
            json.dumps(self.config, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def team_name(self) -> str:
        return self.config["team_name"]

    def get_member(self, name: str) -> dict | None:
        for member in self.config["members"]:
            if member["name"] == name:
                return member
        return None

    def upsert_member(self, name: str, role: str, status: str) -> dict:
        member = self.get_member(name)
        if member:
            member["role"] = role
            member["status"] = status
        else:
            member = {"name": name, "role": role, "status": status}
            self.config["members"].append(member)
        self._save()
        return member

    def set_member_status(self, name: str, status: str) -> None:
        member = self.get_member(name)
        if member:
            member["status"] = status
            self._save()

    def list_members(self) -> list[dict]:
        return list(self.config["members"])

    def member_names(self) -> list[str]:
        return [member["name"] for member in self.config["members"]]

    def start_teammate(
        self,
        name: str,
        target: Callable[..., Any],
        *args: Any,
    ) -> None:
        thread = threading.Thread(target=target, args=args, daemon=True)
        thread.start()
        self.threads[name] = thread


class LocalReviewStore(ReviewStore):
    """In-process review state for local development."""

    def __init__(self):
        self.shutdown_requests = {}
        self.plan_requests = {}

    def create_shutdown_request(self, target: str) -> str:
        request_id = str(uuid.uuid4())[:8]
        self.shutdown_requests[request_id] = {
            "target": target,
            "status": "pending",
        }
        return request_id

    def get_plan_request(self, request_id: str) -> dict | None:
        return self.plan_requests.get(request_id)

    def set_plan_status(self, request_id: str, status: str) -> None:
        if request_id in self.plan_requests:
            self.plan_requests[request_id]["status"] = status


class LocalBackend:
    """Default backend that preserves the original single-machine behavior."""

    def __init__(self, project_root: Path, workdir: Path):
        self.task_store = LocalTaskStore(project_root / ".tasks")
        self.message_store = LocalMessageStore(project_root / ".team" / "inbox")
        self.job_queue = LocalJobQueue(workdir)
        self.agent_runner = LocalAgentRunner(project_root / ".team")
        self.review_store = LocalReviewStore()


class RedisMessageStore(MessageStore):
    """TODO: implement with Redis Streams or Pub/Sub plus durable consumer groups."""

    pass


class PostgresTaskStore(TaskStore):
    """TODO: implement with PostgreSQL rows, transactions, and row-level locks."""

    pass


class CeleryJobQueue(JobQueue):
    """TODO: implement with Celery workers and Redis/RabbitMQ result backend."""

    pass


class KubernetesAgentRunner(AgentRunner):
    """TODO: implement teammate execution with Kubernetes Jobs or worker Deployments."""

    pass
