# harness/messaging.py
# === SECTION: messaging (s09) ===

from runtime.backends import MessageStore


class MessageBus:
    def __init__(self, store: MessageStore):
        self.store = store

    def send(
        self,
        sender: str,
        to: str,
        content: str,
        msg_type: str = "message",
        extra: dict | None = None,
    ) -> str:
        self.store.send(sender, to, content, msg_type, extra)
        return f"Sent {msg_type} to {to}"

    def read_inbox(self, name: str) -> list:
        return self.store.drain_inbox(name)

    def broadcast(self, sender: str, content: str, names: list[str]) -> str:
        count = self.store.broadcast(sender, content, names)
        return f"Broadcast to {count} teammates"
