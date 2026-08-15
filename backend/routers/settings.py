# intel-monitor/backend/routers/settings.py
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import get_current_user
from config import settings

router = APIRouter(prefix="/api/settings", tags=["settings"])

ENV_PATH = Path(__file__).parent.parent / ".env"

# Provider metadata: env key names, default base URL, test model, response parser type
PROVIDERS = {
    "minimax": {
        "key_env": "MINIMAX_API_KEY",
        "url_env": "MINIMAX_BASE_URL",
        "model_env": "MINIMAX_MODEL",
        "default_url": "https://api.minimaxi.com/v1/chat/completions",
        "default_model": "MiniMax-M2.7",
        "parser": "minimax",  # has base_resp
        "label": "MiniMax",
    },
    "deepseek": {
        "key_env": "DEEPSEEK_API_KEY",
        "url_env": "DEEPSEEK_BASE_URL",
        "model_env": "DEEPSEEK_MODEL",
        "default_url": "https://api.deepseek.com",
        "default_model": "deepseek-chat",
        "parser": "openai",  # OpenAI-compatible
        "label": "DeepSeek",
    },
    "mimo": {
        "key_env": "MIMO_API_KEY",
        "url_env": "MIMO_BASE_URL",
        "model_env": "MIMO_MODEL",
        "default_url": "https://api.xiaomimimo.com/v1",
        "default_model": "mimo-v2.5-pro",
        "parser": "openai",
        "auth_style": "api-key",  # uses api-key header instead of Bearer
        "label": "MiMo",
    },
    "lmstudio": {
        "key_env": "LMSTUDIO_API_KEY",
        "url_env": "LMSTUDIO_BASE_URL",
        "model_env": "LMSTUDIO_MODEL",
        "default_url": "http://localhost:1234/v1",
        "default_model": "minicpm-v-4.6-thinking",
        "parser": "openai",  # OpenAI-compatible local server
        "label": "LM Studio",
    },
    "firecrawl": {
        "key_env": "FIRECRAWL_API_KEY",
        "url_env": "FIRECRAWL_BASE_URL",
        "model_env": None,  # Firecrawl has no model concept
        "default_url": "https://api.firecrawl.dev/v2",
        "default_model": "",
        "parser": "firecrawl",  # special parser for service API key test
        "label": "Firecrawl",
    },
    "tavily": {
        "key_env": "TAVILY_API_KEY",
        "url_env": None,  # Tavily SDK doesn't use a separate URL
        "model_env": None,  # Tavily has no model concept
        "default_url": "https://api.tavily.com",
        "default_model": "",
        "parser": "tavily",  # special parser for service API key test
        "label": "Tavily",
    },
    "youtube": {
        "key_env": "YOUTUBE_API_KEY",
        "url_env": None,
        "model_env": None,
        "default_url": "https://www.googleapis.com/youtube/v3",
        "default_model": "",
        "parser": "youtube",  # custom test: hit videos.list with chart=mostPopular
        "label": "YouTube Data API v3",
    },
    "google_cse": {
        "key_env": "GOOGLE_CSE_ID",
        "url_env": None,
        "model_env": None,
        "default_url": "https://cse.google.com/cse",
        "default_model": "",
        "parser": "google_cse",  # validate CSE ID format + page loads
        "label": "Google CSE（Facebook 搜索）",
    },
}


class KeyRequest(BaseModel):
    api_key: str


class ModelNameRequest(BaseModel):
    model: str


class KeyResponse(BaseModel):
    has_key: bool
    masked_key: str = ""


class ProviderStatusResponse(BaseModel):
    provider: str
    label: str
    has_key: bool
    masked_key: str = ""
    base_url: str
    model: str


def _mask_key(key: str) -> str:
    if not key or len(key) < 8:
        return "****"
    return key[:4] + "*" * (len(key) - 8) + key[-4:]


def _read_env() -> dict[str, str]:
    env: dict[str, str] = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


def _write_env(env: dict[str, str]):
    lines = [f"{k}={v}" for k, v in env.items()]
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _get_provider_config(name: str) -> dict:
    """Get runtime config for a provider."""
    if name not in PROVIDERS:
        raise HTTPException(status_code=400, detail=f"不支持的提供商: {name}")
    p = PROVIDERS[name]
    return {
        "api_key": getattr(settings, p["key_env"], ""),
        "base_url": getattr(settings, p["url_env"], p["default_url"]) if p["url_env"] else p["default_url"],
        "model": getattr(settings, p["model_env"], p["default_model"]) if p["model_env"] else "",
        "parser": p["parser"],
        "auth_style": p.get("auth_style", "bearer"),
        "label": p["label"],
    }


