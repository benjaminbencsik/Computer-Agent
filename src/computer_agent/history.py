from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

from platformdirs import user_data_dir


@dataclass
class Conversation:
    id: str
    title: str
    messages: list[dict[str, str]] = field(default_factory=list)


class ChatHistory:
    def __init__(self, path: Path | None = None):
        self.path = path or Path(user_data_dir("ComputerAgent")) / "conversations.json"
        self.conversations = self._load()

    def _load(self) -> list[Conversation]:
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return [Conversation(**item) for item in data if isinstance(item, dict)]
        except (OSError, ValueError, TypeError):
            return []

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps([asdict(item) for item in self.conversations], indent=2),
            encoding="utf-8",
        )

    def create(self, first_message: str) -> Conversation:
        title = " ".join(first_message.split())[:38] or "New chat"
        conversation = Conversation(id=uuid.uuid4().hex, title=title)
        self.conversations.insert(0, conversation)
        self.save()
        return conversation

    def get(self, conversation_id: str | None) -> Conversation | None:
        return next((item for item in self.conversations if item.id == conversation_id), None)
