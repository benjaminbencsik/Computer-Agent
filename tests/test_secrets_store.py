from __future__ import annotations

from computer_agent import secrets_store
from computer_agent.secrets_store import SecretStore


class FakeKeyring:
    def __init__(self):
        self.store: dict[tuple[str, str], str] = {}

    def get_password(self, service, username):
        return self.store.get((service, username))

    def set_password(self, service, username, password):
        self.store[(service, username)] = password

    def delete_password(self, service, username):
        del self.store[(service, username)]


def test_set_then_get_round_trips(monkeypatch):
    fake = FakeKeyring()
    monkeypatch.setattr(secrets_store, "_keyring", lambda: fake)
    SecretStore.set("Anthropic", "sk-test")
    assert SecretStore.get("Anthropic") == "sk-test"


def test_get_missing_returns_empty_string(monkeypatch):
    monkeypatch.setattr(secrets_store, "_keyring", lambda: FakeKeyring())
    assert SecretStore.get("Anthropic") == ""


def test_set_empty_value_deletes_existing_secret(monkeypatch):
    fake = FakeKeyring()
    monkeypatch.setattr(secrets_store, "_keyring", lambda: fake)
    SecretStore.set("Anthropic", "sk-test")
    SecretStore.set("Anthropic", "")
    assert SecretStore.get("Anthropic") == ""


def test_backend_errors_are_swallowed(monkeypatch):
    class Broken:
        def get_password(self, *args):
            raise RuntimeError("no backend")

        def set_password(self, *args):
            raise RuntimeError("no backend")

        def delete_password(self, *args):
            raise RuntimeError("no backend")

    monkeypatch.setattr(secrets_store, "_keyring", lambda: Broken())
    SecretStore.set("Anthropic", "sk-test")
    assert SecretStore.get("Anthropic") == ""
