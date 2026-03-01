from dataclasses import dataclass, field


@dataclass
class Message:
    role: str       # "user" | "agent" | "error"
    content: str
    timestamp: str
    source: str = "browser"  # "browser" | "api" | "telegram" | "discord" | "system"


class MessageLog:
    """In-memory chat history for the lifetime of the server process."""

    def __init__(self) -> None:
        self._entries: list[Message] = []

    def append(self, role: str, content: str, timestamp: str, source: str = "browser") -> None:
        self._entries.append(Message(role=role, content=content, timestamp=timestamp, source=source))

    def all(self) -> list[Message]:
        return list(self._entries)

    def clear(self) -> None:
        self._entries.clear()

    def __len__(self) -> int:
        return len(self._entries)


# Module-level singleton shared across the app
message_log = MessageLog()
