import httpx

from computer_agent.updater import UpdateClient

_RealClient = httpx.Client


def _install_transport(monkeypatch, handler):
    def record(request: httpx.Request) -> httpx.Response:
        return handler(request)

    def fake_get(url, **kwargs):
        with _RealClient(transport=httpx.MockTransport(record)) as client:
            return client.get(url, **{k: v for k, v in kwargs.items() if k != "timeout"})

    monkeypatch.setattr("computer_agent.updater.httpx.get", fake_get)


def _release(tag: str, prerelease: bool = False) -> dict:
    return {
        "tag_name": tag,
        "html_url": f"https://example.com/{tag}",
        "prerelease": prerelease,
        "assets": [
            {"name": "ComputerAgent-Setup.exe", "browser_download_url": "https://example.com/setup.exe"},
            {"name": "ComputerAgent-Setup.exe.sha256", "browser_download_url": "https://example.com/setup.sha256"},
        ],
    }


def test_version_tuple_handles_tags_and_prerelease_suffixes():
    assert UpdateClient._version_tuple("v0.2.0") == (0, 2, 0)
    assert UpdateClient._version_tuple("1.4.2-beta") == (1, 4, 2)


def test_invalid_version_is_safe():
    assert UpdateClient._version_tuple("latest") == (0,)


def test_stable_channel_uses_the_latest_endpoint(monkeypatch):
    seen_urls = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_urls.append(str(request.url))
        return httpx.Response(200, json=_release("v1.0.0"))

    _install_transport(monkeypatch, handler)
    release = UpdateClient().check("0.9.0", channel="stable")
    assert release.version == "1.0.0"
    assert seen_urls[0].endswith("/releases/latest")


def test_beta_channel_uses_the_list_endpoint_and_takes_the_newest(monkeypatch):
    seen_urls = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_urls.append(str(request.url))
        return httpx.Response(200, json=[_release("v1.1.0-beta.1", prerelease=True), _release("v1.0.0")])

    _install_transport(monkeypatch, handler)
    release = UpdateClient().check("0.9.0", channel="beta")
    assert release.version == "1.1.0-beta.1"
    assert "/releases" in seen_urls[0] and not seen_urls[0].endswith("/releases/latest")


def test_stable_channel_with_no_releases_returns_none(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "Not Found"})

    _install_transport(monkeypatch, handler)
    assert UpdateClient().check("0.9.0", channel="stable") is None


def test_current_version_already_up_to_date_returns_none(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_release("v1.0.0"))

    _install_transport(monkeypatch, handler)
    assert UpdateClient().check("1.0.0", channel="stable") is None
