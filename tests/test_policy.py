import sys

import pytest

from computer_agent import tools as tools_module
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


def test_browser_actions_are_registered_with_correct_mutating_policy():
    for action in ("browser_open", "browser_click", "browser_type"):
        assert action in ToolRunner.MUTATING
    for action in ("browser_snapshot", "browser_close"):
        assert action not in ToolRunner.MUTATING


def test_tool_runner_close_without_browser_is_a_noop():
    runner = ToolRunner(lambda _name, _args: True)
    runner.close()


class _FakeGui:
    def __init__(self, image):
        self._image = image
        self.clicks: list[tuple[int, int, str]] = []

    def screenshot(self):
        return self._image

    def click(self, x, y, button="left"):
        self.clicks.append((x, y, button))


def _blank_image(width=800, height=600):
    from PIL import Image

    return Image.new("RGB", (width, height), color="white")


def test_zoom_screenshot_is_read_only_click_zoomed_is_mutating():
    assert "zoom_screenshot" not in ToolRunner.MUTATING
    assert "click_zoomed" in ToolRunner.MUTATING


def test_zoom_screenshot_queues_a_cropped_magnified_screenshot(monkeypatch):
    from io import BytesIO

    from PIL import Image

    fake = _FakeGui(_blank_image())
    monkeypatch.setattr(tools_module, "_gui", lambda: fake)
    runner = ToolRunner(lambda _name, _args: True)

    result = runner.run("zoom_screenshot", {"x": 400, "y": 300, "radius": 100, "scale": 2})
    assert "400, 300" in result or "(400, 300)" in result

    pending = runner.take_pending_screenshot()
    assert pending is not None
    zoomed = Image.open(BytesIO(pending))
    assert zoomed.size == (400, 400)  # (2*radius)*scale square
    assert runner.take_pending_screenshot() is None  # consumed once


def test_click_zoomed_converts_coordinates_back_to_real_screen(monkeypatch):
    fake = _FakeGui(_blank_image())
    monkeypatch.setattr(tools_module, "_gui", lambda: fake)
    runner = ToolRunner(lambda _name, _args: True, auto_approve=True)

    runner.run("zoom_screenshot", {"x": 400, "y": 300, "radius": 100, "scale": 2})
    # crop region is (300,200)-(500,400) at 2x, so zoomed (100,50) -> real (350,225)
    result = runner.run("click_zoomed", {"x": 100, "y": 50})

    assert fake.clicks == [(350, 225, "left")]
    assert "Clicked (350, 225)" in result


def test_click_zoomed_without_a_prior_zoom_is_rejected():
    runner = ToolRunner(lambda _name, _args: True, auto_approve=True)
    with pytest.raises(ToolError, match="zoom_screenshot"):
        runner.run("click_zoomed", {"x": 1, "y": 1})


def test_downscale_to_fit_leaves_small_images_alone():
    from computer_agent.tools import _downscale_to_fit

    image = _blank_image(800, 600)
    result = _downscale_to_fit(image, 1568)
    assert result.size == (800, 600)


def test_downscale_to_fit_shrinks_oversized_images_preserving_aspect_ratio():
    from computer_agent.tools import _downscale_to_fit

    image = _blank_image(3840, 2160)  # 4K, 16:9
    result = _downscale_to_fit(image, 1568)
    assert max(result.size) == 1568
    assert result.size == (1568, 882)  # 2160 * (1568/3840) = 882


def test_screenshot_downscales_oversized_captures(monkeypatch):
    from io import BytesIO

    from PIL import Image

    fake = _FakeGui(_blank_image(3840, 2160))
    monkeypatch.setattr(tools_module, "_gui", lambda: fake)
    runner = ToolRunner(lambda _name, _args: True)

    png_bytes = runner.screenshot()
    captured = Image.open(BytesIO(png_bytes))
    assert max(captured.size) == ToolRunner.MAX_SCREENSHOT_DIMENSION


def test_click_converts_coordinates_from_the_downscaled_screenshot_to_real_pixels(monkeypatch):
    fake = _FakeGui(_blank_image(3840, 2160))  # downscales to 1568x882 (factor ~2.449)
    monkeypatch.setattr(tools_module, "_gui", lambda: fake)
    runner = ToolRunner(lambda _name, _args: True, auto_approve=True)

    runner.screenshot()
    result = runner.run("click", {"x": 784, "y": 441})  # dead center of the shown image

    assert fake.clicks == [(1920, 1080, "left")]  # dead center of the real 4K screen
    assert "Clicked (1920, 1080)" in result


def test_click_is_unscaled_when_the_screenshot_was_not_downscaled(monkeypatch):
    fake = _FakeGui(_blank_image(800, 600))
    monkeypatch.setattr(tools_module, "_gui", lambda: fake)
    runner = ToolRunner(lambda _name, _args: True, auto_approve=True)

    runner.screenshot()
    runner.run("click", {"x": 100, "y": 50})

    assert fake.clicks == [(100, 50, "left")]


def test_zoom_screenshot_never_exceeds_the_screenshot_size_cap(monkeypatch):
    fake = _FakeGui(_blank_image(3840, 2160))
    monkeypatch.setattr(tools_module, "_gui", lambda: fake)
    runner = ToolRunner(lambda _name, _args: True)

    # A large radius/scale combination that would otherwise produce a huge image.
    runner.run("zoom_screenshot", {"x": 1920, "y": 1080, "radius": 700, "scale": 8})
    from io import BytesIO

    from PIL import Image

    pending = runner.take_pending_screenshot()
    zoomed = Image.open(BytesIO(pending))
    assert max(zoomed.size) <= ToolRunner.MAX_SCREENSHOT_DIMENSION


def test_click_zoomed_is_single_use(monkeypatch):
    fake = _FakeGui(_blank_image())
    monkeypatch.setattr(tools_module, "_gui", lambda: fake)
    runner = ToolRunner(lambda _name, _args: True, auto_approve=True)

    runner.run("zoom_screenshot", {"x": 400, "y": 300})
    runner.run("click_zoomed", {"x": 10, "y": 10})
    with pytest.raises(ToolError, match="zoom_screenshot"):
        runner.run("click_zoomed", {"x": 10, "y": 10})


class _FakeBrowser:
    def __init__(self):
        self.closed = False

    def open(self, url):
        return f"Opened {url}"

    def snapshot(self, max_elements=60):
        return f"[0] <button> up to {max_elements}"

    def click(self, index):
        return f"Clicked element [{index}]"

    def fill(self, index, text):
        return f"Typed {text!r} into element [{index}]"

    def close(self):
        self.closed = True
        return "Closed browser"


def test_browser_tools_dispatch_through_tool_runner():
    runner = ToolRunner(lambda _name, _args: True, auto_approve=True)
    fake = _FakeBrowser()
    runner._browser = fake

    assert runner.run("browser_open", {"url": "https://example.com"}) == "Opened https://example.com"
    assert runner.run("browser_snapshot", {}) == "[0] <button> up to 60"
    assert runner.run("browser_click", {"index": 0}) == "Clicked element [0]"
    assert runner.run("browser_type", {"index": 1, "text": "hi"}) == "Typed 'hi' into element [1]"
    runner.close()
    assert fake.closed is True
