from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
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

    def ensure_running(self, timeout: float = 12.0) -> str:
        try:
            self.installed()
            return self.base_url + "/v1"
        except httpx.HTTPError as first_error:
            if os.name != "nt":
                raise RuntimeError(
                    f"Ollama is not reachable at {self.base_url}. Start Ollama and try again."
                ) from first_error

        executable = shutil.which("ollama")
        if not executable:
            candidate = (
                Path(os.environ.get("LOCALAPPDATA", ""))
                / "Programs"
                / "Ollama"
                / "ollama.exe"
            )
            if candidate.exists():
                executable = str(candidate)

        if not executable:
            raise RuntimeError(
                "Ollama is not running and Computer Agent could not find Ollama for Windows. "
                "Open Settings → Manage local models → Install Ollama, or choose Ollama (WSL)."
            )

        try:
            subprocess.Popen(
                [executable, "serve"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except OSError as exc:
            raise RuntimeError(f"Computer Agent could not start Ollama: {exc}") from exc

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                self.installed()
                return self.base_url + "/v1"
            except httpx.HTTPError:
                time.sleep(0.5)
        raise RuntimeError(
            "Ollama was found but did not start in time. Open Ollama once, then retry the task."
        )

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


class WslOllamaClient:
    """Find and expose an Ollama installation running inside WSL."""

    def __init__(self, distro: str | None = None):
        self.distro = distro

    @staticmethod
    def _run_wsl(args: list[str], distro: str | None = None) -> subprocess.CompletedProcess:
        command = ["wsl.exe"]
        if distro:
            command += ["-d", distro]
        command += ["--", *args]
        return subprocess.run(
            command,
            capture_output=True,
            timeout=20,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

    @staticmethod
    def _decode(data: bytes) -> str:
        if not data:
            return ""
        if b"\x00" in data:
            try:
                return data.decode("utf-16-le", errors="ignore").replace("\x00", "")
            except UnicodeError:
                pass
        return data.decode("utf-8", errors="ignore").replace("\x00", "")

    @classmethod
    def distributions(cls) -> list[str]:
        if os.name != "nt" or not shutil.which("wsl.exe"):
            return []
        result = subprocess.run(
            ["wsl.exe", "-l", "-q"],
            capture_output=True,
            timeout=15,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        names = [line.strip() for line in cls._decode(result.stdout).splitlines() if line.strip()]
        return [
            name
            for name in names
            if name.lower() not in {"docker-desktop", "docker-desktop-data"}
        ]

    @classmethod
    def find_installation(cls) -> str:
        if os.name != "nt":
            raise RuntimeError("Ollama (WSL) is available only when Computer Agent runs on Windows.")
        if not shutil.which("wsl.exe"):
            raise RuntimeError("WSL is not installed or wsl.exe is not available.")

        for distro in cls.distributions():
            result = cls._run_wsl(
                ["sh", "-lc", "command -v ollama >/dev/null 2>&1 && printf FOUND"],
                distro,
            )
            if result.returncode == 0 and "FOUND" in cls._decode(result.stdout):
                return distro

        raise RuntimeError(
            "Computer Agent could not find Ollama in any WSL distribution. "
            "Install Ollama inside WSL, then select Ollama (WSL) again."
        )

    def _resolved_distro(self) -> str:
        if not self.distro:
            self.distro = self.find_installation()
        return self.distro

    def _wsl_ip(self) -> str:
        distro = self._resolved_distro()
        result = self._run_wsl(["sh", "-lc", "hostname -I | awk '{print $1}'"], distro)
        ip = self._decode(result.stdout).strip().splitlines()
        if result.returncode != 0 or not ip or not ip[0]:
            raise RuntimeError(f"Could not determine the WSL address for {distro}.")
        return ip[0].strip()

    def ensure_running(self, timeout: float = 15.0) -> str:
        distro = self._resolved_distro()

        # Use the selected WSL distribution directly rather than accidentally
        # connecting to a separate Ollama installation on Windows.
        # Start Ollama in the chosen distro and bind it to the WSL interface so
        # Windows can reach it even when localhost forwarding is unavailable.
        launch = self._run_wsl(
            [
                "sh",
                "-lc",
                (
                    "if ! pgrep -f 'ollama serve' >/dev/null 2>&1; then "
                    "nohup env OLLAMA_HOST=0.0.0.0:11434 ollama serve "
                    ">/tmp/computer-agent-ollama.log 2>&1 </dev/null & fi"
                ),
            ],
            distro,
        )
        if launch.returncode != 0:
            detail = self._decode(launch.stderr).strip()
            raise RuntimeError(
                f"Computer Agent found Ollama in {distro} but could not start it"
                + (f": {detail}" if detail else ".")
            )

        ip = self._wsl_ip()
        base = f"http://{ip}:11434"
        client = OllamaClient(base)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                client.installed()
                return base + "/v1"
            except httpx.HTTPError:
                time.sleep(0.5)

        raise RuntimeError(
            f"Ollama was found in WSL ({distro}) but Windows could not reach it. "
            "Try running 'OLLAMA_HOST=0.0.0.0:11434 ollama serve' inside that WSL distribution."
        )

    def installed(self) -> list[dict]:
        return OllamaClient(self.ensure_running()).installed()

    def pull(self, model: str, progress: Callable[[str, int], None]) -> None:
        OllamaClient(self.ensure_running()).pull(model, progress)


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
