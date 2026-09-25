from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field

import httpx

from .config import Settings

_UNSUPPORTED_TOOLS_MARKERS = (
    "does not support tools",
    "does not support function calling",
    "tool use is not supported",
    "tools\" is not supported",
    "unknown field \"tools\"",
)


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class ModelReply:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    used_tools: bool = False


class ToolCallingUnsupported(RuntimeError):
    """Raised internally when a provider rejects a request because tools are unsupported."""


def _looks_like_unsupported_tools(body: str) -> bool:
    lowered = body.lower()
    return any(marker in lowered for marker in _UNSUPPORTED_TOOLS_MARKERS)


def _safe_json_object(text: str | None) -> dict:
    if not text:
        return {}
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


class ModelProvider:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.supports_tools = True

    def complete(
        self,
        system: str,
        history: list[dict],
        screenshot: bytes | None,
        tools: list[dict] | None = None,
    ) -> ModelReply:
        method = self._anthropic if self.settings.provider.lower() == "anthropic" else self._openai_compatible
        offer_tools = bool(tools) and self.supports_tools and self.settings.native_tool_calling
        try:
            return method(system, history, screenshot, tools if offer_tools else None)
        except ToolCallingUnsupported:
            if not offer_tools:
                raise
            self.supports_tools = False
            return method(system, history, screenshot, None)

    def _openai_compatible(
        self,
        system: str,
        history: list[dict],
        screenshot: bytes | None,
        tools: list[dict] | None,
    ) -> ModelReply:
        url = self.settings.base_url.rstrip("/") + "/chat/completions"
        headers = {"Content-Type": "application/json"}
        if self.settings.api_key:
            headers["Authorization"] = f"Bearer {self.settings.api_key}"
        messages = [{"role": "system", "content": system}, *_openai_history(history)]
        if screenshot:
            messages.append(_openai_image_message(screenshot))
        payload: dict = {"model": self.settings.model, "messages": messages, "temperature": 0.1}
        if tools:
            payload["tools"] = [_openai_tool(spec) for spec in tools]
            payload["tool_choice"] = "auto"
        with httpx.Client(timeout=120) as client:
            response = client.post(url, headers=headers, json=payload)
            if response.status_code == 400 and tools and _looks_like_unsupported_tools(response.text):
                raise ToolCallingUnsupported(response.text)
            response.raise_for_status()
            message = response.json()["choices"][0]["message"]
        calls = [
            ToolCall(
                id=str(call.get("id") or index),
                name=call["function"]["name"],
                arguments=_safe_json_object(call["function"].get("arguments")),
            )
            for index, call in enumerate(message.get("tool_calls") or [])
        ]
        return ModelReply(text=message.get("content") or "", tool_calls=calls, used_tools=bool(tools))

    def _anthropic(
        self,
        system: str,
        history: list[dict],
        screenshot: bytes | None,
        tools: list[dict] | None,
    ) -> ModelReply:
        url = self.settings.base_url.rstrip("/") + "/v1/messages"
        messages = _anthropic_history(history)
        if screenshot:
            messages.append(_anthropic_image_message(screenshot))
        payload: dict = {
            "model": self.settings.model,
            "max_tokens": 2048,
            "system": system,
            "messages": messages,
        }
        if tools:
            payload["tools"] = [_anthropic_tool(spec) for spec in tools]
        with httpx.Client(timeout=120) as client:
            response = client.post(
                url,
                headers={
                    "x-api-key": self.settings.api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json=payload,
            )
            if response.status_code == 400 and tools and _looks_like_unsupported_tools(response.text):
                raise ToolCallingUnsupported(response.text)
            response.raise_for_status()
            blocks = response.json()["content"]
        text = "".join(block.get("text", "") for block in blocks if block.get("type") == "text")
        calls = [
            ToolCall(id=block["id"], name=block["name"], arguments=block.get("input") or {})
            for block in blocks
            if block.get("type") == "tool_use"
        ]
        return ModelReply(text=text, tool_calls=calls, used_tools=bool(tools))


def _openai_tool(spec: dict) -> dict:
    return {
        "type": "function",
        "function": {
            "name": spec["name"],
            "description": spec.get("description", ""),
            "parameters": spec.get("parameters") or {"type": "object", "properties": {}},
        },
    }


def _anthropic_tool(spec: dict) -> dict:
    return {
        "name": spec["name"],
        "description": spec.get("description", ""),
        "input_schema": spec.get("parameters") or {"type": "object", "properties": {}},
    }


def _openai_history(history: list[dict]) -> list[dict]:
    messages = []
    for turn in history:
        role = str(turn.get("role") or "user")
        tool_call = turn.get("tool_call")
        if role == "assistant" and isinstance(tool_call, dict):
            call_id = str(tool_call.get("id") or "tool_call")
            name = str(tool_call.get("name") or "")
            arguments = tool_call.get("arguments")
            if not isinstance(arguments, dict):
                arguments = {}
            messages.append(
                {
                    "role": "assistant",
                    "content": turn.get("thought") or None,
                    "tool_calls": [
                        {
                            "id": call_id,
                            "type": "function",
                            "function": {
                                "name": name,
                                "arguments": json.dumps(arguments, ensure_ascii=False),
                            },
                        }
                    ],
                }
            )
        elif role == "tool":
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": str(turn.get("tool_call_id") or ""),
                    "content": str(turn.get("content") or ""),
                }
            )
        else:
            messages.append({"role": role, "content": str(turn.get("content") or "")})
    return messages


def _anthropic_history(history: list[dict]) -> list[dict]:
    messages = []
    for turn in history:
        role = str(turn.get("role") or "user")
        tool_call = turn.get("tool_call")
        if role == "assistant" and isinstance(tool_call, dict):
            call_id = str(tool_call.get("id") or "tool_call")
            name = str(tool_call.get("name") or "")
            arguments = tool_call.get("arguments")
            if not isinstance(arguments, dict):
                arguments = {}
            content: list[dict] = []
            thought = turn.get("thought")
            if thought:
                content.append({"type": "text", "text": str(thought)})
            content.append(
                {
                    "type": "tool_use",
                    "id": call_id,
                    "name": name,
                    "input": arguments,
                }
            )
            messages.append({"role": "assistant", "content": content})
        elif role == "tool":
            messages.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": str(turn.get("tool_call_id") or ""),
                            "content": str(turn.get("content") or ""),
                        }
                    ],
                }
            )
        else:
            messages.append({"role": role, "content": str(turn.get("content") or "")})
    return messages


def _openai_image_message(screenshot: bytes) -> dict:
    return {
        "role": "user",
        "content": [
            {"type": "text", "text": "Current screenshot:"},
            {
                "type": "image_url",
                "image_url": {
                    "url": "data:image/png;base64," + base64.b64encode(screenshot).decode()
                },
            },
        ],
    }


def _anthropic_image_message(screenshot: bytes) -> dict:
    return {
        "role": "user",
        "content": [
            {"type": "text", "text": "Current screenshot:"},
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
