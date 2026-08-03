# intel-monitor/backend/services/summarizer.py
import logging
import httpx
from config import settings
from crawlers.base import PostData, CommentData

logger = logging.getLogger(__name__)

# Provider config lookup
_PROVIDER_CONFIGS = {
    "minimax": {
        "key_env": "MINIMAX_API_KEY", "url_env": "MINIMAX_BASE_URL", "model_env": "MINIMAX_MODEL",
        "default_url": "https://api.minimaxi.com/v1/chat/completions", "parser": "minimax",
    },
    "deepseek": {
        "key_env": "DEEPSEEK_API_KEY", "url_env": "DEEPSEEK_BASE_URL", "model_env": "DEEPSEEK_MODEL",
        "default_url": "https://api.deepseek.com", "parser": "openai",
    },
    "mimo": {
        "key_env": "MIMO_API_KEY", "url_env": "MIMO_BASE_URL", "model_env": "MIMO_MODEL",
        "default_url": "https://api.xiaomimimo.com/v1", "parser": "openai", "auth_style": "api-key",
    },
}


class ContentSummarizer:
    def _get_active_config(self) -> tuple[str, str, str, str, str]:
        """Returns (api_key, api_url, model, parser, auth_style) for the active provider."""
        provider = settings.AI_PROVIDER
        cfg = _PROVIDER_CONFIGS.get(provider, _PROVIDER_CONFIGS["minimax"])
        api_key = getattr(settings, cfg["key_env"], "")
        base_url = getattr(settings, cfg["url_env"], cfg["default_url"])
        model = getattr(settings, cfg["model_env"], "")
        parser = cfg["parser"]
        auth_style = cfg.get("auth_style", "bearer")

        # For OpenAI-compatible providers, append /chat/completions
        if parser == "openai":
            api_url = f"{base_url.rstrip('/')}/chat/completions"
        else:
            api_url = base_url

        return api_key, api_url, model, parser, auth_style

    def _get_provider_config(self, provider: str) -> tuple[str, str, str, str, str]:
        """Get config for a specific provider. Returns (api_key, api_url, model, parser, auth_style)."""
        cfg = _PROVIDER_CONFIGS.get(provider, _PROVIDER_CONFIGS["minimax"])
        api_key = getattr(settings, cfg["key_env"], "")
        base_url = getattr(settings, cfg["url_env"], cfg["default_url"])
        model = getattr(settings, cfg["model_env"], "")
        parser = cfg["parser"]
        auth_style = cfg.get("auth_style", "bearer")

        if parser == "openai":
            api_url = f"{base_url.rstrip('/')}/chat/completions"
        else:
            api_url = base_url

        return api_key, api_url, model, parser, auth_style

    async def _call_provider(self, provider: str, api_key: str, api_url: str, model: str,
                              parser: str, auth_style: str, system_prompt: str,
                              user_prompt: str, images: list[str] | None = None) -> str:
        """Call a specific AI provider and return the response text."""
        if images:
            content = [{"type": "text", "text": user_prompt}]
            for url in images:
                content.append({"type": "image_url", "image_url": {"url": url}})
            user_message = {"role": "user", "content": content}
        else:
            user_message = {"role": "user", "content": user_prompt}

        if auth_style == "api-key":
            headers = {"api-key": api_key, "Content-Type": "application/json"}
        else:
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

        timeout = 120 if images else 60
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(api_url, headers=headers,
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        user_message,
                    ],
                    "temperature": 0.7,
                },
            )
            logger.info(f"[{provider}] HTTP {resp.status_code}, 耗时 {resp.elapsed.total_seconds():.1f}s")
            resp.raise_for_status()
            data = resp.json()

            # MiniMax-specific: check base_resp
            if parser == "minimax":
                base_resp = data.get("base_resp", {})
                if base_resp.get("status_code", 0) != 0:
                    msg = base_resp.get("status_msg", "API 返回错误")
                    logger.warning(f"[{provider}] 业务错误: {msg}")
                    raise Exception(msg)

            # OpenAI-compatible: check for error field
            if parser == "openai":
                err = data.get("error")
                if err:
                    msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
                    logger.warning(f"[{provider}] API 错误: {msg}")
                    raise Exception(msg)

            choices = data.get("choices")
            if not choices:
                raise Exception("API 未返回有效结果")
            result_text = choices[0]["message"]["content"]
            logger.info(f"[{provider}] 返回 {len(result_text)} 字符")

            # Detect content rejection in successful response (e.g. MiMo)
            if any(kw in result_text.lower() for kw in (
                "rejected because it was considered high risk",
                "content exists risk", "content_filter",
            )):
                logger.warning(f"[{provider}] 响应内容检测到拒绝: {result_text[:100]}")
                raise Exception(result_text[:200])

            return result_text

    async def _call_ai(self, system_prompt: str, user_prompt: str, images: list[str] | None = None,
                       _allow_fallback: bool = True) -> str:
        provider = settings.AI_PROVIDER
        api_key, api_url, model, parser, auth_style = self._get_provider_config(provider)
        mode = f"多模态({len(images)}张图片)" if images else "纯文本"
        logger.info(f"[{provider}] 请求模式: {mode}, 模型: {model}")

        try:
            return await self._call_provider(provider, api_key, api_url, model, parser, auth_style,
                                             system_prompt, user_prompt, images=images)
        except Exception as e:
            msg = str(e)
            # Content policy rejection — try fallback provider
            is_content_block = any(kw in msg.lower() for kw in (
                "content exists risk", "content_filter", "content_policy",
                "safety", "moderation", "inappropriate", "400 bad request",
            ))
            if is_content_block and _allow_fallback:
                # Try each configured fallback provider
                last_error = msg
                fallbacks = [p for p in ["minimax", "mimo"] if p != provider and getattr(settings, _PROVIDER_CONFIGS[p]["key_env"], "")]
                for fb in fallbacks:
                    fb_api_key, fb_api_url, fb_model, fb_parser, fb_auth_style = self._get_provider_config(fb)
                    if not fb_api_key:
                        continue
                    logger.warning(f"[{provider}] 内容安全拒绝, 降级到 {fb}")
                    try:
                        return await self._call_provider(fb, fb_api_key, fb_api_url, fb_model, fb_parser, fb_auth_style,
                                                         system_prompt, user_prompt, images=images)
                    except Exception as fb_err:
                        last_error = str(fb_err)
                        logger.warning(f"[{fb}] 降级也失败: {fb_err}")
                # All fallbacks exhausted — raise with content_block marker so callers can detect
                raise Exception(f"[content_block] 所有 AI 提供商均拒绝处理: {last_error}")
            raise

    async def summarize_posts(self, platform: str, account_name: str, posts: list[PostData]) -> str:
        if not posts:
            return "今日无新内容发布。"

        posts_text = "\n".join(
            f"- [{p.title or '无标题'}] {p.content[:200]} (点赞: {p.likes})"
            for p in posts
        )

        all_images = []
        for p in posts:
            all_images.extend(p.images)
        all_images = all_images[:10]

        system_prompt = settings.SUMMARIZE_POSTS_PROMPT
        user_prompt = f"平台: {platform}\n账号: {account_name}\n今日发布内容:\n{posts_text}"

        try:
            return await self._call_ai(system_prompt, user_prompt, images=all_images or None)
        except Exception as e:
            msg = str(e)
            if all_images:
                logger.warning(f"[{settings.AI_PROVIDER}] 多模态请求失败({e}), 回退纯文本模式")
                try:
                    return await self._call_ai(system_prompt, user_prompt)
                except Exception as e2:
                    msg2 = str(e2)
                    if any(kw in msg2.lower() for kw in ("[content_block]", "content exists risk", "content_filter", "high risk", "rejected")):
                        logger.warning(f"[summarizer] AI 全部拦截，输出原始贴文内容作为摘要")
                        return posts_text[:2000]
                    logger.error(f"[{settings.AI_PROVIDER}] 纯文本回退也失败: {e2}")
                    return f"总结生成失败: {msg2}"
            if any(kw in msg.lower() for kw in ("[content_block]", "content exists risk", "content_filter", "high risk", "rejected")):
                logger.warning(f"[summarizer] AI 全部拦截，输出原始贴文内容作为摘要")
                return posts_text[:2000]
            return f"总结生成失败: {msg}"

    async def summarize_website(self, site_name: str, content: str) -> str:
        if not content:
            return "今日无内容变化。"

        system_prompt = settings.SUMMARIZE_WEBSITE_PROMPT
        user_prompt = f"网站: {site_name}\n内容:\n{content[:5000]}"

        try:
            return await self._call_ai(system_prompt, user_prompt)
        except Exception as e:
            msg = str(e)
            # If all providers rejected due to content policy, output raw content as summary
            if any(kw in msg.lower() for kw in (
                "[content_block]", "content exists risk", "content_filter", "high risk", "rejected",
            )):
                logger.warning(f"[summarizer] AI 全部拦截，输出原始网页内容作为摘要")
                return content[:3000]
            return f"总结生成失败: {msg}"

    async def extract_hot_comments(
        self, all_comments: list[CommentData], max_count: int = 10,
        per_post_limit: int = 3,
    ) -> list[CommentData]:
        """挑选最热门的评论。

        热度分 = 点赞×1 + 回复×2（微博）或 点赞×1 + 转发×2（X）。
        每帖先截断（防单帖霸榜），合并后按热度分排前 2×max_count 候选，
        再交给 AI 从候选中精选 max_count 条（AI 可见完整互动指标）。
        """
        if not all_comments:
            return []

        def _heat(c: CommentData) -> int:
            return c.likes + max(c.reply_count, c.retweet_count) * 2

        # 每帖截断：按 post.url 分组，取每组热度最高的 per_post_limit 条
        by_post: dict[str, list[CommentData]] = {}
        for c in all_comments:
            by_post.setdefault(c.url, []).append(c)
        truncated = []
        for post_comments in by_post.values():
            post_comments.sort(key=_heat, reverse=True)
            truncated.extend(post_comments[:per_post_limit])

        sorted_comments = sorted(truncated, key=_heat, reverse=True)
        candidates = sorted_comments[:max_count * 2]

        if len(candidates) <= max_count:
            return candidates[:max_count]

        def _fmt(c: CommentData) -> str:
            if c.reply_count:
                extra = f"{c.reply_count}回复"
            elif c.retweet_count:
                extra = f"{c.retweet_count}转发"
            else:
                extra = ""
            return f"[{c.likes}赞{',' + extra if extra else ''}] {c.author}: {c.text[:100]}"

        comments_text = "\n".join(
            f"{i+1}. {_fmt(c)}" for i, c in enumerate(candidates)
        )

        system_prompt = (
            "从以下评论中选出最有价值、最热门的10条。"
            "按热度排序，返回编号列表，每行一个编号。"
            "只返回编号，如: 1,3,5,7,9,11,13,15,17,19"
        )

        try:
            result = await self._call_ai(system_prompt, comments_text)
            logger.info(f"[summarizer] AI 精选评论返回: {result[:200]!r} (候选 {len(candidates)} 条)")
            indices = [int(x.strip()) - 1 for x in result.replace("\n", ",").split(",") if x.strip().isdigit()]
            if not indices:
                return candidates[:max_count]
            return [candidates[i] for i in indices if 0 <= i < len(candidates)][:max_count]
        except Exception:
            return candidates[:max_count]


summarizer = ContentSummarizer()
