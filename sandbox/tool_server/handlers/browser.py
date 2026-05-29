import asyncio
from typing import Optional
from playwright.async_api import async_playwright, Browser, Page

# Module-level browser instance — shared across calls within one container session
_playwright = None
_browser: Optional[Browser] = None
_page: Optional[Page] = None


async def _get_page() -> Page:
    global _playwright, _browser, _page
    if _browser is None:
        _playwright = await async_playwright().start()
        _browser = await _playwright.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
    if _page is None or _page.is_closed():
        context = await _browser.new_context()
        _page = await context.new_page()
    return _page


MAX_TEXT = 50_000


async def handle(action: str, params: dict) -> dict:
    page = await _get_page()

    if action == "navigate":
        await page.goto(params["url"], wait_until="domcontentloaded", timeout=30_000)
        return {"title": await page.title(), "url": page.url}

    elif action == "click":
        await page.click(params["selector"], timeout=10_000)
        return {"success": True}

    elif action == "fill":
        await page.fill(params["selector"], params["value"], timeout=10_000)
        return {"success": True}

    elif action == "extract_text":
        selector = params.get("selector")
        if selector:
            text = await page.inner_text(selector)
        else:
            text = await page.inner_text("body")
        truncated = len(text) > MAX_TEXT
        return {"text": text[:MAX_TEXT], "truncated": truncated}

    elif action == "screenshot":
        import base64
        data = await page.screenshot(type="png")
        return {"image_base64": base64.b64encode(data).decode(), "mime_type": "image/png"}

    elif action == "find_links":
        pattern = params.get("filter_pattern", "")
        links = await page.eval_on_selector_all(
            "a[href]",
            "els => els.map(e => ({text: e.innerText.trim(), url: e.href}))",
        )
        if pattern:
            import re
            links = [lnk for lnk in links if re.search(pattern, lnk["url"])]
        return {"links": links[:100]}

    elif action == "wait_for_selector":
        timeout_ms = params.get("timeout_ms", 5_000)
        try:
            await page.wait_for_selector(params["selector"], timeout=timeout_ms)
            return {"found": True}
        except Exception:
            return {"found": False}

    elif action == "scroll":
        direction = params.get("direction", "down")
        pixels = params.get("pixels", 500)
        delta = pixels if direction == "down" else -pixels
        await page.mouse.wheel(0, delta)
        return {"success": True}

    raise ValueError(f"Unknown browser action: {action}")
