# intel-monitor/backend/services/tavily_service.py
"""Tavily 搜索 API 封装 — AI-powered web search with raw content extraction。"""

import asyncio
import logging
from config import settings

logger = logging.getLogger(__name__)


class TavilyError(Exception):
    pass


class TavilyService:
    """Tavily API 异步客户端。通过 asyncio.to_thread 封装同步 SDK。"""

    MAX_RETRIES: int = 2
    RETRY_BACKOFF: float = 1.5  # seconds

    @property
    def api_key(self) -> str:
        return settings.TAVILY_API_KEY

    def _search_sync(self, query: str, max_results: int = 10, search_depth: str = "advanced",
                     include_raw_content: bool = True, include_domains: list[str] | None = None,
                     topic: str = "general") -> dict:
        """Synchronous search call (runs in thread)."""
        from tavily import TavilyClient
        from tavily import InvalidAPIKeyError, UsageLimitExceededError, TavilyKeylessLimitError
        client = TavilyClient(self.api_key)
        try:
            kwargs = {
                "query": query[:400],
                "search_depth": search_depth,
                "max_results": min(max_results, 20),
                "include_raw_content": include_raw_content,
                "include_answer": False,
            }
            if include_domains:
                kwargs["include_domains"] = include_domains[:300]
            if topic != "general":
                kwargs["topic"] = topic

            result = client.search(**kwargs)
            return result
        except InvalidAPIKeyError:
            raise TavilyError("Invalid API Key")
        except UsageLimitExceededError as e:
            raise TavilyError(f"Tavily usage limit exceeded: {e}")
        except TavilyKeylessLimitError:
            raise TavilyError("Tavily keyless limit exceeded")
        except Exception as e:
            raise TavilyError(str(e) or type(e).__name__)

    async def search(
        self,
        query: str,
        max_results: int = 10,
        search_depth: str = "advanced",
        include_raw_content: bool = True,
        include_domains: list[str] | None = None,
        topic: str = "general",
    ) -> list[dict]:
        """搜索 web 并返回 AI 精选的结果（含原始内容）。

        Returns:
            list of result dicts: {title, url, content, raw_content, score}
        """
        if not self.api_key:
            raise TavilyError("TAVILY_API_KEY is not configured")

        logger.info(f"Tavily search: '{query[:80]}...' (depth={search_depth}, limit={max_results})")

        for attempt in range(self.MAX_RETRIES):
            try:
                data = await asyncio.to_thread(
                    self._search_sync, query, max_results, search_depth,
                    include_raw_content, include_domains, topic
                )
                results = []
                for r in data.get("results", []):
                    results.append({
                        "title": r.get("title", ""),
                        "url": r.get("url", ""),
                        "description": r.get("content", "")[:300],
                        "markdown": r.get("raw_content", "") or r.get("content", ""),
                        "score": r.get("score", 0.0),
                    })
                logger.info(f"Tavily search returned {len(results)} results for '{query[:60]}'")
                return results
            except TavilyError as e:
                logger.warning(f"Tavily error on attempt {attempt+1}: {e}")
                if "Invalid API Key" in str(e) or "unauthorized" in str(e).lower():
                    raise
                if attempt < self.MAX_RETRIES - 1:
                    await asyncio.sleep(self.RETRY_BACKOFF * (2 ** attempt))
            except Exception as e:
                logger.warning(f"Tavily unexpected error on attempt {attempt+1}: {e}")
                if attempt < self.MAX_RETRIES - 1:
                    await asyncio.sleep(self.RETRY_BACKOFF)

        logger.warning(f"Tavily search failed after {self.MAX_RETRIES} retries for '{query[:60]}'")
        return []


# Singleton
tavily = TavilyService()