async def _test_key(provider: str, api_key: str) -> dict:
    """Test an API key for any provider."""
    p = PROVIDERS[provider]
    cfg = _get_provider_config(provider)

    # Special handling for Firecrawl (service API, not LLM)
    if provider == "firecrawl":
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    f"{cfg['base_url'].rstrip('/')}/search",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "query": "test",
                        "limit": 1,
                        "sources": ["web"],
                    },
                )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("success"):
                    return {"success": True, "message": "Firecrawl API Key 验证成功"}
                return {"success": False, "message": f"Firecrawl 返回异常: {data.get('warning', 'unknown')}"}
            if resp.status_code == 401:
                return {"success": False, "message": "API Key 无效（认证失败）"}
            return {"success": False, "message": f"Firecrawl HTTP {resp.status_code}"}
        except httpx.TimeoutException:
            return {"success": False, "message": "连接超时，请检查网络"}
        except Exception as e:
            return {"success": False, "message": f"连接失败: {str(e)}"}

    # Special handling for Tavily (service API, not LLM)
    if provider == "tavily":
        try:
            from tavily import TavilyClient
            client = TavilyClient(api_key)
            result = client.search(query="test", search_depth="basic", max_results=1)
            if result and isinstance(result, dict) and "results" in result:
                return {"success": True, "message": f"Tavily API Key 验证成功（{len(result['results'])} 条结果）"}
            return {"success": False, "message": "Tavily 返回异常或无结果"}
        except Exception as e:
            msg = str(e)
            if "401" in msg or "unauthorized" in msg.lower():
                return {"success": False, "message": "API Key 无效（认证失败）"}
            return {"success": False, "message": f"连接失败: {msg}"}

    # Special handling for YouTube Data API v3
    if provider == "youtube":
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    "https://www.googleapis.com/youtube/v3/videos",
                    params={
                        "part": "snippet",
                        "chart": "mostPopular",
                        "maxResults": 1,
                        "key": api_key,
                    },
                )
            if resp.status_code == 200:
                data = resp.json()
                items = data.get("items", [])
                if items:
                    title = items[0].get("snippet", {}).get("title", "")
                    return {"success": True, "message": f"Youtube API Key 验证成功", "reply": title[:100]}
                return {"success": True, "message": "Youtube API Key 验证成功（热门视频返回为空）"}
            if resp.status_code == 403:
                body = resp.json() if resp.text else {}
                reason = body.get("error", {}).get("errors", [{}])[0].get("reason", "")
                if reason == "quotaExceeded":
                    return {"success": False, "message": "YouTube API 日配额已用尽"}
                return {"success": False, "message": "API Key 无效或被限制"}
            # 透出 YouTube 返回的具体错误信息，便于定位（如 regionCode 无效等）
            detail = ""
            if resp.text:
                try:
                    body = resp.json()
                    detail = body.get("error", {}).get("message", "")
                except Exception:
                    detail = resp.text[:200]
            return {"success": False, "message": f"YouTube API HTTP {resp.status_code}: {detail}"}
        except httpx.TimeoutException:
            return {"success": False, "message": "连接超时，请检查网络"}
        except Exception as e:
            return {"success": False, "message": f"连接失败: {str(e)}"}

    # Special handling for Google CSE — validate by loading the CSE page
    if provider == "google_cse":
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    f"https://cse.google.com/cse?cx={api_key}",
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
                )
            if resp.status_code == 200:
                # Check that the page contains a CSE search box (not an error page)
                text = resp.text
                if "gsc.tab" in text or "cse.google.com" in text:
                    return {"success": True, "message": "Google CSE ID 验证成功"}
                if "找不到" in text or "not found" in text.lower() or "invalid" in text.lower():
                    return {"success": False, "message": "CSE ID 无效（搜索引擎不存在）"}
                return {"success": True, "message": "Google CSE ID 验证成功（页面已加载）"}
            if resp.status_code == 400:
                return {"success": False, "message": "CSE ID 格式无效"}
            return {"success": False, "message": f"Google CSE HTTP {resp.status_code}"}
        except httpx.TimeoutException:
            return {"success": False, "message": "连接超时，请检查网络"}
        except Exception as e:
            return {"success": False, "message": f"连接失败: {str(e)}"}

    base_url = cfg["base_url"]
    model = cfg["model"]

    # For OpenAI-compatible providers, endpoint is /chat/completions
    if cfg["parser"] == "openai":
        url = f"{base_url.rstrip('/')}/chat/completions"
    else:
        url = base_url  # MiniMax URL already includes the path

    # Build auth header based on provider's auth style
    auth_style = cfg.get("auth_style", "bearer")
    if auth_style == "api-key":
        headers = {"api-key": api_key, "Content-Type": "application/json"}
    else:
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(url, headers=headers,
                json={
                    "model": model,
                    "messages": [
                        {"role": "user", "content": "你好，请回复'连接成功'"},
                    ],
                    "max_tokens": 30,
                },
            )

        data = resp.json()

        # MiniMax-specific: check base_resp
        if cfg["parser"] == "minimax":
            base_resp = data.get("base_resp", {})
            status_code = base_resp.get("status_code", 0)
            status_msg = base_resp.get("status_msg", "")
            if status_code == 1008:
                return {"success": False, "message": "账户余额不足，请先在 MiniMax 平台充值"}
            if status_code in (1002, 1003):
                return {"success": False, "message": "API Key 无效（认证失败）"}
            if status_code != 0:
                return {"success": False, "message": f"API 错误: {status_msg}"}

        # OpenAI-compatible: check for error field
        if cfg["parser"] == "openai":
            err = data.get("error")
            if err:
                msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
                return {"success": False, "message": f"API 错误: {msg}"}

        # Extract reply from choices
        choices = data.get("choices")
        if choices and len(choices) > 0:
            reply = choices[0].get("message", {}).get("content", "")
            return {"success": True, "message": f"{cfg['label']} API Key 验证成功", "reply": reply.strip()}

        if resp.status_code == 200:
            return {"success": True, "message": f"{cfg['label']} API Key 验证成功"}

        return {"success": False, "message": f"未知响应: HTTP {resp.status_code}"}

    except httpx.TimeoutException:
        return {"success": False, "message": "连接超时，请检查网络"}
    except Exception as e:
        return {"success": False, "message": f"连接失败: {str(e)}"}


