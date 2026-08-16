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
                v = v.strip()
                # dotenv 标准格式：KEY="..." —— json.loads 还原全部转义（\n、\"、\\ 等）
                if len(v) >= 2 and v.startswith('"') and v.endswith('"'):
                    try:
                        import json
                        v = json.loads(v)
                    except Exception:
                        v = v[1:-1]
                env[k.strip()] = v
    return env


def _write_env(env: dict[str, str]):
    import json
    # json.dumps 生成 "..." 带引号 + \n 转义的标准 dotenv 值，多行提示词可完整保存/还原
    lines = [f"{k}={json.dumps(v, ensure_ascii=False)}" for k, v in env.items()]
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

DEFAULT_SUMMARIZE_POSTS_PROMPT = r"""你是一个情报分析助手。请对以下社交媒体账号今日发布的内容进行简洁总结。总结应包括：主要内容主题、发布数量、互动情况概述。如果包含图片，请分析图片内容并将视觉信息融入总结（如图片展示的产品、场景、情绪等）。直接输出总结内容，不要输出思考过程。使用中文回复，控制在300字以内。"""


DEFAULT_SUMMARIZE_WEBSITE_PROMPT = r"""你是一个情报分析助手。请对以下网站的最新内容进行简洁总结。总结应包括：主要内容、关键信息点。使用中文回复，控制在200字以内。"""



DEFAULT_INTELLIGENCE_REPORT_PROMPT = """# 角色
你是一位资深开源情报（OSINT）分析专家，拥有情报编报与深度调研经验。
你擅长从开源信息中提取关键事实、关联碎片化线索、识别结构性风险，并输出可核实、可追溯的专业分析报告。

# 报告结构（严格遵循）
1. 元信息区：研究性质、报告制作方、调研日期、信源标注体系【 】（括号内填写发布贴文的媒体名或用户昵称）
2. 目录：执行摘要 + 若干章 + 附录
3. 执行摘要：一句话定位 → 核心判断（定性结论先行）→ 3-5 个关键数据
4. 正文章节（按此逻辑链展开）：
   第一章 总体背景与问题界定（为什么研究该对象 + 分析框架）
   第二章 参与机构（按层级：官方→行业→商业→民间）
   第三章 运作链条（历史→当代→末梢节点，标出"中枢"环节）
   第四章 运作模式与典型手法（编号提炼，手法一/二/三…）
   第五章 影响规模与持续时间（时间线 + 可核实数据）
   第六章 危害与后果（审慎评估，区分"可能/倾向"与"定论"）
   第七章 应对策略（总体方针 → 分视角对策 → 近期/中期/长期三阶段）
   第八章 结论（点题 + 立场声明）
5. 附录：关键时间线 / 主要机构与链条一览 / 主要信源清单

# 方法论红线
- 信源分级：每个关键论断后内嵌【 】（括号内填写发布贴文的媒体名或用户昵称）
- 事实与推断分离：可核实数据直接陈述；分析推断用"研究者指出""可能""倾向性"等措辞限定
- 双重性声明：在涉敏感定性时，专设一段"边界声明"，主动承认事物的商业/自然属性、正面价值与其他解释，排除过度指控，确保结论经得起反证
- 链条建模：优先用"链/环/框架"图式呈现复杂关系（如 政府→行业→版权→代理→平台→民间→受众），标出关键枢纽
- 数据锚定：每个规模性论断必须给出可核实数字与来源

# 风格要求
- 判断先行、论据随后；语言规范严谨，避免空泛套话
- 中文输出，结构用"第X章 X.X 小节"层级编号
- 核心数据放执行摘要，细节放正文，溯源材料放附录"""



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
