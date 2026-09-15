from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Any


class AccessibilityError(RuntimeError):
    pass


@dataclass(frozen=True)
class Node:
    control_type: str
    name: str
    automation_id: str
    x: int
    y: int
    width: int
    height: int

    @property
    def center(self) -> tuple[int, int]:
        return self.x + self.width // 2, self.y + self.height // 2

    def describe(self) -> str:
        cx, cy = self.center
        parts = [self.control_type or "Element"]
        if self.name:
            parts.append(f'"{self.name}"')
        if self.automation_id:
            parts.append(f"id={self.automation_id}")
        parts.append(f"at ({cx}, {cy})")
        return " ".join(parts)


def _rect(element: Any) -> tuple[int, int, int, int] | None:
    rect = getattr(element, "BoundingRectangle", None)
    if not rect:
        return None
    left = getattr(rect, "left", None)
    top = getattr(rect, "top", None)
    if left is None or top is None:
        return None
    width = getattr(rect, "width", None)
    height = getattr(rect, "height", None)
    if width is None:
        width = getattr(rect, "right", left) - left
    if height is None:
        height = getattr(rect, "bottom", top) - top
    if width <= 0 or height <= 0:
        return None
    return int(left), int(top), int(width), int(height)


def walk(element: Any, max_depth: int = 4, max_nodes: int = 200) -> list[Node]:
    """Flatten an accessibility element tree into a bounded list of named, visible nodes.

    Works against any duck-typed object exposing Name, ControlTypeName, AutomationId,
    BoundingRectangle, and GetChildren() -- this keeps the traversal testable without a
    real Windows UI Automation backend.
    """
    nodes: list[Node] = []
    budget = [max(0, int(max_nodes))]
    _walk(element, max(0, int(max_depth)), 0, budget, nodes)
    return nodes


def _walk(element: Any, max_depth: int, depth: int, budget: list[int], nodes: list[Node]) -> None:
    if budget[0] <= 0:
        return
    name = str(getattr(element, "Name", "") or "").strip()
    automation_id = str(getattr(element, "AutomationId", "") or "").strip()
    control_type = str(
        getattr(element, "ControlTypeName", "") or getattr(element, "ControlType", "") or ""
    ).strip()
    rect = _rect(element)
    if rect and (name or automation_id):
        x, y, width, height = rect
        nodes.append(Node(control_type or "Element", name, automation_id, x, y, width, height))
        budget[0] -= 1
    if depth >= max_depth:
        return
    get_children = getattr(element, "GetChildren", None)
    children = get_children() if callable(get_children) else []
    for child in children:
        if budget[0] <= 0:
            return
        _walk(child, max_depth, depth + 1, budget, nodes)


def format_tree(nodes: list[Node]) -> str:
    if not nodes:
        return "No named UI elements found in the foreground window."
    return "\n".join(f"[{i}] {node.describe()}" for i, node in enumerate(nodes))


def search(
    nodes: list[Node],
    name: str | None = None,
    automation_id: str | None = None,
    control_type: str | None = None,
) -> Node | None:
    for node in nodes:
        if automation_id and node.automation_id != automation_id:
            continue
        if name and name.lower() not in node.name.lower():
            continue
        if control_type and control_type.lower() != node.control_type.lower():
            continue
        return node
    return None


def _foreground_root() -> Any:
    if sys.platform != "win32":
        raise AccessibilityError("UI Automation is only available on Windows")
    try:
        import uiautomation as auto
    except ImportError as exc:
        raise AccessibilityError(
            "The 'uiautomation' package is required. Install it with: pip install uiautomation"
        ) from exc
    root = auto.GetForegroundControl()
    if root is None:
        raise AccessibilityError("Could not find a foreground window")
    return root


def foreground_tree(max_depth: int = 4, max_nodes: int = 200) -> str:
    root = _foreground_root()
    return format_tree(walk(root, max_depth=max_depth, max_nodes=max_nodes))


def find_element(
    name: str | None = None,
    automation_id: str | None = None,
    control_type: str | None = None,
    max_depth: int = 6,
    max_nodes: int = 500,
) -> Node:
    if not name and not automation_id and not control_type:
        raise AccessibilityError("Provide at least one of name, automation_id, or control_type")
    root = _foreground_root()
    nodes = walk(root, max_depth=max_depth, max_nodes=max_nodes)
    node = search(nodes, name=name, automation_id=automation_id, control_type=control_type)
    if node is None:
        raise AccessibilityError("No matching UI element found in the foreground window")
    return node