# --- Model name ---

@router.put("/{provider}/model")
async def set_provider_model(provider: str, req: ModelNameRequest, user=Depends(get_current_user)):
    p = PROVIDERS.get(provider)
    if not p:
        raise HTTPException(status_code=404, detail=f"不支持的提供商: {provider}")
    if p["model_env"] is None:
        raise HTTPException(status_code=400, detail=f"{p['label']} 不支持修改模型名")
    model = req.model.strip()
    if not model:
        raise HTTPException(status_code=400, detail="模型名不能为空")
    env = _read_env()
    env[p["model_env"]] = model
    _write_env(env)
    setattr(settings, p["model_env"], model)
    return {"message": f"{p['label']} 模型名已更新", "model": model}


# --- Prompt management ---

DEFAULT_SUMMARIZE_POSTS_PROMPT = (
    "你是一个情报分析助手。请对以下社交媒体账号今日发布的内容进行简洁总结。"
    "总结应包括：主要内容主题、发布数量、互动情况概述。"
    "如果包含图片，请分析图片内容并将视觉信息融入总结（如图片展示的产品、场景、情绪等）。"
    "直接输出总结内容，不要输出思考过程。"
    "使用中文回复，控制在300字以内。"
)

DEFAULT_SUMMARIZE_WEBSITE_PROMPT = (
    "你是一个情报分析助手。请对以下网站的最新内容进行简洁总结。"
    "总结应包括：主要内容、关键信息点。"
    "使用中文回复，控制在200字以内。"
)


DEFAULT_INTELLIGENCE_REPORT_PROMPT = (
    "你是一位精通公安情报业务的情报分析专家，具备20年公安国保/政保工作经验"
    "和深厚的专业情报编报能力。你对宗教领域战略情报有深入研究，擅长从海量"
    "开源信息中提取关键情报、关联碎片化线索、识别风险隐患。\n\n"
    "情报编报要求：\n"
    "1. 使用规范、严谨的公安情报语言，避免空泛套话\n"
    "2. 所有论断必须建立在具体事实和数据之上，标注信息来源\n"
    "3. 风险研判要具体、有深度，不泛泛而谈\n"
    "4. 对策建议要务实、可操作，有针对性\n"
    "5. 章节结构逻辑清晰，层层递进"
)


class PromptsResponse(BaseModel):
    summarize_posts: str
    summarize_website: str
    summarize_posts_default: str
    summarize_website_default: str
    intelligence_report: str
    intelligence_report_default: str


class PromptsRequest(BaseModel):
    summarize_posts: str | None = None
    summarize_website: str | None = None
    intelligence_report: str | None = None


