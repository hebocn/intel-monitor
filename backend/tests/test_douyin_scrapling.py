"""
Verification test for DouyinScraplingCrawler prototype.

Tests:
  1. StealthyFetcher — does it hit Douyin without being blocked?
  2. Adaptive CSS selectors — can we extract posts?
  3. Search — does search page load with results?
  4. Time extraction — can we parse relative times?

Usage:
  cd intel-monitor/backend
  python tests/test_douyin_scrapling.py
"""
import asyncio
import sys
import os

# Allow running from backend/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from crawlers.douyin_scrapling_crawler import DouyinScraplingCrawler


def test_crawl():
    """Test: fetch posts from a known Douyin user page."""
    print("\n" + "=" * 60)
    print("TEST 1: crawl() — fetch user page")
    print("=" * 60)

    crawler = DouyinScraplingCrawler()
    # Use Douyin official account as test target
    result = asyncio.run(crawler.crawl("https://www.douyin.com/user/MS4wLjABAAAAI8A3PKtv1LEGLBvlQhW5nYRYzAhhIaFVQJhvj_WnP60"))

    print(f"  success: {result.success}")
    print(f"  error:   {result.error_message}")
    print(f"  posts:   {len(result.posts)}")

    for i, p in enumerate(result.posts[:5]):
        print(f"\n  Post {i+1}:")
        print(f"    title:        {p.title[:80] if p.title else '(empty)'}")
        print(f"    url:          {p.url[:80] if p.url else '(empty)'}")
        print(f"    published_at: {p.published_at}")

    return result.success, len(result.posts)


def test_search():
    """Test: search for a keyword on Douyin."""
    print("\n" + "=" * 60)
    print("TEST 2: search_by_keyword()")
    print("=" * 60)

    crawler = DouyinScraplingCrawler()
    result = asyncio.run(crawler.search_by_keyword("人工智能", limit=10))

    print(f"  success: {result.success}")
    print(f"  error:   {result.error_message}")
    print(f"  posts:   {len(result.posts)}")

    for i, p in enumerate(result.posts[:5]):
        print(f"\n  Post {i+1}:")
        print(f"    title:        {p.title[:80] if p.title else '(empty)'}")
        print(f"    url:          {p.url[:80] if p.url else '(empty)'}")
        print(f"    published_at: {p.published_at}")

    return result.success, len(result.posts)


def test_raw_page():
    """Test: raw StealthyFetcher — does Douyin block us?"""
    print("\n" + "=" * 60)
    print("TEST 3: raw StealthyFetcher — anti-bot check")
    print("=" * 60)

    def _run():
        from scrapling import StealthyFetcher

        resp = StealthyFetcher.fetch(
            url="https://www.douyin.com/",
            headless=True,
            wait=5000,
            solve_cloudflare=True,
            timeout=45000,
            locale="zh-CN",
        )
        body = resp.text[:3000] if resp.text else ""
        title = ""
        for t in resp.css("title"):
            if t.text:
                title = t.text
                break

        return title, body

    title, body = asyncio.run(asyncio.to_thread(_run))
    print(f"  <title>:  {title}")
    print(f"  body len: {len(body)}")

    blocked_signals = ["验证码", "captcha", "滑块验证", "请完成安全验证", "请先登录"]
    blocked = any(s in body[:800].lower() for s in blocked_signals)
    print(f"  blocked:  {blocked}")
    if not blocked and body:
        # Show first non-empty visible text
        import re
        clean = re.sub(r'<[^>]+>', ' ', body[:2000])
        clean = re.sub(r'\s+', ' ', clean).strip()
        print(f"  sample:   {clean[:300]}")
    return not blocked


def main():
    print("DouyinScraplingCrawler — Verification Test Suite")
    print("=" * 60)

    results = {}

    # Test 3 first: raw anti-bot check (cheapest failure)
    results['raw_access'] = test_raw_page()
    results['crawl'] = test_crawl()
    results['search'] = test_search()

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for name, (success, count) in results.items():
        if isinstance(count, bool):
            status = "✅ PASS" if success else "❌ FAIL"
            print(f"  {name:20s} {status}")
        else:
            status = f"✅ {count} posts" if success else f"❌ FAIL"
            print(f"  {name:20s} {status}")

    print("\nNext steps:")
    print("  - If raw_access PASS: StealthyFetcher works, anti-bot bypass confirmed")
    print("  - If crawl PASS: adaptive selectors work on user pages")
    print("  - If search PASS: search + SPA rendering works")
    print("  - If any FAIL: check anti-bot strategy, try real_chrome=True")
    print("  - If crawl/search PASS: register as CrawlerEntry in Router")


if __name__ == "__main__":
    main()
