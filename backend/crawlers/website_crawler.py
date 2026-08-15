# intel-monitor/backend/crawlers/website_crawler.py
"""Website crawler with Scrapling + AutoCLI + Playwright fallback chain."""
import asyncio
import logging
import subprocess

from crawlers.base import CrawlResult, PostData

logger = logging.getLogger(__name__)


class WebsiteCrawler:
    """Crawl arbitrary website content. Fallback chain:
    1. Scrapling (stealth browser, Cloudflare Turnstile solver)
    2. AutoCLI read (real Chrome via extension, bypasses WAF fingerprinting)
    3. Playwright (headless, basic sites)
    """

    @staticmethod
    def _filter_images(images: list[str], max_images: int = 5) -> list[str]:
        """去重 + 过滤装饰图/logo/图标/空白像素, 只保留有分析价值的内容图."""
        if not images:
            return []
        seen: set[str] = set()
        result: list[str] = []
        # 常见装饰图文件名/路径特征 (logo/icon/banner/背景/空白)
        deco_patterns = (
            "logo", "icon", "banner", "sprite", "avatar", "default",
            "placeholder", "spacer", "blank", "transparent", "loading",
            "title.gif", "top.jpg", "index.gif", "11.jpg", "1x1", "pixel",
            ".svg", "favicon", "logo_", "_logo", "logo.", "weixin", "qrcode",
        )
        for u in images:
            if not u or u in seen:
                continue
            low = u.lower()
            if any(p in low for p in deco_patterns):
                continue
            # 只保留常见图片格式
            if not any(ext in low for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp")):
                continue
            seen.add(u)
            result.append(u)
            if len(result) >= max_images:
                break
        return result

    async def crawl(self, url: str, css_selector: str | None = None) -> CrawlResult:
        # Chain 1: Scrapling
        try:
            result = await self._crawl_scrapling(url, css_selector)
            if result.success:
                return result
            logger.warning(f"Scrapling failed: {result.error_message}, 降级 AutoCLI")
        except Exception as e:
            logger.warning(f"Scrapling exception: {e}, 降级 AutoCLI")

        # Chain 2: AutoCLI read (real Chrome via extension)
        try:
            result = await self._crawl_autocli(url)
            if result.success:
                return result
            logger.warning(f"AutoCLI read failed: {result.error_message}, 降级 Playwright")
        except Exception as e:
            logger.warning(f"AutoCLI read exception: {e}, 降级 Playwright")

        # Chain 3: Playwright
        return await self._crawl_playwright(url, css_selector)

    # ── Scrapling (stealth) ──────────────────────────────────────────────

    async def _crawl_scrapling(self, url: str, css_selector: str | None = None) -> CrawlResult:
        from scrapling import StealthyFetcher

        extracted = {}

        def page_action(page):
            import time
            time.sleep(5)
            for _ in range(3):
                page.evaluate("window.scrollBy(0, 800)")
                time.sleep(1)
            time.sleep(2)
            extracted["url"] = page.url
            extracted["title"] = page.title()
            if css_selector:
                extracted["body"] = page.evaluate(
                    f"() => document.querySelector('{css_selector}') ? "
                    f"document.querySelector('{css_selector}').innerText : ''"
                )
                extracted["images"] = page.evaluate(
                    f"() => Array.from(document.querySelectorAll('{css_selector} img')).map(i => i.src || i.getAttribute('data-src')).filter(u => u && u.startsWith('http'))"
                )
            else:
                extracted["body"] = page.evaluate(
                    "() => document.body ? document.body.innerText.substring(0, 10000) : ''"
                )
                extracted["images"] = page.evaluate(
                    "() => Array.from(document.querySelectorAll('article img, .content img, .article img, .entry-content img, main img, img')).map(i => i.src || i.getAttribute('data-src')).filter(u => u && u.startsWith('http')).slice(0, 8)"
                )
            return None

        await asyncio.to_thread(
            StealthyFetcher.fetch,
            url=url,
            headless=True,
            wait=5000,
            solve_cloudflare=True,
            disable_resources=True,
            block_ads=True,
            timeout=90000,
            locale="zh-CN",
            page_action=page_action,
            real_chrome=False,
        )

        body = (extracted.get("body") or "").strip()
        title = extracted.get("title") or url

        if not body:
            return CrawlResult(success=False, error_message="页面内容为空")

        block_signals = ["安全验证", "验证码", "captcha", "Cloudflare", "请启用JavaScript", "请稍候"]
        if any(s in body[:500] for s in block_signals):
            return CrawlResult(success=False, error_message=f"被反爬拦截: {body[:200]}")

        return CrawlResult(
            posts=[PostData(url=extracted.get("url", url), title=title, content=body[:5000],
                            images=self._filter_images(extracted.get("images") or []))],
            raw_html=body[:10000],
            success=True,
        )

    # ── AutoCLI read (real Chrome) ────────────────────────────────────────

    async def _crawl_autocli(self, url: str) -> CrawlResult:
        """Use autocli read which reuses the real Chrome browser via extension.
        Bypasses Cloudflare WAF fingerprinting that blocks headless browsers."""
        loop = asyncio.get_running_loop()
        try:
            proc = await loop.run_in_executor(
                None,
                lambda: subprocess.run(
                    ["autocli", "read", url, "--format", "text"],
                    capture_output=True, timeout=90,
                )
            )
        except subprocess.TimeoutExpired:
            return CrawlResult(success=False, error_message="AutoCLI read 超时")
        except FileNotFoundError:
            return CrawlResult(success=False, error_message="AutoCLI 未安装")
        except Exception as e:
            return CrawlResult(success=False, error_message=f"AutoCLI read 失败: {e}")

        if proc.returncode != 0:
            stderr = proc.stderr.decode("utf-8", errors="replace")
            return CrawlResult(success=False, error_message=f"AutoCLI read 失败: {stderr[:200]}")

        text = proc.stdout.decode("utf-8", errors="replace").strip()
        if not text:
            return CrawlResult(success=False, error_message="AutoCLI read 返回空内容")

        # Parse title from first line (if it looks like a title)
        lines = text.split("\n")
        title = lines[0].strip() if lines else url

        return CrawlResult(
            posts=[PostData(url=url, title=title, content=text[:5000])],
            raw_html=text[:10000],
            success=True,
        )

    # ── Playwright fallback ─────────────────────────────────────────────

    async def _crawl_playwright(self, url: str, css_selector: str | None = None) -> CrawlResult:
        from crawlers.base import PlaywrightCrawler

        class _PW(PlaywrightCrawler):
            async def get_hot_comments(self, post_url: str):
                return []

        pw = _PW()
        try:
            await pw.init_browser()
            await pw.page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await pw.page.wait_for_timeout(5000)

            if css_selector:
                content = await pw.page.inner_text(css_selector)
                images = await pw.page.eval_on_selector_all(
                    f"{css_selector} img",
                    "els => els.map(i => i.src || i.getAttribute('data-src')).filter(u => u && u.startsWith('http'))",
                )
            else:
                content = await pw.page.inner_text("body")
                images = await pw.page.eval_on_selector_all(
                    "article img, .content img, .article img, .entry-content img, main img, img",
                    "els => els.map(i => i.src || i.getAttribute('data-src')).filter(u => u && u.startsWith('http')).slice(0, 8)",
                )

            title = await pw.page.title()

            return CrawlResult(
                posts=[PostData(url=url, title=title, content=content[:5000], images=self._filter_images(images))],
                raw_html=content[:10000],
                success=True,
            )
        except Exception as e:
            return CrawlResult(success=False, error_message=str(e))
        finally:
            await pw.close()