@router.get("/prompts", response_model=PromptsResponse)
async def get_prompts(user=Depends(get_current_user)):
    return PromptsResponse(
        summarize_posts=getattr(settings, 'SUMMARIZE_POSTS_PROMPT', DEFAULT_SUMMARIZE_POSTS_PROMPT),
        summarize_website=getattr(settings, 'SUMMARIZE_WEBSITE_PROMPT', DEFAULT_SUMMARIZE_WEBSITE_PROMPT),
        summarize_posts_default=DEFAULT_SUMMARIZE_POSTS_PROMPT,
        summarize_website_default=DEFAULT_SUMMARIZE_WEBSITE_PROMPT,
        intelligence_report=getattr(settings, 'INTELLIGENCE_REPORT_PROMPT', DEFAULT_INTELLIGENCE_REPORT_PROMPT),
        intelligence_report_default=DEFAULT_INTELLIGENCE_REPORT_PROMPT,
    )


@router.put("/prompts")
async def set_prompts(req: PromptsRequest, user=Depends(get_current_user)):
    updates = {}
    if req.summarize_posts is not None:
        if not req.summarize_posts.strip():
            raise HTTPException(status_code=400, detail="贴文分析提示词不能为空")
        updates["SUMMARIZE_POSTS_PROMPT"] = req.summarize_posts.strip()
    if req.summarize_website is not None:
        if not req.summarize_website.strip():
            raise HTTPException(status_code=400, detail="网站分析提示词不能为空")
        updates["SUMMARIZE_WEBSITE_PROMPT"] = req.summarize_website.strip()
    if req.intelligence_report is not None:
        if not req.intelligence_report.strip():
            raise HTTPException(status_code=400, detail="情报报告提示词不能为空")
        updates["INTELLIGENCE_REPORT_PROMPT"] = req.intelligence_report.strip()
    if not updates:
        raise HTTPException(status_code=400, detail="至少需要提供一个提示词")

    env = _read_env()
    for k, v in updates.items():
        env[k] = v
        setattr(settings, k, v)
    _write_env(env)
    return {"message": "提示词已保存", "updated": list(updates.keys())}


# --- Generic provider endpoints ---

@router.get("/{provider}", response_model=ProviderStatusResponse)
async def get_provider_key(provider: str, user=Depends(get_current_user)):
    p = PROVIDERS.get(provider)
    if not p:
        raise HTTPException(status_code=404, detail=f"不支持的提供商: {provider}")
    key = getattr(settings, p["key_env"], "")
    return ProviderStatusResponse(
        provider=provider,
        label=p["label"],
        has_key=bool(key),
        masked_key=_mask_key(key) if key else "",
        base_url=getattr(settings, p["url_env"], p["default_url"]) if p["url_env"] else p["default_url"],
        model=getattr(settings, p["model_env"], p["default_model"]) if p["model_env"] else "",
    )


@router.post("/{provider}")
async def save_provider_key(provider: str, req: KeyRequest, user=Depends(get_current_user)):
    p = PROVIDERS.get(provider)
    if not p:
        raise HTTPException(status_code=404, detail=f"不支持的提供商: {provider}")

    api_key = req.api_key.strip()
    if not api_key:
        raise HTTPException(status_code=400, detail="API Key 不能为空")

    env = _read_env()
    env[p["key_env"]] = api_key
    _write_env(env)
    setattr(settings, p["key_env"], api_key)

    return {"message": f"{p['label']} API Key 已保存", "masked_key": _mask_key(api_key)}


@router.post("/{provider}/test")
async def test_provider_key(provider: str, req: KeyRequest, user=Depends(get_current_user)):
    if provider not in PROVIDERS:
        raise HTTPException(status_code=404, detail=f"不支持的提供商: {provider}")
    api_key = req.api_key.strip()
    if not api_key:
        raise HTTPException(status_code=400, detail="API Key 不能为空")
    return await _test_key(provider, api_key)


@router.post("/{provider}/test-saved")
async def test_saved_provider_key(provider: str, user=Depends(get_current_user)):
    if provider not in PROVIDERS:
        raise HTTPException(status_code=404, detail=f"不支持的提供商: {provider}")
    p = PROVIDERS[provider]
    api_key = getattr(settings, p["key_env"], "")
    if not api_key:
        raise HTTPException(status_code=400, detail="尚未配置 API Key")
    return await _test_key(provider, api_key)


# --- Active provider ---

class ActiveProviderRequest(BaseModel):
    provider: str


@router.get("/active/provider")
async def get_active_provider(user=Depends(get_current_user)):
    return {"provider": settings.AI_PROVIDER}


@router.post("/active/provider")
async def set_active_provider(req: ActiveProviderRequest, user=Depends(get_current_user)):
    if req.provider not in PROVIDERS:
        raise HTTPException(status_code=400, detail=f"不支持的提供商: {req.provider}")
    env = _read_env()
    env["AI_PROVIDER"] = req.provider
    _write_env(env)
    settings.AI_PROVIDER = req.provider
    return {"message": f"已切换到 {PROVIDERS[req.provider]['label']}", "provider": req.provider}
