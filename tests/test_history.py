from computer_agent.history import ChatHistory


def test_conversations_are_persisted_newest_first(tmp_path):
    path = tmp_path / "conversations.json"
    history = ChatHistory(path)
    first = history.create("My first task")
    first.messages.append({"label": "User", "text": "Hello"})
    history.save()
    history.create("My newer task")

    restored = ChatHistory(path)
    assert [chat.title for chat in restored.conversations] == ["My newer task", "My first task"]
    assert restored.get(first.id).messages == [{"label": "User", "text": "Hello"}]
