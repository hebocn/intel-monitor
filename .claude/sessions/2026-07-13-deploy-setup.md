# 会话记录 — 2026-07-13

## 任务：intel-monitor 项目本地部署与配置

### 环境

- **系统**: Windows 11 Pro for Workstations 10.0.26200
- **Python**: 3.14.2 (`C:\Program Files\Python314\`)
- **Node.js**: v24.16.0, npm 11.13.0
- **项目路径**: `C:\Users\Administrator\Desktop\intel-monitor-backup-20260713\intel-monitor\`

### 已完成的步骤

#### 1. 项目分析
- 确认项目类型：全栈 Web 应用（FastAPI 后端 + React/Ant Design 前端）
- 技术栈：Python 3.14, FastAPI, SQLAlchemy async + aiosqlite, JWT 认证, APScheduler 调度
- 前端：React 18, Ant Design 5, Vite 5, TypeScript, Axios
- 爬虫：OpenCLI → CDP → Scrapling → Playwright 降级链
- AI 摘要：MiniMax / DeepSeek / MiMo（通过 OpenAI 兼容 API）
- 功能模块：社交媒体监控、网站内容监控、热门话题追踪（16平台）、舆情搜索（5平台）、AI 情报报告生成

#### 2. Python 依赖安装
安装的包：aiosqlite, bcrypt, python-jose[cryptography], passlib[bcrypt], scrapling[fetchers], pydantic-settings, curl_cffi, patchright, browserforge 等

#### 3. 前端 npm 依赖
`npm install` — 160 packages，有 7 个已知漏洞（非关键）

#### 4. Playwright 浏览器
`python -m playwright install chromium` — Chromium Headless Shell v149.0.7827.55 已安装

#### 5. Scrapling 浏览器依赖
`scrapling install` — Playwright 浏览器依赖已安装

#### 6. 数据库初始化
`backend/data/` 目录已创建，SQLite 数据库表已自动生成

#### 7. 启动服务
- 后端：`python main.py` → `http://localhost:8000` ✅
- 前端：`npm run dev` → `http://localhost:3000` ✅
- API 状态检查：`GET /api/auth/status` 返回 `{"needs_setup": true}`（首次运行）

#### 8. Skill 迁移
将 `../.agents/` 目录移动到 `intel-monitor/.claude/`，包含 18 个自定义 skill：
- opencli-usage, opencli-adapter-author, opencli-autofix, opencli-browser, opencli-browser-sitemap
- improve-codebase-architecture, review, qa, diagnose, grill-me, grill-with-docs
- caveman, design-an-interface, edit-article, handoff, prototype, request-refactor-plan
- git-guardrails-claude-code, migrate-to-shoehorn, obsidian-vault, scaffold-exercises, setup-matt-pocock-skills

### 已配置的 API Keys（来自 `.env`）
- MiniMax API Key ✅
- DeepSeek API Key ✅（当前 AI 提供商，`AI_PROVIDER=deepseek`）
- MiMo API Key ✅
- Firecrawl API Key ✅
- Tavily API Key ✅

### 需用户处理的事项

#### 紧急
1. **重启 Claude Code** — `.claude/skills/` 中的 skill 需要新会话才能加载
2. **创建管理员账号** — 首次访问 `http://localhost:3000` 时按提示设置

#### 常规
3. **Chrome CDP 启动**（影响部分爬虫功能）：
   ```
   "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222
   ```
   微博热搜已有 Playwright 备选方案不受此影响

#### 可选修复
4. `crawlers/toutiao_scrapling_crawler.py:191` — `"\d"` 应改为 `r"\d"`（Python 3.14 SyntaxWarning）
5. 确认 DeepSeek/MiniMax/MiMo/Firecrawl/Tavily API Keys 是否仍有效

### 舆情搜索 — 小红书搜索机制摘要
- 唯一路径：`opencli xiaohongshu search <keyword> --limit N --format json`
- 依赖 `@jackwener/opencli` npm 包 + Chrome 登录态
- **无降级方案**，OpenCLI 失败则直接报错
- 返回字段有限：title, url, likes, images（无 views/comments/shares/bookmarks）
