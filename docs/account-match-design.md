# 账号比对模块 — 设计方案

> 状态: 待实现 | 日期: 2026-07-17

---

## 概述

在原有功能基础上新增"账号比对"模块。用户输入一个目标账号名，在小红书、微博、Twitter 三个平台检索匹配账号，通过传统模糊匹配初筛，最终调用 DeepSeek API 综合评估候选账号与目标是否属于同一个人，输出高置信度的关联账号列表。

---

## 1. 数据流程（5 步漏斗）

```
输入 "张三"
  │
  ▼
┌─ Step 1: 各平台用户搜索 ───────────────────────────┐
│  微博(m.weibo.cn API)  小红书(CDP)  Twitter(Playwright) │
│  → 微博候选 8人 + 小红书 5人 + Twitter 6人 = 19人       │
└──────────────────────────────────────────────────────┘
  │
  ▼
┌─ Step 2: 各候选人抓取近期 5 条帖子 ──────────────────┐
│  微博(移动API)  小红书(CDP)  Twitter(Playwright)       │
│  → 每人 5 条帖子 + 元信息（时间、互动）                 │
└──────────────────────────────────────────────────────┘
  │
  ▼
┌─ Step 3: AI 压缩 + 画像 ────────────────────────────┐
│  每个候选人的帖子 → DeepSeek 压缩为结构化画像          │
│  → {昵称, 平台, 关注领域, 语言风格, 活动时段, ...}    │
└──────────────────────────────────────────────────────┘
  │
  ▼
┌─ Step 4: 跨平台相似度对比 ──────────────────────────┐
│  所有候选人画像 → DeepSeek 全局分析                     │
│  → 为每个跨平台关联对赋分并排序                        │
└──────────────────────────────────────────────────────┘
  │
  ▼
┌─ Step 5: 结果持久化 + 展示 ──────────────────────────┐
│  高置信度关联组列表，支持历史搜索记录查询               │
└──────────────────────────────────────────────────────┘
```

---

## 2. 数据模型（新表）

### `account_match_tasks` — 每次搜索任务

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | Integer PK | |
| `user_id` | Integer FK | 所属用户 |
| `target_name` | String(100) | 输入的搜索名 |
| `status` | String(20) | pending / searching / profiling / comparing / completed / failed |
| `error_log` | Text | 失败信息 |
| `created_at` | DateTime | |
| `completed_at` | DateTime | |

### `account_match_candidates` — 各平台搜到的候选人

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | Integer PK | |
| `task_id` | Integer FK | |
| `platform` | String(20) | weibo / xiaohongshu / twitter |
| `platform_uid` | String(100) | 平台内唯一 ID |
| `nickname` | String(100) | 昵称 |
| `avatar_url` | String(500) | 头像 |
| `bio` | Text | 个人简介/签名 |
| `followers_count` | Integer | 粉丝数（如有） |
| `profile_json` | Text | Step 3 AI 生成的画像 JSON |
| `posts_json` | Text | Step 2 抓取的帖子内容 JSON |

### `account_match_results` — 最终关联结果

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | Integer PK | |
| `task_id` | Integer FK | |
| `group_label` | String(100) | 关联组标签（如 "技术从业者·张三"） |
| `confidence_score` | Float | 综合置信度 0-1 |
| `account_ids_json` | Text | 该组包含的 candidate IDs |
| `ai_analysis` | Text | DeepSeek 的分析理由 |

---

