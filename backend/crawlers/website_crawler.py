# intel-monitor/backend/crawlers/website_crawler.py
"""Website crawler with Scrapling + OpenCLI(Markdown) + AutoCLI + Playwright fallback chain."""
import asyncio
import json
import logging
import re
import subprocess

from crawlers.base import CrawlResult, PostData

logger = logging.getLogger(__name__)

# OpenCLI extract 返回 JSON 中的 Markdown 内容字段
_IMG_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
_BLOCK_SIGNALS = ["ERR_CONNECTION_CLOSED", "ERR_CONNECTION_REFUSED", "ERR_NAME_NOT_RESOLVED",
                  "无法访问此网站", "意外终止了连接", "此网站无法提供安全连接", "ERR_SSL"]


class WebsiteCrawler:
    """Crawl arbitrary website content. Fallback chain:
    1. Scrapling (stealth browser, Cloudflare Turnstile solver)
    2. OpenCLI browser extract (real Chrome, 网页转 Markdown, 复用登录态)
    3. AutoCLI read (real Chrome via extension)
    4. Playwright (headless, basic sites)
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

    async def crawl(self, url: str, css_selector: str | None = None,
                    timeout: float = 180) -> CrawlResult:
        """Crawl website with a hard total timeout (default 180s).

        任何单链卡死都不会永久阻塞——超时后整体返回失败，由上层标记任务状态。
        """
        try:
            return await asyncio.wait_for(
                self._crawl_with_fallback(url, css_selector), timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning(f"[website_crawler] 爬取总超时 ({timeout}s): {url}")
            return CrawlResult(success=False, error_message=f"爬取总超时({timeout}s)")
        except Exception as e:
            logger.exception(f"[website_crawler] 爬取异常: {url}")
            return CrawlResult(success=False, error_message=f"爬取异常: {e}")

    async def _crawl_with_fallback(self, url: str, css_selector: str | None) -> CrawlResult:
        # Chain 1: Scrapling
        try:
            result = await self._crawl_scrapling(url, css_selector)
            if result.success:
                result.method = "scrapling"
                return result
            logger.warning(f"Scrapling failed: {result.error_message}, 降级 OpenCLI")
        except Exception as e:
            logger.warning(f"Scrapling exception: {e}, 降级 OpenCLI")

        # Chain 2: OpenCLI browser extract (网页转 Markdown)
        try:
            result = await self._crawl_opencli_md(url)
            if result.success:
                result.method = "opencli_markdown"
                return result
            logger.warning(f"OpenCLI Markdown failed: {result.error_message}, 降级 AutoCLI")
        except Exception as e:
            logger.warning(f"OpenCLI exception: {e}, 降级 AutoCLI")

        # Chain 3: AutoCLI read (real Chrome via extension)
        try:
            result = await self._crawl_autocli(url)
            if result.success:
                result.method = "autocli"
                return result
            logger.warning(f"AutoCLI read failed: {result.error_message}, 降级 Playwright")
        except Exception as e:
            logger.warning(f"AutoCLI read exception: {e}, 降级 Playwright")

        # Chain 4: Playwright
        result = await self._crawl_playwright(url, css_selector)
        if result.success:
            result.method = "playwright"
        return result

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

    # ── OpenCLI browser extract (网页转 Markdown) ─────────────────────────

    @staticmethod
    def _find_opencli() -> str | None:
        """定位 opencli 可执行文件（后端进程 PATH 可能不含用户目录，需显式探测）。"""
        import os, shutil
        candidates = [
            # 优先 npm 版 (有实际 CLI 输出), App 版 exe 需要 shim 参数
            r"C:\Users\Gary\AppData\Roaming\npm\opencli.cmd",
            r"C:\Users\Gary\AppData\Roaming\npm\opencli",
            r"C:\Users\Administrator\AppData\Roaming\npm\opencli.cmd",
            r"C:\Users\Gary\AppData\Local\OpenCLIApp\opencli-app.exe",
        ]
        for c in candidates:
            if os.path.exists(c):
                return c
        return shutil.which("opencli")

    async def _crawl_opencli_md(self, url: str, max_chars: int = 20000) -> CrawlResult:
        """用 OpenCLI 真实 Chrome 打开网页并提取 Markdown（复用登录态，结构完整）。

        命令: opencli browser default open <url> → opencli browser default extract
        返回: Markdown 文本 + 从 Markdown 提取的图片 URL（补全相对路径）
        """
        loop = asyncio.get_running_loop()
        opencli_bin = self._find_opencli()
        if not opencli_bin:
            return CrawlResult(success=False, error_message="OpenCLI 未安装")

        def _run(*args: str, timeout: int) -> subprocess.CompletedProcess:
            # .cmd 批处理必须 shell=True; 参数用双引号包裹防止空格问题
            cmd = f'"{opencli_bin}" ' + " ".join(f'"{a}"' for a in args)
            return subprocess.run(cmd, capture_output=True, timeout=timeout, shell=True)

        # 1. 打开页面
        try:
            proc = await loop.run_in_executor(None, lambda: _run(
                "browser", "default", "open", url, timeout=45))
        except subprocess.TimeoutExpired:
            return CrawlResult(success=False, error_message="OpenCLI open 超时")
        except Exception as e:
            return CrawlResult(success=False, error_message=f"OpenCLI open 失败: {e}")

        if proc.returncode != 0:
            return CrawlResult(success=False, error_message=f"OpenCLI open 失败: {proc.stderr.decode('utf-8', errors='replace')[:200]}")

        # 2. 提取 Markdown（分块直到拿满内容或没有更多）
        chunks: list[str] = []
        start = 0
        next_start: int | None = 0
        total = 0
        try:
            while next_start is not None and total < max_chars:
                cmd = ["browser", "default", "extract", "--start", str(start)]
                proc = await loop.run_in_executor(None, lambda: _run(*cmd, timeout=60))
                if proc.returncode != 0:
                    if not chunks:
                        return CrawlResult(success=False, error_message="OpenCLI extract 失败")
                    break
                try:
                    data = json.loads(proc.stdout.decode("utf-8", errors="replace"))
                except json.JSONDecodeError:
                    return CrawlResult(success=False, error_message="OpenCLI extract 返回非 JSON")
                content = data.get("content") or ""
                chunks.append(content)
                total += len(content)
                next_start = data.get("next_start_char")
                if next_start is None or next_start <= start:
                    break
                start = next_start
                if len(chunks) >= 10:  # 防止死循环
                    break
        except subprocess.TimeoutExpired:
            if not chunks:
                return CrawlResult(success=False, error_message="OpenCLI extract 超时")
        except Exception as e:
            if not chunks:
                return CrawlResult(success=False, error_message=f"OpenCLI extract 异常: {e}")

        markdown = "\n\n".join(chunks)
        if not markdown.strip():
            return CrawlResult(success=False, error_message="OpenCLI 返回空内容")

        # 检测错误页（网站无法访问等）
        head = markdown[:500]
        if any(sig in head for sig in _BLOCK_SIGNALS):
            return CrawlResult(success=False, error_message=f"网站无法访问: {head[:150]}")

        # 3. 从 Markdown 提取图片 URL（补全相对路径）
        base = url.rstrip("/")
        images: list[str] = []
        for m in _IMG_RE.finditer(markdown):
            img = m.group(1).strip()
            # 去掉 base64 内嵌图
            if img.startswith("data:"):
                continue
            # 去掉 Markdown 标题语法残留 (如 "home-master-1")
            img = re.split(r'\s+"', img)[0]
            if img.startswith("//"):
                img = "https:" + img
            elif img.startswith("/"):
                img = base + img
            elif not img.startswith("http"):
                continue
            if img not in images:
                images.append(img)

        content = markdown[:max_chars]

        return CrawlResult(
            posts=[PostData(url=url, title=url, content=content,
                            images=self._filter_images(images))],
            raw_html=content[:10000],
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
