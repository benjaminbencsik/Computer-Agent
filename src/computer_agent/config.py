from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from platformdirs import user_config_dir

from .secrets_store import SecretStore


@dataclass
class Settings:
    provider: str = "Ollama"
    base_url: str = "http://localhost:11434/v1"
    model: str = "qwen2.5vl:7b"
    api_key: str = ""
    max_steps: int = 20
    auto_approve: bool = False
    native_tool_calling: bool = True

    @property
    def path(self) -> Path:
        return Path(user_config_dir("ComputerAgent")) / "settings.json"

    @classmethod
    def load(cls) -> Settings:
        path = Path(user_config_dir("ComputerAgent")) / "settings.json"
        settings = cls()
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                data.pop("api_key", None)
                settings = cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
            except (OSError, ValueError, TypeError):
                settings = cls()
        settings.api_key = SecretStore.get(settings.provider)
        return settings

    def save(self) -> None:
        SecretStore.set(self.provider, self.api_key)
        data = asdict(self)
        data.pop("api_key", None)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")
