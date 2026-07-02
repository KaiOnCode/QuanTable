"""
Manual Playwright smoke check for the Phase 5 Streamlit backtest UI.

This lives under `test/streamlit/` for discoverability, but it is intentionally
not named `test_*.py` so regular pytest runs do not require a browser runtime.
"""

from playwright.sync_api import sync_playwright


def main() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto("http://127.0.0.1:8501")
        page.wait_for_load_state("networkidle")

        page.get_by_text("Backtest Mode", exact=True).click()
        page.wait_for_timeout(1000)

        body_text = page.locator("body").inner_text()
        required_text = [
            "Broker Backtest Start Date",
            "Broker Backtest End Date",
            "Initial Cash",
            "Commission Rate",
            "Slippage Rate",
        ]
        for text in required_text:
            assert text in body_text, f"missing UI text: {text}"

        page.screenshot(path="/tmp/streamlit_phase5_smoke.png", full_page=True)
        browser.close()


if __name__ == "__main__":
    main()
