# 情报监控平台 - 设计文档

## 概述

一个本地运行的情报监控平台，支持录入社交账号和特定网站，通过 CDP 浏览器自动化定时抓取内容，使用 MiniMax API 进行内容总结和热评提取。

## 技术栈

- **后端**: Python FastAPI
- **前端**: React + Ant Design (Vite 构建)
- **数据库**: SQLite (SQLAlchemy ORM)
- **爬虫**: Playwright (CDP 浏览器自动化)
- **AI**: MiniMax API (内容总结 + 热评提取)
- **调度**: APScheduler (定时任务)
- **部署**: 本地运行，FastAPI 同时托管 API 和前端静态文件

## 架构

```
┌─────────────────────────────────────────────────┐
│                   浏览器 (Chrome)                  │
│  React + Ant Design (构建后由 FastAPI 静态托管)       │
└────────────────────┬────────────────────────────┘
                     │ HTTP API
┌────────────────────▼────────────────────────────┐
│              FastAPI 服务 (单进程)                  │
│  ┌──────────┐ ┌──────────┐ ┌──────────────────┐ │
│  │ Auth模块  │ │ 监控管理  │ │   定时任务调度器   │ │
│  │ 登录/设置 │ │ 账号/网站 │ │  (APScheduler)   │ │
│  └──────────┘ └──────────┘ └──────────────────┘ │
│  ┌──────────┐ ┌──────────┐ ┌──────────────────┐ │
│  │ 爬虫引擎  │ │ AI 总结  │ │   数据查询 API    │ │
│  │(Playwright)│ │(MiniMax) │ │                  │ │
│  └──────────┘ └──────────┘ └──────────────────┘ │
└────────────────────┬────────────────────────────┘
                     │
            ┌────────▼────────┐
            │   SQLite 数据库   │
            └─────────────────┘
```

## 数据模型

### users 表
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 主键 |
| username | VARCHAR(50) | 用户名 |
| password_hash | VARCHAR(128) | 密码哈希 (bcrypt) |
| created_at | DATETIME | 创建时间 |

### targets 表 (社交账号监控目标)
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 主键 |
| user_id | INTEGER FK | 关联用户 |
| type | VARCHAR(20) | 类型: social_media / website |
| platform | VARCHAR(20) | 平台: x/youtube/xiaohongshu/douyin/custom |
| account_name | VARCHAR(100) | 账号名称 |
| account_url | VARCHAR(500) | 账号主页 URL |
| avatar_url | VARCHAR(500) | 头像 URL (可选) |
| monitor_interval_minutes | INTEGER | 监控间隔(分钟)，默认 1440 |
| monitor_hour | INTEGER | 每日监控小时 (0-23) |
| monitor_minute | INTEGER | 每日监控分钟 (0-59) |
| is_active | BOOLEAN | 是否启用 |
| created_at | DATETIME | 创建时间 |
| updated_at | DATETIME | 更新时间 |

### website_targets 表 (网站监控目标)
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 主键 |
| user_id | INTEGER FK | 关联用户 |
| name | VARCHAR(100) | 网站名称 |
| url | VARCHAR(500) | 网站 URL |
| css_selector | VARCHAR(200) | 内容区域 CSS 选择器 (可选) |
| monitor_interval_minutes | INTEGER | 监控间隔(分钟)，默认 1440 |
| monitor_hour | INTEGER | 每日监控小时 |
| monitor_minute | INTEGER | 每日监控分钟 |
| is_active | BOOLEAN | 是否启用 |
| created_at | DATETIME | 创建时间 |
| updated_at | DATETIME | 更新时间 |

### monitor_results 表
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 主键 |
| target_id | INTEGER FK | 关联监控目标 |
| target_type | VARCHAR(20) | social_media / website |
| monitor_date | DATE | 监控日期 |
| summary | TEXT | AI 生成的内容总结 |
| raw_content | TEXT | 原始抓取内容 (JSON) |
| status | VARCHAR(20) | success/failed/pending |
| error_message | TEXT | 失败原因 |
| created_at | DATETIME | 创建时间 |

### hot_comments 表
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 主键 |
| monitor_result_id | INTEGER FK | 关联监控结果 |
| post_url | VARCHAR(500) | 原始贴文 URL |
| comment_text | TEXT | 评论内容 |
| author | VARCHAR(100) | 评论作者 |
| likes_count | INTEGER | 点赞数 |
| rank | INTEGER | 排名 (1-10) |
| created_at | DATETIME | 创建时间 |

## 核心模块

### 爬虫引擎

每个平台一个独立的爬虫模块，统一接口：

```python
class BaseCrawler(ABC):
    @abstractmethod
    async def crawl(self, target: Target) -> CrawlResult:
        """抓取指定账号的最新内容"""
        pass

    @abstractmethod
    async def get_hot_comments(self, post_url: str) -> list[Comment]:
        """获取指定贴文的热门评论"""
        pass
```

平台实现：
- **XCrawler**: X (Twitter) 用户主页推文抓取
- **YouTubeCrawler**: YouTube 频道最新视频 + 热门评论
- **XiaoHongShuCrawler**: 小红书用户笔记抓取
- **DouyinCrawler**: 抖音用户视频列表 + 评论
- **WebsiteCrawler**: 通用网站正文内容抓取

