"""Headless screenshots of the live app for the report (Playwright).

Writes report/figures/app_forecast.png. Needs the `report` dependency group
(`uv sync --group report`) and a Chromium download (`uv run playwright
install chromium`); `make report` skips this script gracefully when
Playwright is unavailable.
"""

from __future__ import annotations

import sys
from pathlib import Path

URL = "https://gb-carbon-forecast-go.streamlit.app/"
OUT = Path("report/figures/app_forecast.png")


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright not installed; skipping app screenshots")
        return 0

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 1400})
        page.goto(URL, wait_until="networkidle", timeout=120_000)
        page.wait_for_timeout(15_000)  # let Streamlit hydrate and charts render
        page.screenshot(path=str(OUT), full_page=False)
        browser.close()
    print(f"screenshot -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
