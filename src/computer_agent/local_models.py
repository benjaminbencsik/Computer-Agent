from __future__ import annotations

import json
from collections.abc import Callable

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