### AI 总结模块

使用 MiniMax API 进行：
1. 当日贴文/内容的智能总结
2. 从所有评论中提取热度最高的 10 条
3. 支持中英文内容

### 定时调度器

- APScheduler AsyncIOScheduler
- 每个监控目标独立的 cron job
- 用户修改时间/频次时动态更新 job
- 支持立即执行一次监控
- 失败自动重试 (最多 3 次)

## UI 设计

深色科技风主题，主色调: 深蓝/紫渐变 + 青色高亮。

### 页面结构

1. **登录页**: 首次使用设置账号密码，之后登录
2. **仪表盘**: 监控概览、今日报告、最近状态
3. **社交账号管理**: 按平台分类展示，CRUD 操作
4. **网站监控管理**: 网站列表，CRUD 操作
5. **监控详情**: 单个目标的历史记录、贴文详情、热评
6. **系统设置**: 账户设置、全局配置

### 布局

```
┌──────────────────────────────────────────────────────────┐
│  🔍 情报监控平台                    [用户头像] [设置] [退出] │
├────────────┬─────────────────────────────────────────────┤
│            │                                             │
│  📊 仪表盘  │         主内容区域                            │
│            │                                             │
│  📱 社交账号 │  ┌─────────────────────────────────────┐    │
│   ├ X       │  │  监控目标卡片/详情表格                  │    │
│   ├ YouTube │  │                                     │    │
│   ├ 小红书   │  │                                     │    │
│   └ 抖音     │  └─────────────────────────────────────┘    │
│            │                                             │
│  🌐 网站监控 │  ┌─────────────────────────────────────┐    │
│            │  │  监控报告/热评列表                      │    │
│  📋 监控日志 │  │                                     │    │
│            │  └─────────────────────────────────────┘    │
│  ⚙️ 系统设置 │                                             │
└────────────┴─────────────────────────────────────────────┘
```

## API 设计

```
POST   /api/auth/setup          # 首次设置账号密码
POST   /api/auth/login           # 登录
POST   /api/auth/logout          # 登出

GET    /api/targets              # 获取所有监控目标
POST   /api/targets              # 添加监控目标
PUT    /api/targets/{id}         # 更新监控目标
DELETE /api/targets/{id}         # 删除监控目标
POST   /api/targets/{id}/monitor # 立即执行一次监控

GET    /api/results              # 获取监控结果列表
GET    /api/results/{id}         # 获取单个结果详情

GET    /api/websites             # 获取网站监控列表
POST   /api/websites             # 添加网站监控
PUT    /api/websites/{id}        # 更新网站监控
DELETE /api/websites/{id}        # 删除网站监控

GET    /api/dashboard            # 仪表盘概览数据
```

## 项目结构

```
intel-monitor/
├── backend/
│   ├── main.py                 # FastAPI 入口
│   ├── config.py               # 配置管理
│   ├── database.py             # SQLite 连接
│   ├── models/                 # SQLAlchemy 模型
│   │   ├── user.py
│   │   ├── target.py
│   │   └── result.py
│   ├── routers/                # API 路由
│   │   ├── auth.py
│   │   ├── targets.py
│   │   ├── results.py
│   │   └── schedule.py
│   ├── crawlers/               # 爬虫引擎
│   │   ├── base.py
│   │   ├── x_crawler.py
│   │   ├── youtube_crawler.py
│   │   ├── xiaohongshu_crawler.py
│   │   ├── douyin_crawler.py
│   │   └── website_crawler.py
│   ├── services/               # 业务逻辑
│   │   ├── summarizer.py       # MiniMax AI 总结
│   │   ├── scheduler.py        # APScheduler 调度
│   │   └── monitor.py          # 监控执行逻辑
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   ├── components/
│   │   ├── services/
│   │   └── App.tsx
│   ├── package.json
│   └── vite.config.ts
└── start.bat                   # 一键启动脚本
```

## 配置项

通过 `.env` 文件或环境变量配置:

- `MINIMAX_API_KEY`: MiniMax API 密钥
- `JWT_SECRET`: JWT 签名密钥 (首次运行自动生成)
- `JWT_EXPIRE_MINUTES`: JWT 过期时间，默认 1440 (24小时)
- `DATABASE_URL`: 数据库路径，默认 `sqlite:///./data/intel_monitor.db`
- `HOST`: 服务监听地址，默认 `0.0.0.0`
- `PORT`: 服务端口，默认 `8000`

## 关键依赖

### 后端 (requirements.txt)
- fastapi
- uvicorn
- sqlalchemy
- aiosqlite
- playwright
- apscheduler
- httpx
- bcrypt
- python-jose (JWT)
- pydantic

### 前端 (package.json)
- react
- react-dom
- react-router-dom
- antd
- @ant-design/icons
- axios
- dayjs

## 实施阶段

1. **Phase 1**: 后端基础 - 数据库模型、认证、基础 CRUD API
2. **Phase 2**: 爬虫引擎 - 各平台爬虫实现
3. **Phase 3**: AI 总结 - MiniMax API 集成
4. **Phase 4**: 定时调度 - APScheduler 集成
5. **Phase 5**: 前端 UI - 所有页面实现
6. **Phase 6**: 集成测试 - 端到端测试
