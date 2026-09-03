from computer_agent.updater import UpdateClient


def test_version_tuple_handles_tags_and_prerelease_suffixes():
    assert UpdateClient._version_tuple("v0.2.0") == (0, 2, 0)
    assert UpdateClient._version_tuple("1.4.2-beta") == (1, 4, 2)


def test_invalid_version_is_safe():
    assert UpdateClient._version_tuple("latest") == (0,)
