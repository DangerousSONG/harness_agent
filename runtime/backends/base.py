from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any


class TaskStore(ABC):
    """Persistent task board storage."""

    @abstractmethod
    def create(self, subject: str, description: str = "") -> dict:
        raise NotImplementedError

    @abstractmethod
    def get(self, task_id: int) -> dict:
        raise NotImplementedError

    @abstractmethod
    def update(
        self,
        task_id: int,
        status: str | None = None,
        add_blocked_by: list[int] | None = None,
        remove_blocked_by: list[int] | None = None,
    ) -> dict | None:
        raise NotImplementedError

    @abstractmethod
    def list(self) -> list[dict]:
        raise NotImplementedError

    @abstractmethod
    def claim(self, task_id: int, owner: str) -> dict:
        raise NotImplementedError

    @abstractmethod
    def list_unclaimed(self) -> list[dict]:
        raise NotImplementedError


class MessageStore(ABC):
    """Mailbox/message transport for lead and teammates."""

    @abstractmethod
    def send(
        self,
        sender: str,
        to: str,
        content: str,
        msg_type: str = "message",
        extra: dict | None = None,
    ) -> dict:
        raise NotImplementedError

    @abstractmethod
    def drain_inbox(self, name: str) -> list[dict]:
        raise NotImplementedError

    @abstractmethod
    def broadcast(self, sender: str, content: str, names: list[str]) -> int:
        raise NotImplementedError


class JobQueue(ABC):
    """Background job execution and notification queue."""

    @abstractmethod
    def enqueue_shell(self, command: str, timeout: int = 120) -> str:
        raise NotImplementedError

    @abstractmethod
    def check(self, task_id: str | None = None) -> dict | list[dict] | None:
        raise NotImplementedError

    @abstractmethod
    def drain_notifications(self) -> list[dict]:
        raise NotImplementedError


class AgentRunner(ABC):
    """Runs teammate agents and stores their lifecycle state."""

    @abstractmethod
    def team_name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def upsert_member(self, name: str, role: str, status: str) -> dict:
        raise NotImplementedError

    @abstractmethod
    def get_member(self, name: str) -> dict | None:
        raise NotImplementedError

    @abstractmethod
    def set_member_status(self, name: str, status: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def list_members(self) -> list[dict]:
        raise NotImplementedError

    @abstractmethod
    def member_names(self) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    def start_teammate(
        self,
        name: str,
        target: Callable[..., Any],
        *args: Any,
    ) -> None:
        raise NotImplementedError


class ReviewStore(ABC):
    """Review gates such as shutdown and plan approval requests."""

    @abstractmethod
    def create_shutdown_request(self, target: str) -> str:
        raise NotImplementedError

    @abstractmethod
    def get_plan_request(self, request_id: str) -> dict | None:
        raise NotImplementedError

    @abstractmethod
    def set_plan_status(self, request_id: str, status: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def create_review(self, **fields: Any) -> dict:
        raise NotImplementedError

    @abstractmethod
    def get_review(self, review_id: str) -> dict | None:
        raise NotImplementedError

    @abstractmethod
    def list_reviews(self, status: str | None = None) -> list[dict]:
        raise NotImplementedError

    @abstractmethod
    def approve_review(self, review_id: str) -> dict:
        raise NotImplementedError

    @abstractmethod
    def reject_review(self, review_id: str) -> dict:
        raise NotImplementedError


class RuntimeBackend(ABC):
    """Factory for concrete runtime infrastructure."""

    task_store: TaskStore
    message_store: MessageStore
    job_queue: JobQueue
    agent_runner: AgentRunner
    review_store: ReviewStore
