"""Quick test: what happens when we visit the specific Toutiao user URL."""
import sys, io, asyncio
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

async def main():
    from scrapling import StealthyFetcher
    url = "https://www.toutiao.com/c/user/token/MS4wLjABAAAAvRBgIucCPu9wOfA4c0h9md6c9N2dZ1rLpyUPfgMXHks/?source=profile"

    extracted = {}
    def page_action(page):
        import time
        time.sleep(3)
        extracted["final_url"] = page.url
        extracted["title"] = page.title()
        body = page.evaluate("() => document.body ? document.body.innerText.substring(0, 1500) : ''")
        extracted["body"] = body
        # Check for login wall
        extracted["has_login"] = "登录" in body[:500]
        return None

    print(f"Requesting: {url}")
    resp = await asyncio.to_thread(
        StealthyFetcher.fetch,
        url=url, headless=True, wait=4000, timeout=30000, locale="zh-CN",
        page_action=page_action,
    )
    print(f"Final URL: {extracted.get('final_url', 'n/a')}")
    print(f"Title: {extracted.get('title', 'n/a')}")
    print(f"Has login wall: {extracted.get('has_login')}")
    print(f"Body (first 500): {extracted.get('body', '')[:500]}")

asyncio.run(main())
