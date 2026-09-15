from __future__ import annotations

import hashlib
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

import httpx


@dataclass(frozen=True)
class ReleaseInfo:
    version: str
    page_url: str
    installer_url: str
    checksum_url: str


class UpdateClient:
    LATEST_URL = "https://api.github.com/repos/benjaminbencsik/Computer-Agent/releases/latest"
    LIST_URL = "https://api.github.com/repos/benjaminbencsik/Computer-Agent/releases"
    HEADERS: ClassVar[dict[str, str]] = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "Computer-Agent",
    }

    @staticmethod
    def _version_tuple(value: str) -> tuple[int, ...]:
        clean = value.lower().removeprefix("v").split("-", 1)[0]
        try:
            return tuple(int(part) for part in clean.split("."))
        except ValueError:
            return (0,)

    def _fetch_latest(self, channel: str) -> dict | None:
        if channel == "beta":
            response = httpx.get(
                self.LIST_URL, headers=self.HEADERS, params={"per_page": 5}, timeout=20
            )
            response.raise_for_status()
            releases = [r for r in response.json() if not r.get("draft")]
            return releases[0] if releases else None
        response = httpx.get(self.LATEST_URL, headers=self.HEADERS, timeout=20)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()

    def check(self, current_version: str, channel: str = "stable") -> ReleaseInfo | None:
        release = self._fetch_latest(channel)
        if release is None:
            return None
        version = str(release.get("tag_name", "")).removeprefix("v")
        if self._version_tuple(version) <= self._version_tuple(current_version):
            return None
        assets = {asset["name"]: asset["browser_download_url"] for asset in release["assets"]}
        installer = assets.get("ComputerAgent-Setup.exe")
        checksum = assets.get("ComputerAgent-Setup.exe.sha256")
        if not installer or not checksum:
            raise RuntimeError("The latest release is missing its installer or checksum")
        return ReleaseInfo(version, str(release["html_url"]), installer, checksum)

    def download(self, release: ReleaseInfo, progress: Callable[[str, int], None]) -> Path:
        target = Path(tempfile.gettempdir()) / f"ComputerAgent-{release.version}-Setup.exe"
        with httpx.stream(
            "GET", release.installer_url, follow_redirects=True, timeout=None
        ) as response:
            response.raise_for_status()
            total = int(response.headers.get("content-length") or 0)
            completed = 0
            digest = hashlib.sha256()
            with target.open("wb") as output:
                for chunk in response.iter_bytes(1024 * 1024):
                    output.write(chunk)
                    digest.update(chunk)
                    completed += len(chunk)
                    progress("Downloading update", int(completed * 100 / total) if total else 0)
        checksum_response = httpx.get(release.checksum_url, follow_redirects=True, timeout=20)
        checksum_response.raise_for_status()
        expected = checksum_response.text.strip().split()[0].lower()
        if digest.hexdigest().lower() != expected:
            target.unlink(missing_ok=True)
            raise RuntimeError("Update checksum verification failed")
        return target

    @staticmethod
    def launch(path: Path) -> None:
        subprocess.Popen([str(path)], close_fds=True)
