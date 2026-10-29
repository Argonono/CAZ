"""Keep the CareAtZero app awake and its data warm (run by .github/workflows/keep-awake.yml).

Streamlit Community Cloud puts an app to sleep after 12 hours with no visitors.
This opens the app in a real (headless) browser like a visitor would. If the app is
asleep, it clicks "Yes, get this app back up!" and waits until the Home screen loads.
Loading Home also refreshes the clinic lists in the app's 6-hour memory.

Usage:  python tools/keep_awake.py https://YOUR-APP.streamlit.app
"""
import sys
import time

from playwright.sync_api import sync_playwright

WAKE_TEXT = "get this app back up"
READY_TEXT = "Find free care"   # a button on the Home screen
TIMEOUT_S = 300                 # waking up can take a few minutes


def page_has(page, text):
    """True if any frame on the page shows this text (the app runs inside an iframe)."""
    for frame in page.frames:
        try:
            if frame.get_by_text(text, exact=False).count() > 0:
                return True
        except Exception:
            pass
    return False


def main(url):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 390, "height": 844})
        page.goto(url, wait_until="domcontentloaded", timeout=120_000)
        clicked = False
        start = time.time()
        while time.time() - start < TIMEOUT_S:
            if page_has(page, READY_TEXT):
                page.wait_for_timeout(15_000)   # let Home finish loading the clinic lists
                print(f"OK: app is awake ({'woke it up' if clicked else 'was already awake'}), {int(time.time() - start)} s")
                browser.close()
                return 0
            if not clicked:
                button = page.get_by_role("button", name=WAKE_TEXT, exact=False)
                if button.count() > 0:
                    print("App was asleep; clicking the wake-up button")
                    button.first.click()
                    clicked = True
            page.wait_for_timeout(5_000)
        page.screenshot(path="keep_awake_failed.png", full_page=True)
        browser.close()
        print(f"FAILED: the Home screen did not appear within {TIMEOUT_S} s (screenshot saved)")
        return 1


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    sys.exit(main(sys.argv[1]))
