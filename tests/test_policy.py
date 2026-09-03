import pytest

from computer_agent.agent import Agent
from computer_agent.tools import ToolError, ToolRunner


def test_parse_json_and_fenced_json():
    assert Agent._parse('{"final":"done"}')["final"] == "done"
    assert Agent._parse('```json\n{"final":"done"}\n```')["final"] == "done"


def test_mutating_action_can_be_denied():
    runner = ToolRunner(lambda _name, _args: False)
    assert runner.run("type_text", {"text": "secret"}) == "DENIED by user"


def test_unknown_action_is_rejected():
    runner = ToolRunner(lambda _name, _args: True)
    with pytest.raises(ToolError):
        runner.run("download_and_execute", {})


def test_dangerous_powershell_is_blocked_even_with_auto_approval():
    runner = ToolRunner(lambda _name, _args: True, auto_approve=True)
    with pytest.raises(ToolError, match="blocked"):
        runner.run("powershell", {"command": "Remove-Item -Recurse C:\\Users\\Example"})
