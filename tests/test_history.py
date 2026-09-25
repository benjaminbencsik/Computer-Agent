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


def test_delete_chat_persists(tmp_path):
    path = tmp_path / "conversations.json"
    history = ChatHistory(path)
    first = history.create("Keep me")
    second = history.create("Delete me")

    assert history.delete(second.id) is True
    assert history.delete("missing") is False

    restored = ChatHistory(path)
    assert [chat.id for chat in restored.conversations] == [first.id]
