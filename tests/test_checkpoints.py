from __future__ import annotations

import json

from computer_agent.checkpoints import Checkpoint, CheckpointStore, history_through


def test_checkpoints_are_persisted_and_reloaded(tmp_path):
    store = CheckpointStore("conv-1", root=tmp_path)
    store.append(Checkpoint(step=1, thought="click ok", action="click", arguments={"x": 1}, result="Clicked"))
    store.append(
        Checkpoint(
            step=2,
            thought="save file",
            action="write_file",
            arguments={"path": "a.txt", "content": "hi"},
            result="Wrote 2 characters",
            undo={"kind": "write_file", "path": "a.txt", "existed": False},
        )
    )

    reloaded = CheckpointStore("conv-1", root=tmp_path)
    assert [c.action for c in reloaded.checkpoints] == ["click", "write_file"]
    assert reloaded.last_undoable().action == "write_file"


def test_last_undoable_returns_none_when_nothing_reversible(tmp_path):
    store = CheckpointStore("conv-2", root=tmp_path)
    store.append(Checkpoint(step=1, thought="", action="click", arguments={}, result="Clicked"))
    assert store.last_undoable() is None


def test_clear_empties_and_persists(tmp_path):
    store = CheckpointStore("conv-3", root=tmp_path)
    store.append(Checkpoint(step=1, thought="", action="click", arguments={}, result="Clicked"))
    store.clear()
    assert store.checkpoints == []
    assert CheckpointStore("conv-3", root=tmp_path).checkpoints == []


def test_history_through_rebuilds_conversation_up_to_a_step():
    checkpoints = [
        Checkpoint(step=1, thought="t1", action="click", arguments={"x": 1}, result="r1"),
        Checkpoint(step=2, thought="t2", action="wait", arguments={"seconds": 1}, result="r2"),
        Checkpoint(step=3, thought="t3", action="click", arguments={"x": 2}, result="r3"),
    ]
    history = history_through(checkpoints, "do the thing", upto_step=2)

    assert history[0] == {"role": "user", "content": "do the thing"}
    assert len(history) == 5  # user task + 2 * (assistant, user) pairs
    first_decision = json.loads(history[1]["content"])
    assert first_decision == {"thought": "t1", "action": {"name": "click", "arguments": {"x": 1}}}
    assert history[2]["content"] == "Tool result: r1\nContinue the task."
    assert "t3" not in history[-1]["content"] and "t3" not in history[-2]["content"]