## 3. 后端 API

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/api/account-match/search` | 发起比对任务（body: target_name, platforms），后台异步执行，立即返回 `task_id` |
| `GET` | `/api/account-match/tasks` | 查询历史搜索记录 |
| `GET` | `/api/account-match/tasks/{id}` | 查询单个任务详情（含 candidates + results） |
| `DELETE` | `/api/account-match/tasks/{id}` | 删除历史记录 |

---

## 4. 各平台搜索技术方案

| 平台 | 用户搜索 | 发帖抓取 |
|---|---|---|
| **微博** | `m.weibo.cn/api/container/getIndex?containerid=100103type%3D3%26q%3D{name}` 用户搜索端点，纯 HTTP | 复用 `weibo_crawler.py` 的 profile API |
| **小红书** | CDP 浏览器驱动 — 搜索框输入 + 点击"用户"tab，解析 DOM 获取用户列表 | CDP 浏览器进入用户主页抓取最近笔记 |
| **Twitter/X** | Playwright → `x.com/search?q={name}&f=user` → 解析页面获取用户卡片列表 | Playwright 进入用户主页抓取最近推文 |

---

## 5. DeepSeek 调用结构

### Step 3 — 单个候选人画像（N 个候选 × 1 次调用，可并发）

```
System: "你是一个用户画像分析专家。根据以下社交账号的发帖内容，输出该用户的画像JSON..."
User:   "平台: 微博\n昵称: 张三_Official\n发帖内容:\n[帖子1] ...[帖子5]"
→ 返回: {"domain": "科技/AI", "tone": "技术分享型", "activity_region": "北京", ...}
```

### Step 4 — 全局相似度分析（1 次调用）

```
System: "你是一个跨平台身份关联分析专家。根据以下候选人画像，判断哪些是同一人..."
User:   "[微博] 张三_Official: {画像JSON}\n[小红书] 张三的日常: {画像JSON}\n[Twitter] @zhangsan_real: {画像JSON}\n..."
→ 返回: [{"group": "张三·科技从业者", "score": 0.92, "members": [1,5,12], "reason": "..."}, ...]
```

---

## 6. 前端

**路由**: `/account-match`

**侧边栏**: 菜单项放在"社交账号"下方，图标使用 `TeamOutlined` 或 `SwapOutlined`

**页面布局**（参考 `HotTopicsPage` / `SentimentPage` 风格）：

- **搜索区**: 输入框（目标账号名） + 平台多选（微博/小红书/Twitter） + "开始比对"按钮
- **搜索中**: 显示阶段性进度（"正在搜索微博..." → "微博: 找到 8 个候选" → "正在抓取帖子..." → "正在画像..." → "正在关联分析..."）
- **历史记录区**: 卡片列表，每条显示搜索名、时间、关联组数、状态，点击展开结果
- **结果展示**: 每个关联组一张卡片，显示置信度分数、各平台账号信息（头像、昵称、平台名、跳转链接）+ AI 分析理由

### API 服务 (`frontend/src/services/api.ts`)

```typescript
export const accountMatchAPI = {
  search: (data: { target_name: string; platforms: string[] }) =>
    api.post('/account-match/search', data),
  listTasks: () => api.get('/account-match/tasks'),
  getTask: (id: number) => api.get(`/account-match/tasks/${id}`),
  deleteTask: (id: number) => api.delete(`/account-match/tasks/${id}`),
}
```

轮询模式：发起搜索后前端每 3 秒轮询 `GET /tasks/{id}`，直到 `status` 变为 `completed` 或 `failed`。

---

## 7. 前后端文件清单

| 层 | 新建/修改 | 文件 |
|---|---|---|
| 后端 | **新建** | `backend/models/account_match.py` |
| 后端 | **新建** | `backend/schemas/account_match.py` |
| 后端 | **新建** | `backend/routers/account_match.py` |
| 后端 | **新建** | `backend/services/account_matcher.py`（核心编排） |
| 后端 | **新建** | `backend/crawlers/account_search.py`（三平台用户搜索） |
| 后端 | **修改** | `backend/models/__init__.py`（注册新模型） |
| 后端 | **修改** | `backend/main.py`（挂载新路由） |
| 前端 | **新建** | `frontend/src/pages/AccountMatchPage.tsx` |
| 前端 | **修改** | `frontend/src/App.tsx`（新路由） |
| 前端 | **修改** | `frontend/src/components/AppLayout.tsx`（新菜单项） |
| 前端 | **修改** | `frontend/src/services/api.ts`（新 API 方法） |

---

## 8. 风险点

| 风险 | 应对 |
|---|---|
| 小红书 CDP 用户搜索不稳定 | 用 CSS 选择器而非坐标点击，加重试和超时保护 |
| Twitter Playwright 反爬 | 使用项目中已有的 stealth 浏览器设置，限制请求频率 |
| DeepSeek 结构化输出不可靠 | prompt 中要求严格 JSON 格式 + 前端 try/catch 容错 |
| 搜索时间过长（预估 2-5 分钟） | 全程异步 + 前端进度轮询，不阻塞 |
| 用户画像压缩丢失关键信息 | Step 3 保留原始帖子 JSON，Step 4 同时传画像 + 部分原文 |

---

## 9. 后续扩展（不在本次范围）

- 一键将关联账号添加到社交账号监测
- 支持更多平台（抖音、B站、知乎等）
- 定期自动重新比对（追踪账号改名）
- 头像视觉特征比对辅助验证
