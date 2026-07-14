"""
Verify ToutiaoScraplingCrawler end-to-end.
"""
import sys, io, asyncio, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from crawlers.toutiao_scrapling_crawler import ToutiaoScraplingCrawler


async def main():
    crawler = ToutiaoScraplingCrawler()

    print("=" * 60)
    print("ToutiaoScraplingCrawler — End-to-End Test")
    print("=" * 60)

    result = await crawler.search_by_keyword("人工智能", limit=10)

    print(f"\nsuccess: {result.success}")
    print(f"error:   {result.error_message}")
    print(f"posts:   {len(result.posts)}")

    for i, p in enumerate(result.posts[:10]):
        print(f"\n  [{i+1}] {p.title[:100]}")
        print(f"       url:       {p.url[:100]}")
        print(f"       author:    {p.author_name}")
        print(f"       views:     {p.views}")
        print(f"       published: {p.published_at}")
        if p.content:
            print(f"       content:   {p.content[:120]}")

    print("\n" + "=" * 60)
    if result.success and result.posts:
        print("✅ PASS — ToutiaoScraplingCrawler working")
    else:
        print("❌ FAIL — check error message above")

asyncio.run(main())
