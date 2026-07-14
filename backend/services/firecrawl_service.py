# intel-monitor/backend/services/firecrawl_service.py
"""Firecrawl API 封装 — search + scrape，用于战略情报报告的公开 web 搜索。"""

import asyncio
import logging
import httpx
from config import settings

logger = logging.getLogger(__name__)


class FirecrawlError(Exception):
    pass


class FirecrawlService:
    """Firecrawl v2 API 异步客户端。"""

    BASE: str = settings.FIRECRAWL_BASE_URL or "https://api.firecrawl.dev/v2"
    MAX_RETRIES: int = 3
    RETRY_BACKOFF: float = 2.0  # seconds

    @property
    def api_key(self) -> str:
        return settings.FIRECRAWL_API_KEY

    @property
    def _auth_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def _post(self, path: str, payload: dict, timeout: int = 60000) -> dict:
        """POST to Firecrawl with retries."""
        url = f"{self.BASE}{path}"
        last_error = None
        for attempt in range(self.MAX_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=timeout / 1000) as client:
                    resp = await client.post(url, json=payload, headers=self._auth_headers)
                    if resp.status_code == 429:
                        retry_after = int(resp.headers.get("Retry-After", self.RETRY_BACKOFF * (2 ** attempt)))
                        logger.warning(f"Firecrawl 429, retry after {retry_after}s (attempt {attempt+1})")
                        await asyncio.sleep(retry_after)
                        continue
                    resp.raise_for_status()
                    data = resp.json()
                    if not data.get("success"):
                        raise FirecrawlError(data.get("error", data.get("warning", "Unknown error")))
                    return data
            except httpx.HTTPStatusError as e:
                last_error = e
                logger.warning(f"Firecrawl HTTP {e.response.status_code} on attempt {attempt+1}: {path}")
                if attempt < self.MAX_RETRIES - 1:
                    await asyncio.sleep(self.RETRY_BACKOFF * (2 ** attempt))
            except Exception as e:
                last_error = e
                logger.warning(f"Firecrawl error on attempt {attempt+1}: {e}")
                if attempt < self.MAX_RETRIES - 1:
                    await asyncio.sleep(self.RETRY_BACKOFF)
        raise FirecrawlError(f"Firecrawl request failed after {self.MAX_RETRIES} retries: {last_error}")

    async def search(
        self,
        query: str,
        limit: int = 10,
        sources: list[str] | None = None,
        tbs: str | None = None,
        scrape_formats: list[str] | None = None,
        only_main_content: bool = True,
        max_age_ms: int = 604800000,  # 7 days
    ) -> list[dict]:
        """搜索 web 并自动抓取每条结果的正文内容。

        Returns:
            list of result dicts: {title, description, url, markdown, metadata, ...}
        """
        if not self.api_key:
            raise FirecrawlError("FIRECRAWL_API_KEY is not configured")

        if scrape_formats is None:
            scrape_formats = ["markdown"]

        payload = {
            "query": query[:500],
            "limit": min(limit, 100),
            "sources": sources or ["web"],
            "scrapeOptions": {
                "onlyMainContent": only_main_content,
                "formats": scrape_formats,
                "maxAge": max_age_ms,
            },
        }
        if tbs:
            payload["tbs"] = tbs

        logger.info(f"Firecrawl search: '{query[:80]}...' (limit={limit})")
        data = await self._post("/search", payload, timeout=90000)

        # Flatten results from all sources
        results = []
        web_hits = data.get("data", {}).get("web", [])
        for hit in web_hits:
            results.append({
                "title": hit.get("title", ""),
                "description": hit.get("description", ""),
                "url": hit.get("url", ""),
                "markdown": hit.get("markdown", ""),
                "metadata": hit.get("metadata", {}),
            })
        # news results
        news_hits = data.get("data", {}).get("news", [])
        for hit in news_hits:
            results.append({
                "title": hit.get("title", ""),
                "description": hit.get("snippet", ""),
                "url": hit.get("url", ""),
                "markdown": hit.get("markdown", ""),
                "date": hit.get("date", ""),
                "source_type": "news",
            })

        logger.info(f"Firecrawl search returned {len(results)} results for '{query[:60]}'")
        return results

    async def scrape(
        self,
        url: str,
        formats: list[str] | None = None,
        only_main_content: bool = True,
        timeout: int = 30000,
    ) -> dict | None:
        """深度抓取单个 URL，返回正文 markdown。

        Returns:
            dict: {title, markdown, url, metadata, ...} or None on failure
        """
        if not self.api_key:
            raise FirecrawlError("FIRECRAWL_API_KEY is not configured")

        if formats is None:
            formats = ["markdown"]

        payload = {
            "url": url,
            "formats": formats,
            "onlyMainContent": only_main_content,
            "timeout": timeout,
        }

        try:
            logger.info(f"Firecrawl scrape: {url[:100]}")
            data = await self._post("/scrape", payload, timeout=35000)
            result = data.get("data", {})
            return {
                "title": result.get("metadata", {}).get("title", ""),
                "url": result.get("metadata", {}).get("sourceURL", url),
                "markdown": result.get("markdown", ""),
                "metadata": result.get("metadata", {}),
            }
        except FirecrawlError:
            logger.warning(f"Firecrawl scrape failed for {url[:100]}")
            return None
        except Exception as e:
            logger.warning(f"Firecrawl scrape error for {url[:100]}: {e}")
            return None


# Singleton
firecrawl = FirecrawlService()
