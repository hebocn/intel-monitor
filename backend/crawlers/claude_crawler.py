# intel-monitor/backend/crawlers/claude_crawler.py
"""
Claude Code + web-access skill 爬虫
通过 Claude Code CLI 使用用户已登录的浏览器爬取内容
"""
import asyncio
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

from crawlers.base import CrawlResult, PostData, CommentData
from crawlers.router import CrawlerEntry


# 结果文件目录
RESULTS_DIR = Path(__file__).parent.parent / "data" / "crawl_results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

CLAUDE_PROMPT_TEMPLATE = """必须加载 web-access skill 并遵循指引。

任务：访问 {url}，提取该账号最近发布的内容。

要求：
1. 使用 CDP 连接用户浏览器（用户已登录）
2. 提取最多 10 条帖子，每条包含：内容文本、URL、点赞数
3. 如果有热门评论，提取最多 10 条（作者、评论文本、点赞数）
4. 将结果以 JSON 格式写入文件：{output_file}

JSON 格式：
{{
  "posts": [
    {{
      "content": "帖子内容",
      "url": "帖子链接",
      "likes": 123,
      "comments": [
        {{"author": "评论者", "text": "评论内容", "likes": 10}}
      ]
    }}
  ],
  "error": ""
}}

注意：
- 如果页面需要登录但用户未登录，将 error 设为 "需要登录"
- 如果爬取失败，将 error 设为具体错误信息
- 成功时 error 设为空字符串
- 完成后输出"DONE"
"""


def _parse_claude_output(output: str) -> dict:
    """从 Claude Code 输出中提取 JSON 结果"""
    # 尝试直接解析
    try:
        return json.loads(output)
    except json.JSONDecodeError:
        pass

    # 查找 JSON 部分
    start = output.find("{")
    end = output.rfind("}") + 1
    if start >= 0 and end > start:
        try:
            return json.loads(output[start:end])
        except json.JSONDecodeError:
            pass

    return {"posts": [], "error": "无法解析 Claude Code 输出"}


def _result_to_crawlresult(data: dict) -> CrawlResult:
    """将 JSON 结果转换为 CrawlResult"""
    error = data.get("error", "")
    if error:
        return CrawlResult(success=False, error_message=error)

    posts = []
    for item in data.get("posts", []):
        comments = [
            CommentData(
                text=c.get("text", ""),
                author=c.get("author", ""),
                likes=c.get("likes", 0),
            )
            for c in item.get("comments", [])
        ]
        posts.append(PostData(
            url=item.get("url", ""),
            content=item.get("content", ""),
            likes=item.get("likes", 0),
            comments=comments,
        ))

    return CrawlResult(posts=posts, success=True)


async def crawl_with_claude(url: str, target_name: str = "") -> CrawlResult:
    """
    使用 Claude Code + web-access skill 爬取内容
    在新窗口打开 PowerShell 运行 Claude Code，异步等待结果文件

    Args:
        url: 目标 URL
        target_name: 目标名称（用于日志）

    Returns:
        CrawlResult: 爬取结果
    """
    # 生成唯一的结果文件名
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = target_name.replace("@", "").replace("/", "_")[:20] or "target"
    output_file = RESULTS_DIR / f"{safe_name}_{timestamp}.json"

    # 构造 Claude Code 命令
    prompt = CLAUDE_PROMPT_TEMPLATE.format(
        url=url,
        output_file=str(output_file).replace("\\", "/")
    )

    try:
        # 写入 prompt 到临时文件（避免命令行转义问题）
        prompt_file = RESULTS_DIR / f"prompt_{timestamp}.txt"
        prompt_file.write_text(prompt, encoding="utf-8")

        # 在新窗口打开 PowerShell 运行 Claude Code
        # 使用 -File 参数读取 prompt 文件
        ps_cmd = (
            f'Start-Process powershell -ArgumentList '
            f'"-NoExit", "-Command", '
            f'"claude -p (Get-Content -Raw \'{prompt_file}\')  --output-format json"'
        )

        proc = await asyncio.create_subprocess_exec(
            "powershell", "-Command", ps_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        # 等待启动
        await asyncio.sleep(2)

        # 清理 prompt 文件
        prompt_file.unlink(missing_ok=True)

        # 等待结果文件出现（最多等待 5 分钟）
        for _ in range(60):  # 每 5 秒检查一次，共 5 分钟
            if output_file.exists():
                # 等待文件写入完成
                await asyncio.sleep(1)
                break
            await asyncio.sleep(5)

        # 读取结果
        if output_file.exists():
            try:
                with open(output_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                # 清理结果文件
                output_file.unlink(missing_ok=True)

                return _result_to_crawlresult(data)
            except json.JSONDecodeError:
                return CrawlResult(
                    success=False,
                    error_message="Claude Code 返回的结果文件格式错误"
                )

        # 超时未找到结果文件
        return CrawlResult(
            success=False,
            error_message="Claude Code 执行超时（5分钟），请检查 Claude Code 是否正常运行"
        )

    except Exception as e:
        return CrawlResult(success=False, error_message=f"Claude Code 执行失败: {str(e)}")


async def crawl_with_claude_sync(url: str, target_name: str = "") -> CrawlResult:
    """
    同步版本：等待 Claude Code 完成后返回结果
    不打开新窗口，直接等待进程完成
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = target_name.replace("@", "").replace("/", "_")[:20] or "target"
    output_file = RESULTS_DIR / f"{safe_name}_{timestamp}.json"

    prompt = CLAUDE_PROMPT_TEMPLATE.format(
        url=url,
        output_file=str(output_file).replace("\\", "/")
    )

    try:
        # 写入 prompt 到临时文件
        prompt_file = RESULTS_DIR / f"prompt_{timestamp}.txt"
        prompt_file.write_text(prompt, encoding="utf-8")

        # 直接运行 Claude Code（不打开新窗口）
        cmd = f'claude -p (Get-Content -Raw \'{prompt_file}\')  --output-format json'

        proc = await asyncio.create_subprocess_exec(
            "powershell", "-Command", cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        # 等待完成（最多 5 分钟）
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
        except asyncio.TimeoutError:
            proc.kill()
            prompt_file.unlink(missing_ok=True)
            return CrawlResult(
                success=False,
                error_message="Claude Code 执行超时（5分钟）"
            )

        # 清理 prompt 文件
        prompt_file.unlink(missing_ok=True)

        # 读取结果文件
        if output_file.exists():
            try:
                with open(output_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                output_file.unlink(missing_ok=True)
                return _result_to_crawlresult(data)
            except json.JSONDecodeError:
                pass

        # 尝试从 stdout 解析结果
        if stdout:
            output = stdout.decode("utf-8", errors="ignore")
            data = _parse_claude_output(output)
            return _result_to_crawlresult(data)

        return CrawlResult(
            success=False,
            error_message="Claude Code 未返回有效结果"
        )

    except Exception as e:
        return CrawlResult(success=False, error_message=f"Claude Code 执行失败: {str(e)}")


def build_claude_entry() -> CrawlerEntry:
    import shutil

    async def _check():
        return shutil.which("claude") is not None

    async def _crawl(platform, account_name, account_url, post_limit=10):
        return await crawl_with_claude_sync(account_url, account_name)

    return CrawlerEntry(
        name="claude",
        platforms=frozenset({"x", "xiaohongshu", "reddit", "bilibili", "youtube", "weibo", "douyin"}),
        crawl=_crawl,
        available=_check,
    )
