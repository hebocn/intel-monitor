"""Test: ToutiaoScraplingCrawler on homepage feed with TreeWalker pairing."""
import sys, io, asyncio, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from crawlers.toutiao_scrapling_crawler import ToutiaoScraplingCrawler

async def main():
    c = ToutiaoScraplingCrawler()
    r = await c.crawl("https://www.toutiao.com/")
    print(f"success={r.success} posts={len(r.posts)} error={r.error_message}")
    for i, p in enumerate(r.posts[:8]):
        ts = str(p.published_at) if p.published_at else "None"
        print(f"[{i+1}] author={p.author_name or '(none)'} time={ts}")
        print(f"    {p.title[:80]}")

asyncio.run(main())
