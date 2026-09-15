import sys

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


def test_ui_tree_is_a_known_read_only_action():
    assert "ui_tree" not in ToolRunner.MUTATING
    assert "click_element" in ToolRunner.MUTATING


@pytest.mark.skipif(sys.platform == "win32", reason="asserts the non-Windows error path")
def test_ui_tree_reports_a_clean_error_off_windows():
    runner = ToolRunner(lambda _name, _args: True)
    with pytest.raises(ToolError, match="UI Automation"):
        runner.run("ui_tree", {})


def test_capture_undo_ignores_non_write_actions():
    runner = ToolRunner(lambda _name, _args: True)
    assert runner.capture_undo("click", {"x": 1, "y": 2}) is None


def test_capture_and_apply_undo_restores_overwritten_file(tmp_path):
    target = tmp_path / "notes.txt"
    target.write_text("original", encoding="utf-8")
    runner = ToolRunner(lambda _name, _args: True, auto_approve=True)
    entry = runner.capture_undo("write_file", {"path": str(target), "content": "new"})
    runner.run("write_file", {"path": str(target), "content": "new"})
    assert target.read_text(encoding="utf-8") == "new"

    assert ToolRunner.undo(entry) == f"Restored previous contents of {target}"
    assert target.read_text(encoding="utf-8") == "original"


def test_undo_removes_file_that_did_not_exist_before(tmp_path):
    target = tmp_path / "new.txt"
    runner = ToolRunner(lambda _name, _args: True, auto_approve=True)
    entry = runner.capture_undo("write_file", {"path": str(target), "content": "created"})
    runner.run("write_file", {"path": str(target), "content": "created"})
    assert target.exists()

    ToolRunner.undo(entry)
    assert not target.exists()


def test_undo_rejects_unknown_kind():
    with pytest.raises(ToolError):
        ToolRunner.undo({"kind": "click"})
