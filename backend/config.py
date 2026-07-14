# intel-monitor/backend/config.py
import secrets
from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
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

    # Firecrawl
    FIRECRAWL_API_KEY: str = ""
    FIRECRAWL_BASE_URL: str = "https://api.firecrawl.dev/v2"

    # Tavily
    TAVILY_API_KEY: str = ""

    # YouTube Data API v3
    YOUTUBE_API_KEY: str = ""

    # AI Prompts
    SUMMARIZE_POSTS_PROMPT: str = (
        "你是一个情报分析助手。请对以下社交媒体账号今日发布的内容进行简洁总结。"
        "总结应包括：主要内容主题、发布数量、互动情况概述。"
        "如果包含图片，请分析图片内容并将视觉信息融入总结（如图片展示的产品、场景、情绪等）。"
        "直接输出总结内容，不要输出思考过程。"
        "使用中文回复，控制在300字以内。"
    )
    SUMMARIZE_WEBSITE_PROMPT: str = (
        "你是一个情报分析助手。请对以下网站的最新内容进行简洁总结，并进行邪教风险评估。\n\n"
        "已知邪教组织参考（已由中国政府依法定性）：\n"
        "- 法轮功（法轮大法）：宣扬李洪志为宇宙主佛，鼓吹\"真善忍\"，已被依法取缔\n"
        "- 菩提功：又称\"菩提禅修\"，由金菩提（狄玉明）创立，宣扬\"菩提禅修\"可治病健身、开发超能力，神化头目，已被依法定性为邪教\n"
        "- 全能神（东方闪电）：宣扬\"女基督\"，制造社会恐慌\n"
        "- 门徒会（三赎基督）：宣扬\"祷告治病\"，危害社会秩序\n"
        "- 呼喊派、灵灵教、观音法门等其他已定性邪教组织\n\n"
        "总结应包括：\n"
        "1. 主要内容：网站定位、核心主张、关键信息点，若网站内容与上述已知邪教组织相关联请明确指出\n"
        "2. 邪教风险评估：依据中国法律法规（刑法第300条、两高关于办理组织利用邪教组织破坏法律实施等刑事案件适用法律若干问题的解释），"
        "从以下维度分析该网站是否具备邪教特征：\n"
        "   a) 神化头目：是否宣扬某人物具有超自然能力或救世主身份\n"
        "   b) 精神控制：是否要求成员绝对服从、与外界隔离或禁止质疑\n"
        "   c) 敛财行为：是否以修行、捐赠、课程等名义大量收取财物\n"
        "   d) 危害社会：是否有反社会、反政府言论或煽动对抗法律法规\n"
        "   e) 秘密结社：是否建立封闭性组织体系、秘密活动\n"
        "3. 综合研判：该网站是否涉嫌邪教宣传，给出\"高风险\"\"中风险\"\"低风险\"\"无明显风险\"的评级及依据\n\n"
        "使用中文回复，控制在500字以内。"
    )
    INTELLIGENCE_REPORT_PROMPT: str = (
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

    JWT_SECRET: str = secrets.token_urlsafe(32)
    JWT_EXPIRE_MINUTES: int = 1440
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/intel_monitor.db"
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()

# Ensure data directory exists
Path("data").mkdir(exist_ok=True)
