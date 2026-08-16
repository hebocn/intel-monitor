# intel-monitor/backend/config.py
import secrets
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", env_file=".env", env_file_encoding="utf-8")
    # Active AI provider: minimax / deepseek / mimo
    AI_PROVIDER: str = "minimax"

    # MiniMax
    MINIMAX_API_KEY: str = ""
    MINIMAX_BASE_URL: str = "https://api.minimaxi.com/v1/chat/completions"
    MINIMAX_MODEL: str = "MiniMax-M2.7"

    # DeepSeek
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    DEEPSEEK_MODEL: str = "deepseek-chat"

    # Mimo (Xiaomi)
    MIMO_API_KEY: str = ""
    MIMO_BASE_URL: str = "https://api.xiaomimimo.com/v1"
    MIMO_MODEL: str = "mimo-v2.5-pro"

    # LM Studio (local, OpenAI-compatible; API key optional placeholder)
    LMSTUDIO_API_KEY: str = ""
    LMSTUDIO_BASE_URL: str = "http://localhost:1234/v1"
    LMSTUDIO_MODEL: str = ""

    # Firecrawl
    FIRECRAWL_API_KEY: str = ""
    FIRECRAWL_BASE_URL: str = "https://api.firecrawl.dev/v2"

    # Tavily
    TAVILY_API_KEY: str = ""

    # YouTube Data API v3
    YOUTUBE_API_KEY: str = ""

    # Google Custom Search Engine (CSE) — Facebook search
    GOOGLE_CSE_ID: str = "016621447308871563343:vylfmzjmlti"

    # Feishu (Lark) bot — set FEISHU_ENABLED=true + app credentials to activate
    FEISHU_ENABLED: bool = False
    FEISHU_APP_ID: str = ""
    FEISHU_APP_SECRET: str = ""

    # AI Prompts
    SUMMARIZE_POSTS_PROMPT: str = (
        "你是一个情报分析助手。请对以下社交媒体账号今日发布的内容进行简洁总结。"
        "总结应包括：主要内容主题、发布数量、互动情况概述。"
        "如果包含图片，请分析图片内容并将视觉信息融入总结（如图片展示的产品、场景、情绪等）。"
        "直接输出总结内容，不要输出思考过程。"
        "使用中文回复，控制在300字以内。"
    )
    SUMMARIZE_WEBSITE_PROMPT: str = (
        "你是一个情报分析助手。请对以下网站的最新内容进行简洁总结。"
        "总结应包括：主要内容、关键信息点。"
        "使用中文回复，控制在200字以内。"
    )
    INTELLIGENCE_REPORT_PROMPT: str = """# 角色
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

    JWT_SECRET: str = secrets.token_urlsafe(32)
    JWT_EXPIRE_MINUTES: int = 1440
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/intel_monitor.db"
    HOST: str = "0.0.0.0"
    PORT: int = 8000


settings = Settings()

# Ensure data directory exists
Path("data").mkdir(exist_ok=True)
