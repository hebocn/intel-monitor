# intel-monitor/backend/scripts/init_telegram.py
"""
Initialize Telegram login session for @kuai search crawler.

Opens a headed Chrome window pointed at Telegram Web.
Scan the QR code with your phone, then close the window.
The session (cookies + localStorage) persists in backend/data/telegram_profile/
and is reused by the sentiment search crawler.

Usage:
    cd backend
    python scripts/init_telegram.py
"""
import asyncio
import os
import sys
from pathlib import Path

# Add backend to path so we can import from crawlers
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


async def main():
    from playwright.async_api import async_playwright

    profile_dir = os.environ.get(
        "TELEGRAM_PROFILE_DIR",
        str(Path(__file__).resolve().parents[2] / "data" / "telegram_profile"),
    )
    Path(profile_dir).mkdir(parents=True, exist_ok=True)

    # Set stdout to UTF-8 so emoji work on Windows
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

    async with async_playwright() as p:
        print("启动浏览器...")
        browser = await p.chromium.launch_persistent_context(
            user_data_dir=profile_dir,
            headless=False,  # VISIBLE so you can scan QR
            args=["--no-sandbox"],
            viewport={"width": 1280, "height": 900},
        )
        page = browser.pages[0] if browser.pages else await browser.new_page()

        print("打开 Telegram Web...")
        await page.goto("https://web.telegram.org/k/", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(2)

        # Check if already logged in
        content = await page.text_content("body") or ""
        if "Log in by QR Code" not in content and "Log in to Telegram by QR Code" not in content:
            print("[OK] Already logged in. No QR scan needed.")
            print(f"   Session saved at: {profile_dir}")
        else:
            print()
            print("[ACTION] Scan the QR code on the page with your phone's Telegram app...")
            print("   After login, wait a few seconds for session to save, then close the browser window.")
            print(f"   Session will be saved to: {profile_dir}")
            print()

            # Wait for user to close the browser window
            try:
                while True:
                    try:
                        if page.is_closed() or not browser.pages:
                            break
                    except Exception:
                        break
                    await asyncio.sleep(2)
            except KeyboardInterrupt:
                pass

        await browser.close()
        print("Browser closed. Session saved. [OK]")


if __name__ == "__main__":
    asyncio.run(main())
