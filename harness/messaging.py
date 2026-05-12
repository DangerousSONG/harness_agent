# harness/messaging.py
# === SECTION: messaging (s09) ===
import json
import time
from pathlib import Path


class MessageBus:
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
    ) -> str:
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

        return f"Sent {msg_type} to {to}"

    def read_inbox(self, name: str) -> list:
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

    def broadcast(self, sender: str, content: str, names: list[str]) -> str:
        count = 0

        for name in names:
            if name != sender:
                self.send(sender, name, content, "broadcast")
                count += 1

        return f"Broadcast to {count} teammates"