from __future__ import annotations

import os
from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api")

from computer_agent.browser import BrowserController, BrowserError

# Lets this suite point at a pre-provisioned Chromium binary (e.g. in a sandboxed
# CI image) whose revision doesn't match the pip-installed playwright package's
# expected default. Production code never sets this; BrowserController() alone
# uses whatever `playwright install` downloaded, as real users will have.
_TEST_CHROMIUM_PATH = os.environ.get("COMPUTER_AGENT_TEST_CHROMIUM_PATH")


def _write_page(tmp_path: Path) -> str:
    page = tmp_path / "page.html"
    page.write_text(
        """<html><body>
<button id="go">Click me</button>
<input id="box" placeholder="type here">
<script>
document.getElementById('go').addEventListener('click', () => {
    document.getElementById('go').innerText = 'Clicked!';
});
</script>
</body></html>""",
        encoding="utf-8",
    )
    return page.as_uri()


@pytest.fixture
def controller():
    ctrl = BrowserController(headless=True, executable_path=_TEST_CHROMIUM_PATH)
    try:
        yield ctrl
    finally:
        ctrl.close()


def _open_or_skip(controller: BrowserController, url: str) -> str:
    try:
        return controller.open(url)
    except BrowserError as exc:
        pytest.skip(f"Chromium not available in this environment: {exc}")


def test_open_snapshot_click_and_fill(tmp_path, controller):
    url = _write_page(tmp_path)
    result = _open_or_skip(controller, url)
    assert result.startswith("Opened file://")

    snapshot = controller.snapshot()
    assert "<button>" in snapshot
    assert "<input>" in snapshot

    assert controller.click(0) == "Clicked element [0]"
    assert "Clicked!" in controller.snapshot()
    assert controller.fill(1, "hello world") == "Typed into element [1]"


def test_click_unknown_index_raises(tmp_path, controller):
    url = _write_page(tmp_path)
    _open_or_skip(controller, url)
    with pytest.raises(BrowserError):
        controller.click(99)


def test_open_adds_https_scheme_when_missing(controller, monkeypatch):
    calls = {}

    class FakePage:
        url = "https://example.com/"

        def goto(self, url, wait_until=None):
            calls["url"] = url

    monkeypatch.setattr(controller, "_ensure_page", lambda: FakePage())
    result = controller.open("example.com")
    assert calls["url"] == "https://example.com"
    assert result == "Opened https://example.com/"


def test_close_without_opening_is_a_noop():
    controller = BrowserController(headless=True, executable_path=_TEST_CHROMIUM_PATH)
    assert controller.close() == "Closed browser"
