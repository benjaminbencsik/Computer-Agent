from __future__ import annotations

import io
import subprocess
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, ClassVar

from PIL import Image

ApprovalCallback = Callable[[str, dict[str, Any]], bool]


def _gui():
    import pyautogui

    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.15
    return pyautogui


def _downscale_to_fit(image: Image.Image, max_dimension: int) -> Image.Image:
    """Shrink (never enlarge) an image so its longest side fits max_dimension.

    Vision models don't extract more detail from a screenshot far past their own
    input resolution, so sending one at native 4K just costs encode time and
    (for cloud providers) tokens -- especially painful for CPU-only inference.
    zoom_screenshot recovers detail on demand when it's actually needed.
    """
    width, height = image.size
    longest = max(width, height)
    if longest <= max_dimension:
        return image
    factor = max_dimension / longest
    new_size = (max(1, round(width * factor)), max(1, round(height * factor)))
    return image.resize(new_size, Image.LANCZOS)


class ToolError(RuntimeError):
    pass


class ToolRunner:
    MAX_SCREENSHOT_DIMENSION: ClassVar[int] = 1568
    MUTATING: ClassVar[set[str]] = {
        "click",
        "type_text",
        "hotkey",
        "powershell",
        "write_file",
        "click_element",
        "browser_open",
        "browser_click",
        "browser_type",
        "click_zoomed",
    }
    BLOCKED_PS: ClassVar[tuple[str, ...]] = (
        "remove-item -recurse",
        "format-volume",
        "clear-disk",
        "initialize-disk",
        "stop-computer",
        "restart-computer",
        "cipher /w",
        "bcdedit",
    )

    def __init__(self, approve: ApprovalCallback, auto_approve: bool = False):
        self.approve = approve
        self.auto_approve = auto_approve
        self._browser = None
        self._pending_screenshot: bytes | None = None
        self._zoom_origin: tuple[float, float, float] | None = None
        # real_pixels / shown_pixels for the most recent full screenshot(): click()
        # coordinates come back from the model in the *shown* image's pixel space, so
        # this converts them to real screen coordinates before clicking.
        self._screenshot_scale: float = 1.0

    def screenshot(self) -> bytes:
        image = _gui().screenshot()
        real_longest = max(image.size)
        shown = _downscale_to_fit(image, self.MAX_SCREENSHOT_DIMENSION)
        shown_longest = max(shown.size)
        self._screenshot_scale = real_longest / shown_longest if shown_longest else 1.0
        output = io.BytesIO()
        shown.save(output, format="PNG")
        return output.getvalue()

    def take_pending_screenshot(self) -> bytes | None:
        """Consume and return a zoomed screenshot queued by zoom_screenshot, if any."""
        data = self._pending_screenshot
        self._pending_screenshot = None
        return data

    @staticmethod
    def schema() -> str:
        return """Available actions:
- screen_info {} -> screen width and height
- click {"x": integer, "y": integer, "button": "left|right"}
- type_text {"text": string, "interval": number}
- hotkey {"keys": [string, ...]}
- wait {"seconds": number, max 10}
- powershell {"command": string, "timeout": integer, max 60}
- read_file {"path": string, "max_chars": integer}
- list_directory {"path": string}
- write_file {"path": string, "content": string}
- ui_tree {"max_depth": integer, "max_nodes": integer} -> Windows UI Automation tree of the
  foreground window: control type, name, automation id, and center point for each element
- click_element {"name": string, "automation_id": string, "control_type": string, "button": "left|right"}
  -> click a UI element found via ui_tree instead of guessing raw coordinates
- browser_open {"url": string} -> launch/reuse a Chromium browser and navigate to a URL
- browser_snapshot {"max_elements": integer} -> list interactive elements (links, buttons,
  inputs) on the current page with an index for each, grounded in the DOM
- browser_click {"index": integer} -> click the element at that index from browser_snapshot
- browser_type {"index": integer, "text": string} -> fill the element at that index with text
- browser_close {} -> close the browser session
- zoom_screenshot {"x": integer, "y": integer, "radius": integer, "scale": integer} -> capture
  a magnified crop of the screen centered on (x, y); shown as the screenshot on your next turn
- click_zoomed {"x": integer, "y": integer, "button": "left|right"} -> click using coordinates
  measured on the most recent zoomed screenshot (not the full screen); call zoom_screenshot first
Use coordinates from the latest screenshot. Prefer keyboard navigation when reliable.
Prefer ui_tree + click_element over raw click coordinates when the foreground window
supports UI Automation, since element positions do not drift with layout changes.
Prefer browser_snapshot + browser_click/browser_type over raw coordinates when working
inside a browser, since DOM-grounded selectors do not drift with page layout.
When a target is small or you are unsure of its exact position (common with smaller
local models), call zoom_screenshot on your best-guess location first, then use
click_zoomed on the magnified image instead of guessing raw coordinates."""

    @staticmethod
    def tool_specs() -> list[dict[str, Any]]:
        """JSON-schema tool definitions for native provider function/tool calling."""
        return [
            {
                "name": "screen_info",
                "description": "Get the screen width and height in pixels.",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
            {
                "name": "click",
                "description": "Click a screen coordinate from the latest screenshot.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "x": {"type": "integer"},
                        "y": {"type": "integer"},
                        "button": {"type": "string", "enum": ["left", "right"]},
                    },
                    "required": ["x", "y"],
                },
            },
            {
                "name": "type_text",
                "description": "Type text at the current keyboard focus.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "interval": {"type": "number", "description": "Seconds between keystrokes"},
                    },
                    "required": ["text"],
                },
            },
            {
                "name": "hotkey",
                "description": "Press a key combination, e.g. [\"ctrl\", \"c\"].",
                "parameters": {
                    "type": "object",
                    "properties": {"keys": {"type": "array", "items": {"type": "string"}}},
                    "required": ["keys"],
                },
            },
            {
                "name": "wait",
                "description": "Pause for up to 10 seconds.",
                "parameters": {
                    "type": "object",
                    "properties": {"seconds": {"type": "number"}},
                    "required": [],
                },
            },
            {
                "name": "powershell",
                "description": "Run a PowerShell command and return its output (max 60s timeout).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string"},
                        "timeout": {"type": "integer"},
                    },
                    "required": ["command"],
                },
            },
            {
                "name": "read_file",
                "description": "Read a text file's contents.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "max_chars": {"type": "integer"},
                    },
                    "required": ["path"],
                },
            },
            {
                "name": "list_directory",
                "description": "List the entries of a directory.",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            },
            {
                "name": "write_file",
                "description": "Write text content to a file, creating parent directories.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "content": {"type": "string"},
                    },
                    "required": ["path", "content"],
                },
            },
            {
                "name": "ui_tree",
                "description": (
                    "Read the Windows UI Automation tree of the foreground window: control "
                    "type, name, automation id, and center point for each named element."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "max_depth": {"type": "integer"},
                        "max_nodes": {"type": "integer"},
                    },
                    "required": [],
                },
            },
            {
                "name": "click_element",
                "description": (
                    "Click a UI element resolved by name/automation id/control type from "
                    "ui_tree, instead of guessing raw screen coordinates."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "automation_id": {"type": "string"},
                        "control_type": {"type": "string"},
                        "button": {"type": "string", "enum": ["left", "right"]},
                    },
                    "required": [],
                },
            },
            {
                "name": "browser_open",
                "description": "Launch or reuse a Chromium browser and navigate to a URL.",
                "parameters": {
                    "type": "object",
                    "properties": {"url": {"type": "string"}},
                    "required": ["url"],
                },
            },
            {
                "name": "browser_snapshot",
                "description": (
                    "List interactive elements (links, buttons, inputs) on the current page "
                    "with a stable index for each, grounded in the DOM."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {"max_elements": {"type": "integer"}},
                    "required": [],
                },
            },
            {
                "name": "browser_click",
                "description": "Click the element at the given index from browser_snapshot.",
                "parameters": {
                    "type": "object",
                    "properties": {"index": {"type": "integer"}},
                    "required": ["index"],
                },
            },
            {
                "name": "browser_type",
                "description": "Fill the element at the given index from browser_snapshot with text.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "index": {"type": "integer"},
                        "text": {"type": "string"},
                    },
                    "required": ["index", "text"],
                },
            },
            {
                "name": "browser_close",
                "description": "Close the browser session.",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
            {
                "name": "zoom_screenshot",
                "description": (
                    "Capture a magnified crop of the screen centered on (x, y). The zoomed "
                    "image is shown as the screenshot on your next turn -- use this before "
                    "click_zoomed when a target is small or its position is uncertain."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "x": {"type": "integer"},
                        "y": {"type": "integer"},
                        "radius": {"type": "integer", "description": "Half-width of the crop in screen pixels"},
                        "scale": {"type": "integer", "description": "Magnification factor"},
                    },
                    "required": ["x", "y"],
                },
            },
            {
                "name": "click_zoomed",
                "description": (
                    "Click using coordinates measured on the most recent zoom_screenshot "
                    "image, not the full screen. Call zoom_screenshot first."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "x": {"type": "integer"},
                        "y": {"type": "integer"},
                        "button": {"type": "string", "enum": ["left", "right"]},
                    },
                    "required": ["x", "y"],
                },
            },
        ]

    def run(self, name: str, arguments: dict[str, Any]) -> str:
        if name not in {
            "screen_info",
            "click",
            "type_text",
            "hotkey",
            "wait",
            "powershell",
            "read_file",
            "list_directory",
            "write_file",
            "ui_tree",
            "click_element",
            "browser_open",
            "browser_snapshot",
            "browser_click",
            "browser_type",
            "browser_close",
            "zoom_screenshot",
            "click_zoomed",
        }:
            raise ToolError(f"Unknown action: {name}")
        if name in self.MUTATING and not self.auto_approve and not self.approve(name, arguments):
            return "DENIED by user"
        method = getattr(self, f"_do_{name}")
        return str(method(**arguments))

    def _do_screen_info(self) -> str:
        width, height = _gui().size()
        return f"{width}x{height}"

    def _do_click(self, x: int, y: int, button: str = "left") -> str:
        # x, y are in the pixel space of the most recently shown screenshot, which may
        # have been downscaled from the real screen -- convert back before clicking.
        real_x = round(int(x) * self._screenshot_scale)
        real_y = round(int(y) * self._screenshot_scale)
        _gui().click(real_x, real_y, button=button)
        return f"Clicked ({real_x}, {real_y}) with {button} button"

    def _do_type_text(self, text: str, interval: float = 0.01) -> str:
        _gui().write(text, interval=max(0, min(float(interval), 0.2)))
        return f"Typed {len(text)} characters"

    def _do_hotkey(self, keys: list[str]) -> str:
        if not keys:
            raise ToolError("keys cannot be empty")
        _gui().hotkey(*keys)
        return "Pressed " + "+".join(keys)

    def _do_wait(self, seconds: float = 1) -> str:
        seconds = max(0, min(float(seconds), 10))
        time.sleep(seconds)
        return f"Waited {seconds:g} seconds"

    def _do_powershell(self, command: str, timeout: int = 30) -> str:
        normalized = " ".join(command.lower().split())
        if any(pattern in normalized for pattern in self.BLOCKED_PS):
            raise ToolError("Command blocked by safety policy")
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True,
            text=True,
            timeout=max(1, min(int(timeout), 60)),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            check=False,
        )
        output = (result.stdout + result.stderr).strip()
        return f"Exit code {result.returncode}\n{output[:8000]}"

    def _do_read_file(self, path: str, max_chars: int = 12000) -> str:
        return Path(path).expanduser().read_text(encoding="utf-8", errors="replace")[:max_chars]

    def _do_list_directory(self, path: str) -> str:
        root = Path(path).expanduser()
        return "\n".join(
            f"{'DIR ' if item.is_dir() else 'FILE'} {item.name}"
            for item in list(root.iterdir())[:200]
        )

    def capture_undo(self, name: str, arguments: dict[str, Any]) -> dict[str, Any] | None:
        """Snapshot what a mutating action is about to overwrite, if it can be undone."""
        if name != "write_file":
            return None
        path = arguments.get("path")
        if not path:
            return None
        target = Path(str(path)).expanduser()
        if not target.exists():
            return {"kind": "write_file", "path": str(target), "existed": False}
        try:
            previous = target.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None
        return {"kind": "write_file", "path": str(target), "existed": True, "previous_content": previous}

    @staticmethod
    def undo(entry: dict[str, Any]) -> str:
        if entry.get("kind") != "write_file":
            raise ToolError(f"Cannot undo action kind: {entry.get('kind')}")
        target = Path(entry["path"])
        if entry.get("existed"):
            target.write_text(entry.get("previous_content") or "", encoding="utf-8")
            return f"Restored previous contents of {target}"
        target.unlink(missing_ok=True)
        return f"Removed {target} (it did not exist before the write)"

    def _do_write_file(self, path: str, content: str) -> str:
        target = Path(path).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"Wrote {len(content)} characters to {target}"

    def _do_zoom_screenshot(self, x: int, y: int, radius: int = 150, scale: int = 3) -> str:
        image = _gui().screenshot()
        width, height = image.size
        radius = max(10, int(radius))
        requested_scale = max(1, min(int(scale), 8))
        left = max(0, int(x) - radius)
        top = max(0, int(y) - radius)
        right = min(width, int(x) + radius)
        bottom = min(height, int(y) + radius)
        if right <= left or bottom <= top:
            raise ToolError("Zoom region is empty; check x/y/radius against screen_info")
        cropped = image.crop((left, top, right, bottom))
        # Never let a large radius * scale combination produce an oversized image --
        # clamp to the same cap screenshot() uses, same reasoning: past that, a vision
        # model gets no extra detail, just a slower encode.
        max_scale = max(1, self.MAX_SCREENSHOT_DIMENSION // max(cropped.width, cropped.height))
        scale = min(requested_scale, max_scale)
        zoomed = cropped.resize((cropped.width * scale, cropped.height * scale), Image.LANCZOS)
        output = io.BytesIO()
        zoomed.save(output, format="PNG")
        self._pending_screenshot = output.getvalue()
        self._zoom_origin = (float(left), float(top), float(scale))
        return (
            f"Captured a {scale}x zoomed screenshot of the region around ({x}, {y}) "
            f"(screen pixels {left},{top} to {right},{bottom}). It will be shown as the "
            "screenshot on your next turn -- use click_zoomed with coordinates measured on "
            "that zoomed image to click precisely within this region."
        )

    def _do_click_zoomed(self, x: int, y: int, button: str = "left") -> str:
        if self._zoom_origin is None:
            raise ToolError("No zoomed screenshot is active; call zoom_screenshot first")
        left, top, scale = self._zoom_origin
        real_x = round(left + int(x) / scale)
        real_y = round(top + int(y) / scale)
        _gui().click(real_x, real_y, button=button)
        self._zoom_origin = None
        return f"Clicked ({real_x}, {real_y}) with {button} button (from zoomed region)"

    def _do_ui_tree(self, max_depth: int = 4, max_nodes: int = 200) -> str:
        from .accessibility import AccessibilityError, foreground_tree

        try:
            return foreground_tree(max_depth=int(max_depth), max_nodes=int(max_nodes))
        except AccessibilityError as exc:
            raise ToolError(str(exc)) from exc

    def _do_click_element(
        self,
        name: str | None = None,
        automation_id: str | None = None,
        control_type: str | None = None,
        button: str = "left",
    ) -> str:
        from .accessibility import AccessibilityError, find_element

        try:
            node = find_element(name=name, automation_id=automation_id, control_type=control_type)
        except AccessibilityError as exc:
            raise ToolError(str(exc)) from exc
        x, y = node.center
        _gui().click(x, y, button=button)
        return f"Clicked {node.describe()}"

    def _get_browser(self):
        if self._browser is None:
            from .browser import BrowserController

            self._browser = BrowserController()
        return self._browser

    def _do_browser_open(self, url: str) -> str:
        from .browser import BrowserError

        try:
            return self._get_browser().open(url)
        except BrowserError as exc:
            raise ToolError(str(exc)) from exc

    def _do_browser_snapshot(self, max_elements: int = 60) -> str:
        from .browser import BrowserError

        try:
            return self._get_browser().snapshot(max_elements=int(max_elements))
        except BrowserError as exc:
            raise ToolError(str(exc)) from exc

    def _do_browser_click(self, index: int) -> str:
        from .browser import BrowserError

        try:
            return self._get_browser().click(int(index))
        except BrowserError as exc:
            raise ToolError(str(exc)) from exc

    def _do_browser_type(self, index: int, text: str) -> str:
        from .browser import BrowserError

        try:
            return self._get_browser().fill(int(index), text)
        except BrowserError as exc:
            raise ToolError(str(exc)) from exc

    def _do_browser_close(self) -> str:
        if self._browser is None:
            return "No browser session was open"
        result = self._browser.close()
        self._browser = None
        return result

    def close(self) -> None:
        """Release any open browser session; call when a run finishes."""
        if self._browser is not None:
            self._browser.close()
            self._browser = None
