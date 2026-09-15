from __future__ import annotations

import json
import re
from collections.abc import Callable

from .providers import ModelProvider
from .tools import ToolRunner

SYSTEM_PROMPT = """You are Computer Agent, operating a Windows PC for its owner.
Work toward the user's stated task. Inspect the latest screenshot before choosing coordinates.
Tools may be available as native function/tool calls; use them when offered. Otherwise return
EXACTLY one JSON object and no markdown. Choose one form:
{{"thought":"short reason","action":{{"name":"tool name","arguments":{{}}}}}}
{{"thought":"short reason","final":"concise result"}}
Never claim an action succeeded until its tool result confirms it. Do not weaken security controls,
obtain credentials, make purchases, publish content, or delete data without clear user direction.

{tools}
"""


class Agent:
    def __init__(self, provider: ModelProvider, tools: ToolRunner, max_steps: int = 20):
        self.provider = provider
        self.tools = tools
        self.max_steps = max_steps

    @staticmethod
    def _parse(text: str) -> dict:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.IGNORECASE)
        try:
            value = json.loads(cleaned)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
            if not match:
                raise ValueError("Model did not return a JSON action")
            value = json.loads(match.group(0))
        if not isinstance(value, dict):
            raise TypeError("Model response must be a JSON object")
        return value

    def _run_tool(self, name: str, arguments: dict, event: Callable[[str, str], None]) -> str:
        event("action", f"{name}: {json.dumps(arguments, ensure_ascii=False)}")
        try:
            result = self.tools.run(name, arguments)
        except Exception as exc:
            result = f"ERROR: {type(exc).__name__}: {exc}"
        event("result", result)
        return result

    def run(self, task: str, event: Callable[[str, str], None]) -> str:
        history: list[dict] = [{"role": "user", "content": task}]
        system = SYSTEM_PROMPT.format(tools=self.tools.schema())
        tool_specs = self.tools.tool_specs()
        for step in range(1, self.max_steps + 1):
            event("status", f"Thinking — step {step}/{self.max_steps}")
            screenshot = self.tools.screenshot()
            reply = self.provider.complete(system, history, screenshot, tool_specs)

            if reply.tool_calls:
                if reply.text.strip():
                    event("thought", reply.text.strip())
                if len(reply.tool_calls) > 1:
                    event(
                        "status",
                        f"Ignoring {len(reply.tool_calls) - 1} extra tool call(s); "
                        "actions run one at a time.",
                    )
                call = reply.tool_calls[0]
                result = self._run_tool(call.name, call.arguments, event)
                history.append(
                    {
                        "role": "assistant",
                        "thought": reply.text.strip(),
                        "tool_call": {"id": call.id, "name": call.name, "arguments": call.arguments},
                    }
                )
                history.append({"role": "tool", "tool_call_id": call.id, "content": result})
                continue

            try:
                decision = self._parse(reply.text)
            except (ValueError, TypeError):
                if reply.used_tools:
                    return reply.text.strip() or "Stopped: the model returned an empty response."
                raise
            thought = str(decision.get("thought", ""))
            if thought:
                event("thought", thought)
            if "final" in decision:
                return str(decision["final"])
            action = decision.get("action")
            if not isinstance(action, dict) or not isinstance(action.get("name"), str):
                raise TypeError("Model response contains neither final nor a valid action")
            name = action["name"]
            arguments = action.get("arguments") or {}
            if not isinstance(arguments, dict):
                raise TypeError("Action arguments must be an object")
            result = self._run_tool(name, arguments, event)
            history.extend(
                [
                    {"role": "assistant", "content": json.dumps(decision)},
                    {"role": "user", "content": f"Tool result: {result}\nContinue the task."},
                ]
            )
        return f"Stopped after the {self.max_steps}-step safety limit."
