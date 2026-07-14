"""Test Toutiao user page with network_idle + longer wait."""
import sys, io, asyncio, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

async def main():
    from scrapling import StealthyFetcher
    url = "https://www.toutiao.com/c/user/token/MS4wLjABAAAAvRBgIucCPu9wOfA4c0h9md6c9N2dZ1rLpyUPfgMXHks/?source=profile"

    extracted = {}
    def page_action(page):
        import time
        time.sleep(8)
        for _ in range(5):
            page.evaluate("window.scrollBy(0, 1000)")
            time.sleep(2)
        time.sleep(3)
        extracted["final_url"] = page.url
        extracted["title"] = page.title()
        extracted["body"] = page.evaluate("() => document.body ? document.body.innerText.substring(0, 4000) : ''")

        # Find all article links
        articles = page.evaluate("""() => {
            var links = document.querySelectorAll('a[href*="/article/"]');
            var items = [];
            var seen = {};
            for (var i = 0; i < links.length; i++) {
                var h = links[i].href || '';
                if (seen[h]) continue;
                seen[h] = true;
                if (h.indexOf('/article/') < 0) continue;
                var t = (links[i].innerText || '').trim();
                if (t.length < 5) continue;
                items.push({text: t.substring(0, 120), href: h.substring(0, 200)});
            }
            return JSON.stringify(items);
        }""")
        extracted["articles"] = articles
        return None

    print(f"Testing with network_idle + longer scroll...")
    resp = await asyncio.to_thread(
        StealthyFetcher.fetch,
        url=url, headless=True, network_idle=True, wait=8000,
        timeout=120000, locale="zh-CN", real_chrome=True,
        page_action=page_action,
    )
    print(f"Final URL: {extracted.get('final_url','')}")
    print(f"Title: {extracted.get('title','')}")
    body = extracted.get('body','')
    print(f"Body len: {len(body)}")
    # Check for content vs loading failure
    if "加载失败" in body:
        print("⚠️ Still showing '加载失败' — async content didn't load")
    print(f"Body (first 800): {body[:800]}")

    articles = json.loads(extracted.get('articles','[]'))
    print(f"\nArticle links: {len(articles)}")
    for a in articles[:10]:
        print(f"  [{a['text'][:80]}]")

asyncio.run(main())
