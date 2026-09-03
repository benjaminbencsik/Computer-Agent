from __future__ import annotations

import io
import subprocess
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, ClassVar

ApprovalCallback = Callable[[str, dict[str, Any]], bool]


def _gui():
    import pyautogui

    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.15
    return pyautogui


class ToolError(RuntimeError):
    pass


class ToolRunner:
    MUTATING: ClassVar[set[str]] = {"click", "type_text", "hotkey", "powershell", "write_file"}
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

    @staticmethod
    def screenshot() -> bytes:
        image = _gui().screenshot()
        output = io.BytesIO()
        image.save(output, format="PNG")
        return output.getvalue()

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
Use coordinates from the latest screenshot. Prefer keyboard navigation when reliable."""

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
        _gui().click(int(x), int(y), button=button)
        return f"Clicked ({x}, {y}) with {button} button"

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

    def _do_write_file(self, path: str, content: str) -> str:
        target = Path(path).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"Wrote {len(content)} characters to {target}"
