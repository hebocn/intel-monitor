"""Dump DOM of Toutiao user page (with real_chrome) to find post elements."""
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
        # Dump: find all elements with meaningful text that look like posts
        result = page.evaluate("""() => {
            var posts = [];
            // Find ALL a tags with text
            var allA = document.querySelectorAll('a');
            for (var i = 0; i < allA.length; i++) {
                var a = allA[i];
                var t = (a.innerText || '').trim();
                var h = a.href || '';
                var cls = (a.className || '').substring(0, 60);
                if (t.length > 5 && t.length < 200) {
                    // Get parent chain info
                    var p = a.parentElement;
                    var pTag = p ? p.tagName : '';
                    var pCls = p ? (p.className || '').substring(0, 80) : '';
                    var pp = p ? p.parentElement : null;
                    var ppTag = pp ? pp.tagName : '';
                    var ppCls = pp ? (pp.className || '').substring(0, 80) : '';
                    posts.push({
                        text: t.substring(0, 100),
                        url: h.substring(0, 150),
                        cls: cls,
                        pTag: pTag, pCls: pCls,
                        ppTag: ppTag, ppCls: ppCls
                    });
                }
            }
            return JSON.stringify(posts.slice(0, 30));
        }""")
        extracted["all_links"] = result
        extracted["body"] = page.evaluate("() => document.body ? document.body.innerText.substring(0, 2000) : ''")
        return None

    print("Dumping user page DOM...")
    resp = await asyncio.to_thread(
        StealthyFetcher.fetch,
        url=url, headless=True, wait=5000, timeout=60000,
        locale="zh-CN", real_chrome=True,
        page_action=page_action,
    )
    print(f"Title: {extracted.get('title','')}")

    links = json.loads(extracted.get('all_links','[]'))
    print(f"\nAll meaningful links ({len(links)}):")
    for l in links[:20]:
        print(f"  [{l['text'][:60]}]")
        print(f"    a.cls={l['cls']}")
        print(f"    parent: <{l['pTag']}> {l['pCls']}")
        print(f"    grandparent: <{l['ppTag']}> {l['ppCls']}")
        print()

    # Also dump body to see content
    body = extracted.get('body','')
    print(f"Body (first 600): {body[:600]}")

asyncio.run(main())
