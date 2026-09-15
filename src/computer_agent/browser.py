from __future__ import annotations

from typing import Any


class BrowserError(RuntimeError):
    pass


class BrowserController:
    """Lazily launches a Chromium browser via Playwright and grounds actions in
    the DOM (elements tagged with a stable index attribute) instead of screen
    coordinates, so browser automation survives layout and window changes."""

    _MARKER_ATTR = "data-ca-index"
    _SELECTOR = "a, button, input, textarea, select, [role=button], [role=link], [onclick]"

    def __init__(self, headless: bool = False, executable_path: str | None = None):
        self.headless = headless
        self.executable_path = executable_path
        self._playwright = None
        self._browser = None
        self._page = None

    def _ensure_page(self) -> Any:
        if self._page is not None:
            return self._page
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise BrowserError(
                "The 'playwright' package is required. Install it with: "
                "pip install computer-agent[browser] && playwright install chromium"
            ) from exc
        self._playwright = sync_playwright().start()
        try:
            self._browser = self._playwright.chromium.launch(
                headless=self.headless, executable_path=self.executable_path
            )
        except Exception as exc:
            self._playwright.stop()
            self._playwright = None
            raise BrowserError(f"Could not launch Chromium: {exc}") from exc
        self._page = self._browser.new_page()
        return self._page

    def open(self, url: str) -> str:
        page = self._ensure_page()
        if "://" not in url:
            url = "https://" + url
        try:
            page.goto(url, wait_until="domcontentloaded")
        except Exception as exc:
            raise BrowserError(f"Could not open {url}: {exc}") from exc
        return f"Opened {page.url}"

    def snapshot(self, max_elements: int = 60) -> str:
        page = self._ensure_page()
        page.eval_on_selector_all(
            f"[{self._MARKER_ATTR}]",
            f"nodes => nodes.forEach(n => n.removeAttribute('{self._MARKER_ATTR}'))",
        )
        elements = page.eval_on_selector_all(
            self._SELECTOR,
            """(nodes, args) => nodes.slice(0, args.max).map((el, i) => {
                el.setAttribute(args.attr, String(i));
                const text = (
                    el.innerText || el.value || el.placeholder ||
                    el.getAttribute('aria-label') || ''
                ).trim();
                return {
                    index: i,
                    tag: el.tagName.toLowerCase(),
                    role: el.getAttribute('role') || '',
                    text: text.slice(0, 60),
                };
            })""",
            {"max": max_elements, "attr": self._MARKER_ATTR},
        )
        if not elements:
            return "No interactive elements found on the page."
        lines = []
        for item in elements:
            label = f'"{item["text"]}"' if item["text"] else ""
            role = f" role={item['role']}" if item["role"] else ""
            lines.append(f"[{item['index']}] <{item['tag']}>{role} {label}".rstrip())
        return "\n".join(lines)

    def _locator(self, index: int):
        page = self._ensure_page()
        selector = f"[{self._MARKER_ATTR}='{int(index)}']"
        locator = page.locator(selector)
        if locator.count() == 0:
            raise BrowserError(f"No element at index {index}; call browser_snapshot again")
        return locator

    def click(self, index: int) -> str:
        self._locator(index).click()
        return f"Clicked element [{index}]"

    def fill(self, index: int, text: str) -> str:
        self._locator(index).fill(text)
        return f"Typed into element [{index}]"

    def close(self) -> str:
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()
        self._browser = None
        self._page = None
        self._playwright = None
        return "Closed browser"
