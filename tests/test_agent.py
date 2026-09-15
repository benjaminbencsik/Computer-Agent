from __future__ import annotations

import pytest

from computer_agent.agent import Agent
from computer_agent.providers import ModelReply, ToolCall


class FakeTools:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    def schema(self) -> str:
        return "schema"

    def tool_specs(self) -> list[dict]:
        return [{"name": "noop", "description": "", "parameters": {"type": "object", "properties": {}}}]

    def screenshot(self) -> bytes:
        return b"png"

    def run(self, name: str, arguments: dict) -> str:
        self.calls.append((name, arguments))
        return f"ran {name}"


class SequenceProvider:
    def __init__(self, replies: list[ModelReply]):
        self.replies = list(replies)
        self.calls: list[tuple[list[dict], list[dict] | None]] = []

    def complete(self, system, history, screenshot, tools=None):
        self.calls.append((list(history), tools))
        return self.replies.pop(0)


def test_agent_executes_native_tool_call_then_finishes():
    tools = FakeTools()
    provider = SequenceProvider(
        [
            ModelReply(
                text="clicking",
                tool_calls=[ToolCall(id="1", name="noop", arguments={"a": 1})],
                used_tools=True,
            ),
            ModelReply(text='{"final":"done"}', used_tools=True),
        ]
    )
    events: list[tuple[str, str]] = []
    result = Agent(provider, tools, max_steps=5).run("task", lambda k, t: events.append((k, t)))

    assert result == "done"
    assert tools.calls == [("noop", {"a": 1})]
    second_call_history = provider.calls[1][0]
    assert second_call_history[-2]["tool_call"] == {"id": "1", "name": "noop", "arguments": {"a": 1}}
    assert second_call_history[-1] == {"role": "tool", "tool_call_id": "1", "content": "ran noop"}
    assert ("thought", "clicking") in events
    assert ("result", "ran noop") in events


def test_agent_falls_back_to_text_json_when_no_tool_calls():
    tools = FakeTools()
    provider = SequenceProvider(
        [
            ModelReply(text='{"thought":"ok","action":{"name":"noop","arguments":{}}}'),
            ModelReply(text='{"final":"all done"}'),
        ]
    )
    result = Agent(provider, tools, max_steps=5).run("task", lambda k, t: None)
    assert result == "all done"
    assert tools.calls == [("noop", {})]


def test_agent_treats_final_plain_text_as_done_when_tools_were_offered():
    tools = FakeTools()
    provider = SequenceProvider(
        [ModelReply(text="All finished, nothing else to do.", used_tools=True)]
    )
    result = Agent(provider, tools, max_steps=5).run("task", lambda k, t: None)
    assert result == "All finished, nothing else to do."


def test_agent_raises_on_unparseable_text_without_native_tools():
    tools = FakeTools()
    provider = SequenceProvider([ModelReply(text="not json", used_tools=False)])
    with pytest.raises(ValueError):
        Agent(provider, tools, max_steps=5).run("task", lambda k, t: None)


def test_agent_ignores_extra_tool_calls_beyond_the_first():
    tools = FakeTools()
    provider = SequenceProvider(
        [
            ModelReply(
                text="",
                tool_calls=[
                    ToolCall(id="1", name="noop", arguments={}),
                    ToolCall(id="2", name="noop", arguments={"ignored": True}),
                ],
                used_tools=True,
            ),
            ModelReply(text='{"final":"done"}', used_tools=True),
        ]
    )
    events: list[tuple[str, str]] = []
    Agent(provider, tools, max_steps=5).run("task", lambda k, t: events.append((k, t)))
    assert tools.calls == [("noop", {})]
    assert any("Ignoring 1 extra tool call" in text for kind, text in events if kind == "status")
