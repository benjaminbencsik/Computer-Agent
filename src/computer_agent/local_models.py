from __future__ import annotations

import json
import os
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path

import httpx


class OllamaClient:
    def __init__(self, base_url: str):
        root = base_url.rstrip("/")
        self.base_url = root.removesuffix("/v1")

    def installed(self) -> list[dict]:
        response = httpx.get(self.base_url + "/api/tags", timeout=10)
        response.raise_for_status()
        return response.json().get("models", [])

    def pull(self, model: str, progress: Callable[[str, int], None]) -> None:
        with httpx.stream(
            "POST", self.base_url + "/api/pull", json={"name": model, "stream": True}, timeout=None
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line:
                    continue
                update = json.loads(line)
                total = int(update.get("total") or 0)
                completed = int(update.get("completed") or 0)
                percent = int(completed * 100 / total) if total else 0
                progress(str(update.get("status", "Downloading")), percent)


class OllamaInstaller:
    DOWNLOAD_URL = "https://ollama.com/download/OllamaSetup.exe"

    @classmethod
    def download(cls, progress: Callable[[str, int], None]) -> Path:
        if os.name != "nt":
            raise RuntimeError("The automatic Ollama installer is available only on Windows")
        target = Path(tempfile.gettempdir()) / "OllamaSetup.exe"
        with httpx.stream("GET", cls.DOWNLOAD_URL, follow_redirects=True, timeout=None) as response:
            response.raise_for_status()
            total = int(response.headers.get("content-length") or 0)
            completed = 0
            with target.open("wb") as output:
                for chunk in response.iter_bytes(1024 * 1024):
                    output.write(chunk)
                    completed += len(chunk)
                    percent = int(completed * 100 / total) if total else 0
                    progress("Downloading Ollama", percent)
        cls.verify_signature(target)
        return target

    @staticmethod
    def verify_signature(path: Path) -> None:
        escaped_path = str(path).replace("'", "''")
        command = (
            f"$s = Get-AuthenticodeSignature -LiteralPath '{escaped_path}'; Write-Output $s.Status"
        )
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode != 0 or result.stdout.strip() != "Valid":
            path.unlink(missing_ok=True)
            raise RuntimeError(
                "The downloaded Ollama installer did not have a valid Windows signature"
            )

    @staticmethod
    def launch(path: Path) -> None:
        subprocess.Popen([str(path)], close_fds=True)
