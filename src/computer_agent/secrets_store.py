from __future__ import annotations

import contextlib

SERVICE_NAME = "ComputerAgent"


def _keyring():
    import keyring

    return keyring


class SecretStore:
    """Persists provider API keys in the OS credential vault (Windows Credential
    Manager via keyring's WinVaultKeyring backend, Keychain on macOS, Secret
    Service on Linux) instead of writing them to disk in plain text."""

    @staticmethod
    def get(provider: str) -> str:
        try:
            return _keyring().get_password(SERVICE_NAME, provider) or ""
        except Exception:
            return ""

    @staticmethod
    def set(provider: str, value: str) -> None:
        if not value:
            SecretStore.delete(provider)
            return
        with contextlib.suppress(Exception):
            _keyring().set_password(SERVICE_NAME, provider, value)

    @staticmethod
    def delete(provider: str) -> None:
        with contextlib.suppress(Exception):
            _keyring().delete_password(SERVICE_NAME, provider)
