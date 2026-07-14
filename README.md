# Intel Monitor — 情报监控平台

监控社交媒体账号动态和网站内容变化，自动抓取、AI 摘要、定时推送。

## 功能

- **社交媒体监控**: 微博、X (Twitter)、小红书、抖音、YouTube、Bilibili
- **舆情搜索**: 关键词实时搜索 5 个中文平台（微博/抖音/小红书/今日头条/108天台社区），影响力评分排序
- **网站内容监控**: 任意网页，支持 CSS 选择器提取
- **热门话题追踪**: 16 个平台热搜（微博/知乎/B站/HackerNews/GitHub 等），一键批量抓取
- **AI 摘要**: 自动总结每日动态和热点评论，支持多模态图片分析
- **定时调度**: 支持 cron 表达式灵活配置
- **爬虫降级**: OpenCLI → CDP → Playwright 自动切换

## 快速启动

```bash
# 一键启动（后端 + 前端）
start.bat

# 或手动启动：
cd backend
pip install -r requirements.txt
python main.py              # 后端 http://localhost:8000

cd frontend
npm install
npm run dev                 # 前端 http://localhost:3000
```

首次访问会提示创建管理员账号。

## 技术栈

| 层 | 技术 |
|----|------|
| 后端 | Python 3.14, FastAPI, SQLAlchemy, APScheduler |
| 前端 | React 18, Ant Design 5, Vite |
| 数据库 | SQLite |
| AI 摘要 | MiniMax / DeepSeek / MiMo（可切换） |
| 爬虫 | OpenCLI, CDP Proxy, Playwright |
| 热门话题 | AutoCLI (Chrome CDP, 复用登录态) |

## 文档

- [设计文档](docs/superpowers/specs/) — 架构设计和功能规格
- [实施计划](docs/superpowers/plans/) — 详细实施步骤
- [API 文档](http://localhost:8000/docs) — Swagger UI（运行时访问）
