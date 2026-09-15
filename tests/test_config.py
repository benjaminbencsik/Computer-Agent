from __future__ import annotations

import json
from typing import ClassVar

from computer_agent import config as config_module
from computer_agent.config import Settings


class FakeSecretStore:
    store: ClassVar[dict[str, str]] = {}

    @classmethod
    def get(cls, provider):
        return cls.store.get(provider, "")

    @classmethod
    def set(cls, provider, value):
        if value:
            cls.store[provider] = value
        else:
            cls.store.pop(provider, None)


def _use_tmp_config_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(config_module, "user_config_dir", lambda _name: str(tmp_path))
    FakeSecretStore.store.clear()
    monkeypatch.setattr(config_module, "SecretStore", FakeSecretStore)


def test_save_persists_api_key_to_secret_store_not_json(tmp_path, monkeypatch):
    _use_tmp_config_dir(monkeypatch, tmp_path)
    settings = Settings(provider="Anthropic", api_key="sk-test")
    settings.save()
    assert FakeSecretStore.store["Anthropic"] == "sk-test"
    on_disk = json.loads((tmp_path / "settings.json").read_text())
    assert "api_key" not in on_disk


def test_load_rehydrates_api_key_from_secret_store(tmp_path, monkeypatch):
    _use_tmp_config_dir(monkeypatch, tmp_path)
    FakeSecretStore.store["Anthropic"] = "sk-saved"
    (tmp_path / "settings.json").write_text(
        json.dumps({"provider": "Anthropic", "model": "claude-x"})
    )
    settings = Settings.load()
    assert settings.provider == "Anthropic"
    assert settings.model == "claude-x"
    assert settings.api_key == "sk-saved"


def test_load_with_no_file_checks_secret_store_for_default_provider(tmp_path, monkeypatch):
    _use_tmp_config_dir(monkeypatch, tmp_path)
    FakeSecretStore.store["Ollama"] = "unused-local-key"
    settings = Settings.load()
    assert settings.provider == "Ollama"
    assert settings.api_key == "unused-local-key"
