"""Visit the deployed app so the host does not put it to sleep.

Streamlit Community Cloud suspends apps that receive no browser visits,
regardless of repository activity, and shows a wake-up page instead. A real
headless visit (plus a click on the wake button when present) counts as
traffic. Exits non-zero when the app has not rendered within the budget, so
the workflow run goes red and the failure is visible.

Run: uv run python scripts/keepalive_visit.py
"""

from __future__ import annotations

import re
import sys
import time

from playwright.sync_api import sync_playwright

APP_URL = "https://gb-carbon-forecast-go.streamlit.app/"
TITLE_TOKEN = "GB Carbon Intensity Forecast"
BUDGET_S = 240


def main() -> int:
    deadline = time.monotonic() + BUDGET_S
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(APP_URL, wait_until="domcontentloaded", timeout=60_000)
        clicked = False
        while time.monotonic() < deadline:
            if TITLE_TOKEN.lower() in (page.title() or "").lower():
                print(f"app awake: title={page.title()!r}, wake_click={clicked}")
                browser.close()
                return 0
            if not clicked:
                button = page.get_by_role(
                    "button", name=re.compile("app back up", re.I)
                )
                if button.count():
                    button.first.click()
                    clicked = True
                    print("clicked the wake-up button")
            time.sleep(5)
        print(
            f"app did not render within {BUDGET_S}s; last title={page.title()!r}",
            file=sys.stderr,
        )
        browser.close()
        return 1


if __name__ == "__main__":
    sys.exit(main())
