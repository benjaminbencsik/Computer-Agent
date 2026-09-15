from __future__ import annotations

import json

import httpx
import pytest

from computer_agent.config import Settings
from computer_agent.providers import ModelProvider

_RealClient = httpx.Client


def _install_transport(monkeypatch, handler):
    requests: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return handler(request)

    def fake_client(**kwargs):
        kwargs.pop("timeout", None)
        return _RealClient(transport=httpx.MockTransport(record))

    monkeypatch.setattr("computer_agent.providers.httpx.Client", fake_client)
    return requests


TOOLS = [{"name": "click", "description": "Click", "parameters": {"type": "object", "properties": {}}}]


def test_openai_compatible_includes_tools_and_parses_tool_calls(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {"name": "click", "arguments": '{"x": 1, "y": 2}'},
                                }
                            ],
                        }
                    }
                ]
            },
        )

    requests = _install_transport(monkeypatch, handler)
    provider = ModelProvider(Settings(provider="OpenAI Compatible", base_url="http://x/v1"))
    reply = provider.complete("sys", [{"role": "user", "content": "hi"}], None, TOOLS)

    body = json.loads(requests[0].content)
    assert body["tools"][0]["function"]["name"] == "click"
    assert reply.used_tools is True
    assert reply.tool_calls[0].name == "click"
    assert reply.tool_calls[0].arguments == {"x": 1, "y": 2}


def test_openai_compatible_plain_text_reply_has_no_tool_calls(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"choices": [{"message": {"role": "assistant", "content": "all done"}}]}
        )

    _install_transport(monkeypatch, handler)
    provider = ModelProvider(Settings(provider="OpenAI Compatible", base_url="http://x/v1"))
    reply = provider.complete("sys", [{"role": "user", "content": "hi"}], None, None)
    assert reply.text == "all done"
    assert reply.tool_calls == []
    assert reply.used_tools is False


def test_openai_compatible_falls_back_when_tools_unsupported(monkeypatch):
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            return httpx.Response(400, text='{"error": "model does not support tools"}')
        return httpx.Response(
            200, json={"choices": [{"message": {"role": "assistant", "content": "ok"}}]}
        )

    requests = _install_transport(monkeypatch, handler)
    provider = ModelProvider(Settings(provider="OpenAI Compatible", base_url="http://x/v1"))
    reply = provider.complete("sys", [{"role": "user", "content": "hi"}], None, TOOLS)

    assert len(requests) == 2
    assert "tools" in json.loads(requests[0].content)
    assert "tools" not in json.loads(requests[1].content)
    assert reply.text == "ok"
    assert provider.supports_tools is False

    # Subsequent calls should not retry tools at all.
    provider.complete("sys", [{"role": "user", "content": "hi"}], None, TOOLS)
    assert len(requests) == 3
    assert "tools" not in json.loads(requests[2].content)


def test_openai_history_round_trips_tool_call_and_result(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"choices": [{"message": {"role": "assistant", "content": "next"}}]}
        )

    requests = _install_transport(monkeypatch, handler)
    provider = ModelProvider(Settings(provider="OpenAI Compatible", base_url="http://x/v1"))
    history = [
        {"role": "user", "content": "task"},
        {
            "role": "assistant",
            "thought": "clicking",
            "tool_call": {"id": "call_1", "name": "click", "arguments": {"x": 1, "y": 2}},
        },
        {"role": "tool", "tool_call_id": "call_1", "content": "Clicked (1, 2)"},
    ]
    provider.complete("sys", history, b"png-bytes", None)

    messages = json.loads(requests[0].content)["messages"]
    assert messages[2]["tool_calls"][0]["function"]["name"] == "click"
    assert messages[3] == {"role": "tool", "tool_call_id": "call_1", "content": "Clicked (1, 2)"}
    assert messages[-1]["content"][0]["text"] == "Current screenshot:"


def test_anthropic_parses_text_and_tool_use_blocks(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "content": [
                    {"type": "text", "text": "thinking"},
                    {"type": "tool_use", "id": "toolu_1", "name": "click", "input": {"x": 3}},
                ]
            },
        )

    requests = _install_transport(monkeypatch, handler)
    provider = ModelProvider(Settings(provider="Anthropic", base_url="http://x", api_key="k"))
    reply = provider.complete("sys", [{"role": "user", "content": "hi"}], None, TOOLS)

    body = json.loads(requests[0].content)
    assert body["tools"][0]["name"] == "click"
    assert reply.text == "thinking"
    assert reply.tool_calls[0].name == "click"
    assert reply.tool_calls[0].arguments == {"x": 3}


def test_anthropic_history_round_trips_tool_result(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"content": [{"type": "text", "text": "next"}]})

    requests = _install_transport(monkeypatch, handler)
    provider = ModelProvider(Settings(provider="Anthropic", base_url="http://x", api_key="k"))
    history = [
        {"role": "user", "content": "task"},
        {
            "role": "assistant",
            "thought": "clicking",
            "tool_call": {"id": "toolu_1", "name": "click", "arguments": {"x": 1}},
        },
        {"role": "tool", "tool_call_id": "toolu_1", "content": "Clicked (1, 2)"},
    ]
    provider.complete("sys", history, None, None)

    messages = json.loads(requests[0].content)["messages"]
    assert messages[1]["content"][1]["type"] == "tool_use"
    assert messages[2]["content"][0]["tool_use_id"] == "toolu_1"


@pytest.mark.parametrize("provider_name", ["OpenAI Compatible", "Anthropic"])
def test_native_tool_calling_can_be_disabled(monkeypatch, provider_name):
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert "tools" not in body
        if provider_name == "Anthropic":
            return httpx.Response(200, json={"content": [{"type": "text", "text": "ok"}]})
        return httpx.Response(
            200, json={"choices": [{"message": {"role": "assistant", "content": "ok"}}]}
        )

    _install_transport(monkeypatch, handler)
    settings = Settings(provider=provider_name, base_url="http://x", api_key="k", native_tool_calling=False)
    provider = ModelProvider(settings)
    reply = provider.complete("sys", [{"role": "user", "content": "hi"}], None, TOOLS)
    assert reply.text == "ok"


def test_ollama_requests_include_keep_alive(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"choices": [{"message": {"role": "assistant", "content": "ok"}}]}
        )

    requests = _install_transport(monkeypatch, handler)
    settings = Settings(provider="Ollama", base_url="http://localhost:11434/v1", ollama_keep_alive="30m")
    ModelProvider(settings).complete("sys", [{"role": "user", "content": "hi"}], None, None)

    assert json.loads(requests[0].content)["keep_alive"] == "30m"


def test_non_ollama_requests_omit_keep_alive(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"choices": [{"message": {"role": "assistant", "content": "ok"}}]}
        )

    requests = _install_transport(monkeypatch, handler)
    settings = Settings(provider="OpenAI Compatible", base_url="http://x", ollama_keep_alive="30m")
    ModelProvider(settings).complete("sys", [{"role": "user", "content": "hi"}], None, None)

    assert "keep_alive" not in json.loads(requests[0].content)


def test_empty_ollama_keep_alive_is_omitted(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"choices": [{"message": {"role": "assistant", "content": "ok"}}]}
        )

    requests = _install_transport(monkeypatch, handler)
    settings = Settings(provider="Ollama", base_url="http://localhost:11434/v1", ollama_keep_alive="")
    ModelProvider(settings).complete("sys", [{"role": "user", "content": "hi"}], None, None)

    assert "keep_alive" not in json.loads(requests[0].content)
