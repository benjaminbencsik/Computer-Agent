from __future__ import annotations

import base64
from dataclasses import dataclass

import httpx

from .config import Settings


@dataclass
class ModelReply:
    text: str


class ModelProvider:
    def __init__(self, settings: Settings):
        self.settings = settings

    def complete(self, system: str, messages: list[dict], screenshot: bytes | None) -> ModelReply:
        if self.settings.provider.lower() == "anthropic":
            return self._anthropic(system, messages, screenshot)
        return self._openai_compatible(system, messages, screenshot)

    def _openai_compatible(
        self, system: str, messages: list[dict], screenshot: bytes | None
    ) -> ModelReply:
        url = self.settings.base_url.rstrip("/") + "/chat/completions"
        headers = {"Content-Type": "application/json"}
        if self.settings.api_key:
            headers["Authorization"] = f"Bearer {self.settings.api_key}"
        payload_messages = [{"role": "system", "content": system}, *messages]
        if screenshot:
            content = [
                {"type": "text", "text": messages[-1]["content"]},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": "data:image/png;base64," + base64.b64encode(screenshot).decode()
                    },
                },
            ]
            payload_messages[-1] = {"role": "user", "content": content}
        with httpx.Client(timeout=120) as client:
            response = client.post(
                url,
                headers=headers,
                json={
                    "model": self.settings.model,
                    "messages": payload_messages,
                    "temperature": 0.1,
                },
            )
            response.raise_for_status()
            return ModelReply(response.json()["choices"][0]["message"]["content"])

    def _anthropic(self, system: str, messages: list[dict], screenshot: bytes | None) -> ModelReply:
        url = self.settings.base_url.rstrip("/") + "/v1/messages"
        request_messages = [dict(message) for message in messages]
        if screenshot:
            request_messages[-1] = {
                "role": "user",
                "content": [
                    {"type": "text", "text": messages[-1]["content"]},
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": base64.b64encode(screenshot).decode(),
                        },
                    },
                ],
            }
        with httpx.Client(timeout=120) as client:
            response = client.post(
                url,
                headers={
                    "x-api-key": self.settings.api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": self.settings.model,
                    "max_tokens": 2048,
                    "system": system,
                    "messages": request_messages,
                },
            )
            response.raise_for_status()
            blocks = response.json()["content"]
            return ModelReply("".join(block.get("text", "") for block in blocks))
