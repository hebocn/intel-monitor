"""Test Toutiao user page with real_chrome=True (user's logged-in Chrome)."""
import sys, io, asyncio, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

async def main():
    from scrapling import StealthyFetcher
    url = "https://www.toutiao.com/c/user/token/MS4wLjABAAAAvRBgIucCPu9wOfA4c0h9md6c9N2dZ1rLpyUPfgMXHks/?source=profile"

    extracted = {}
    def page_action(page):
        import time
        time.sleep(5)
        for _ in range(3):
            page.evaluate("window.scrollBy(0, 800)")
            time.sleep(1.5)
        extracted["final_url"] = page.url
        extracted["title"] = page.title()
        extracted["body"] = page.evaluate("() => document.body ? document.body.innerText.substring(0, 3000) : ''")

        # Try to find article links
        articles = page.evaluate("""() => {
            var links = document.querySelectorAll('a[href*="/article/"]');
            var items = [];
            for (var i = 0; i < Math.min(links.length, 10); i++) {
                items.push({
                    text: (links[i].innerText||'').trim().substring(0, 100),
                    href: (links[i].href||'').substring(0, 150)
                });
            }
            return JSON.stringify(items);
        }""")
        extracted["articles"] = articles
        return None

    print(f"Testing real_chrome=True on user page...")
    try:
        resp = await asyncio.to_thread(
            StealthyFetcher.fetch,
            url=url, headless=True, wait=5000, timeout=60000,
            locale="zh-CN", real_chrome=True,
            page_action=page_action,
        )
    except Exception as e:
        print(f"ERROR: {e}")
        return

    print(f"Final URL: {extracted.get('final_url','')}")
    print(f"Title: {extracted.get('title','')}")
    body = extracted.get('body','')
    print(f"Body len: {len(body)}")
    print(f"Body (first 600): {body[:600]}")

    # Check login wall
    has_login = "登录" in body[:500] and "立即登录" in body[:500]
    print(f"Login wall: {has_login}")

    articles = json.loads(extracted.get('articles','[]'))
    print(f"\nArticle links found: {len(articles)}")
    for a in articles[:5]:
        print(f"  [{a['text'][:80]}] -> {a['href']}")

asyncio.run(main())
