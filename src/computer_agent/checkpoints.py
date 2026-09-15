from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from platformdirs import user_data_dir


@dataclass
class Checkpoint:
    step: int
    thought: str
    action: str | None
    arguments: dict[str, Any]
    result: str
    undo: dict[str, Any] | None = None
    timestamp: float = field(default_factory=time.time)


class CheckpointStore:
    """Persists the step-by-step trace of one agent run so it can be resumed
    (replayed up to a step, then continued) and so reversible actions can be
    undone later, independent of the chat transcript shown in the UI."""

    def __init__(self, conversation_id: str, root: Path | None = None):
        self.conversation_id = conversation_id
        base = root or Path(user_data_dir("ComputerAgent")) / "checkpoints"
        self.path = base / f"{conversation_id}.json"
        self.checkpoints: list[Checkpoint] = self._load()

    def _load(self) -> list[Checkpoint]:
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return [Checkpoint(**item) for item in data if isinstance(item, dict)]
        except (OSError, ValueError, TypeError):
            return []

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps([asdict(item) for item in self.checkpoints], indent=2), encoding="utf-8"
        )

    def append(self, checkpoint: Checkpoint) -> None:
        self.checkpoints.append(checkpoint)
        self.save()

    def clear(self) -> None:
        self.checkpoints = []
        self.save()

    def last_undoable(self) -> Checkpoint | None:
        for checkpoint in reversed(self.checkpoints):
            if checkpoint.undo:
                return checkpoint
        return None

    def mark_undone(self, checkpoint: Checkpoint) -> None:
        checkpoint.undo = None
        self.save()


def history_through(checkpoints: list[Checkpoint], task: str, upto_step: int) -> list[dict]:
    """Rebuild the provider-neutral conversation history an agent run would have
    accumulated through the given step, for resuming a task from a checkpoint."""
    history: list[dict] = [{"role": "user", "content": task}]
    for checkpoint in checkpoints:
        if checkpoint.step > upto_step:
            break
        decision = {
            "thought": checkpoint.thought,
            "action": {"name": checkpoint.action, "arguments": checkpoint.arguments},
        }
        history.append({"role": "assistant", "content": json.dumps(decision)})
        history.append(
            {"role": "user", "content": f"Tool result: {checkpoint.result}\nContinue the task."}
        )
    return history
