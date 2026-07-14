# 会话记录 — 2026-07-13

## 任务：修复小红书舆情搜索无结果问题

### 根因分析

1. **CDP Proxy 未运行** — 小红书舆情搜索唯一入口 `xhs_cdp_search.py:search_xhs()` 完全依赖 CDP Proxy (localhost:3456)，该代理不会随系统或后端自动启动。一旦被杀就永久失效，且无降级方案。
2. **中文搜索关键词编码损坏** — `_cdp_new_tab()` 和 `_cdp_navigate()` 通过 httpx `content` 参数传递 URL 时未显式用 UTF-8 bytes 编码。

### 完整调用链

```
SentimentPage.tsx:handleSearch()
  → POST /api/sentiment/search (routers/sentiment.py)
    → asyncio.create_task(run_sentiment_search())
      → _search_xiaohongshu(keyword, limit) (services/sentiment.py)
        → xhs_cdp_search.py:search_xhs(keyword, limit)
          → CDP Proxy (localhost:3456) → Chrome CDP (:9222) → 小红书
```

**无降级方案**：舆情搜索中 xiaohongshu 只有 CDP 路径。`opencli_crawler.py` 有 xiaohongshu search 能力但未接入哨兵搜索。

### 修复一：中文关键词编码

**文件**: `backend/crawlers/xhs_cdp_search.py`

```python
# _cdp_new_tab — line 44
content=url.encode("utf-8")  # was: content=url

# _cdp_navigate — line 55  
content=url.encode("utf-8")  # was: content=url
```

### 修复二：CDP Proxy 按需自启动

**文件**: `backend/crawlers/xhs_cdp_search.py`

新增函数：
- `_cdp_proxy_script()` — 自动解析 cdp-proxy.mjs 路径 (`<project>/.claude/skills/web-access/scripts/cdp-proxy.mjs`)
- `_ensure_cdp_proxy()` — 先检查 health，不可用时 `subprocess.Popen(["node", script])` 启动，最多等待 5s
- `search_xhs()` 中 `_check_cdp_proxy()` 替换为 `_ensure_cdp_proxy()`

### 验证结果

| 测试 | 结果 |
|------|------|
| CDP Proxy 关停 → 触发搜索 → 自启动 | ✅ 日志 `Auto-starting CDP Proxy: node ...` |
| 搜索 "北京" → 返回 "北京旅游" 等 | ✅ 数据库 keyword hex `E58C97E4BAAC` = 北京 |
| 多轮搜索稳定性 | ✅ Task 9/12 均正常 |

### 运行中服务

| 组件 | 地址 |
|------|------|
| 后端 FastAPI | localhost:8000 |
| 前端 Vite | localhost:3000 |
| Chrome CDP | localhost:9222 |
| CDP Proxy | localhost:3456 (按需自启动) |

### 已知仍未解决的问题

1. 小红书搜索无降级方案 — OpenCLI 已有 `xiaohongshu search` 能力但未接入 `_search_xiaohongshu`
2. 前端在部分平台失败时不展示 `error_log`（任务 status 为 completed 时静默）
