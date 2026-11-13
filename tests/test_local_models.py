from __future__ import annotations

import os

import pytest

from computer_agent.local_models import OllamaInstaller


@pytest.mark.skipif(os.name != "nt", reason="Windows shell launch is Windows-only")
def test_ollama_installer_launch_uses_windows_shell(monkeypatch, tmp_path):
    installer = tmp_path / "OllamaSetup.exe"
    installer.write_bytes(b"test")
    launched = []

    monkeypatch.setattr(os, "startfile", lambda path: launched.append(path))

    OllamaInstaller.launch(installer)

    assert launched == [str(installer)]
