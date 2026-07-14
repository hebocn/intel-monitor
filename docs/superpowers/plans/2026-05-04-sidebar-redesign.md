# 侧边栏重设计实现计划

> **致自动化执行者：** 请使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务执行本计划。步骤使用 `- [ ]` 语法追踪进度。

**目标：** 将左侧边栏从传统固定 Ant Design Menu 改造为可折叠玻璃拟态导航 + 底部迷你仪表盘

**架构：** 保留 Ant Design Sider 容器和路由能力，用自定义 div 替换 Menu 组件实现玻璃拟态菜单项。底部仪表盘从 `/api/dashboard` 获取实时数据。折叠状态通过 `useState` 管理。

**技术栈：** React 18、Ant Design 5 (Tooltip)、CSS 动画、FastAPI `/api/dashboard`

---

## 文件结构

| 文件 | 变更类型 | 职责 |
|------|---------|------|
| `frontend/src/global.css` | 修改 | 新增侧边栏动画关键帧（脉冲、折叠过渡） |
| `frontend/src/components/AppLayout.tsx` | 重写 | 自定义导航、折叠逻辑、底部仪表盘、全部动效 |

> `theme.ts` 不需要修改 — 自定义 div 菜单项不再依赖 Ant Design Menu token。

---

### 任务 1：添加 CSS 动画关键帧

**文件：**
- 修改：`frontend/src/global.css:375-395`

**说明：** 在现有 `.ant-menu` 覆写之前，新增侧边栏专用的 CSS 动画关键帧和样式类。现有的 Menu CSS 覆写将保留（万一有其他地方用到），但新侧边栏不再依赖它们。

- [ ] **步骤 1：在 global.css 的 `/* ===== Menu ===== */` 部分之前插入新的动画关键帧和侧边栏样式**

在 `frontend/src/global.css` 的第 374 行（`/* ===== Menu ===== */` 注释之前）插入：

```css
/* ===== Sidebar Animations ===== */
@keyframes sidebarPulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(82,183,136,0.5); }
  50% { box-shadow: 0 0 12px 4px rgba(82,183,136,0.3); }
}
@keyframes sidebarDashSlide {
  from { opacity: 0; transform: translateY(-8px); }
  to { opacity: 1; transform: translateY(0); }
}
.sidebar-status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #52b788;
  animation: sidebarPulse 2s ease-in-out infinite;
  flex-shrink: 0;
}
.sidebar-nav-item {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 12px 16px;
  border-radius: 12px;
  background: rgba(255,255,255,0.04);
  cursor: pointer;
  transition: all 0.25s cubic-bezier(0.22, 1, 0.36, 1);
  position: relative;
  overflow: hidden;
  user-select: none;
}
.sidebar-nav-item:hover {
  background: rgba(255,255,255,0.08);
}
.sidebar-nav-item:hover .sidebar-nav-icon {
  transform: scale(1.08);
}
.sidebar-nav-item:active {
  transform: scale(0.95);
}
.sidebar-nav-item.active {
  background: rgba(82,183,136,0.1);
}
.sidebar-nav-item.active::before {
  content: '';
  position: absolute;
  left: 0;
  top: 8px;
  bottom: 8px;
  width: 3px;
  background: #52b788;
  border-radius: 0 2px 2px 0;
}
.sidebar-nav-item.active .sidebar-nav-icon {
  color: #52b788;
}
.sidebar-nav-item.active .sidebar-nav-label {
  color: #ffffff;
  font-weight: 600;
}
.sidebar-nav-icon {
  font-size: 20px;
  color: rgba(255,255,255,0.45);
  transition: all 0.15s ease;
  flex-shrink: 0;
}
.sidebar-nav-label {
  font-size: 14px;
  color: rgba(255,255,255,0.55);
  font-family: var(--font-body);
  font-weight: 500;
  letter-spacing: 0.3px;
  white-space: nowrap;
  transition: opacity 0.2s ease;
}
.sidebar-nav-collapsed-item {
  width: 48px;
  height: 48px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(255,255,255,0.04);
  cursor: pointer;
  transition: all 0.25s cubic-bezier(0.22, 1, 0.36, 1);
  position: relative;
  user-select: none;
}
.sidebar-nav-collapsed-item:hover {
  background: rgba(255,255,255,0.08);
}
.sidebar-nav-collapsed-item:hover .sidebar-nav-icon {
  transform: scale(1.08);
}
.sidebar-nav-collapsed-item:active {
  transform: scale(0.95);
}
.sidebar-nav-collapsed-item.active {
  background: rgba(82,183,136,0.1);
  box-shadow: 0 0 12px rgba(82,183,136,0.25);
}
.sidebar-nav-collapsed-item.active::after {
  content: '';
  position: absolute;
  bottom: 2px;
  left: 50%;
  transform: translateX(-50%);
  width: 20px;
  height: 3px;
  background: #52b788;
  border-radius: 2px;
}
.sidebar-nav-collapsed-item.active .sidebar-nav-icon {
  color: #52b788;
}
.sidebar-collapse-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: 8px;
  background: rgba(255,255,255,0.06);
  border: 1px solid rgba(255,255,255,0.08);
  cursor: pointer;
  transition: all 0.25s cubic-bezier(0.22, 1, 0.36, 1);
  color: rgba(255,255,255,0.4);
  font-size: 14px;
}
.sidebar-collapse-btn:hover {
  background: rgba(255,255,255,0.1);
  color: rgba(255,255,255,0.7);
}
.sidebar-collapse-btn:active {
  transform: scale(0.92);
}
.sidebar-dashboard-card {
  padding: 12px;
  background: rgba(255,255,255,0.03);
  border-radius: 10px;
  border: 1px solid rgba(255,255,255,0.04);
  margin-bottom: 6px;
  animation: sidebarDashSlide 0.3s ease both;
}
.sidebar-dashboard-card:last-child {
  margin-bottom: 0;
}
```

- [ ] **步骤 2：验证 CSS 无语法错误**

在浏览器中打开任意页面，确认控制台无 CSS 解析错误。

- [ ] **步骤 3：提交**

```bash
git add frontend/src/global.css
git commit -m "feat(sidebar): 新增侧边栏动画关键帧和样式类"
```

---

### 任务 2：重写 AppLayout.tsx — 侧边栏基础结构与折叠逻辑

**文件：**
- 重写：`frontend/src/components/AppLayout.tsx`

**说明：** 用自定义导航替换 Ant Design Menu，实现可折叠侧边栏。本任务先搭骨架（布局 + 折叠 + 路由跳转），下一任务添加底部仪表盘。

- [ ] **步骤 1：重写 AppLayout.tsx**

将 `frontend/src/components/AppLayout.tsx` 整体替换为：

```tsx
import { Layout, Tooltip, Avatar, Dropdown, Button, Typography } from 'antd'
import {
  DashboardOutlined, MobileOutlined, GlobalOutlined,
  SettingOutlined, UserOutlined, LogoutOutlined, RadarChartOutlined,
  LeftOutlined, RightOutlined,
} from '@ant-design/icons'
import { useNavigate, useLocation } from 'react-router-dom'
import { ReactNode, useState, useEffect, useCallback } from 'react'

const { Sider, Header, Content } = Layout
const { Text } = Typography

interface Props {
  children: ReactNode
  onLogout: () => void
}

const menuItems = [
  { key: '/', icon: <DashboardOutlined />, label: '仪表盘' },
  { key: '/social', icon: <MobileOutlined />, label: '社交账号' },
  { key: '/websites', icon: <GlobalOutlined />, label: '网站监测' },
  { key: '/settings', icon: <SettingOutlined />, label: '系统设置' },
]

export default function AppLayout({ children, onLogout }: Props) {
  const navigate = useNavigate()
  const location = useLocation()
  const [collapsed, setCollapsed] = useState(false)

  // 响应式自动折叠
  const handleResize = useCallback(() => {
    if (window.innerWidth < 768) setCollapsed(true)
  }, [])

  useEffect(() => {
    handleResize()
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [handleResize])

  const currentLabel = menuItems.find(m => m.key === location.pathname)?.label || '页面'

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider
        width={260}
        collapsedWidth={72}
        collapsed={collapsed}
        trigger={null}
        style={{
          background: '#1a2e26',
          borderRight: 'none',
          position: 'relative',
          overflow: 'hidden',
          transition: 'width 0.3s cubic-bezier(0.22, 1, 0.36, 1)',
        }}
      >
        {/* 顶部渐变 */}
        <div style={{
          position: 'absolute', top: 0, left: 0, right: 0, height: 200,
          background: 'linear-gradient(180deg, rgba(45,106,79,0.12) 0%, transparent 100%)',
          pointerEvents: 'none',
        }} />

        {/* Logo 区域 */}
        <div style={{
          padding: collapsed ? '24px 0' : '32px 28px 28px',
          display: 'flex', alignItems: 'center',
          justifyContent: collapsed ? 'center' : 'flex-start',
          gap: collapsed ? 0 : 16,
          borderBottom: '1px solid transparent',
          borderImage: 'linear-gradient(to right, rgba(255,255,255,0.06), transparent) 1',
          position: 'relative',
        }}>
          {collapsed ? (
            <Tooltip title="情报监测" placement="right" mouseEnterDelay={0.3}>
              <div style={{
                width: 48, height: 48, borderRadius: '50%',
                background: 'rgba(255,255,255,0.04)',
                border: '1px solid rgba(45,106,79,0.25)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>
                <RadarChartOutlined style={{ fontSize: 22, color: '#52b788' }} />
              </div>
            </Tooltip>
          ) : (
            <>
              <div style={{
                width: 48, height: 48, borderRadius: 12,
                background: 'rgba(255,255,255,0.04)',
                border: '1px solid rgba(45,106,79,0.25)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                flexShrink: 0,
              }}>
                <RadarChartOutlined style={{ fontSize: 22, color: '#52b788' }} />
              </div>
              <div style={{ minWidth: 0 }}>
                <Text strong style={{
                  color: '#ffffff', fontSize: 20, display: 'block', lineHeight: 1.2,
                  fontFamily: "var(--font-display)", letterSpacing: 1, fontWeight: 700,
                }}>
                  情报监测
                </Text>
                <Text style={{
                  color: 'rgba(255,255,255,0.35)', fontSize: 11, letterSpacing: 3,
                  fontFamily: "var(--font-mono)", fontWeight: 500,
                }}>
                  INTEL · MONITOR
                </Text>
              </div>
            </>
          )}
        </div>

        {/* 导航菜单 */}
        <nav style={{
          padding: collapsed ? '20px 0' : '20px 12px',
          display: 'flex', flexDirection: 'column',
          alignItems: collapsed ? 'center' : 'stretch',
          gap: 6,
        }}>
          {menuItems.map(item => {
            const isActive = location.pathname === item.key
            if (collapsed) {
              return (
                <Tooltip key={item.key} title={item.label} placement="right" mouseEnterDelay={0.3}>
                  <div
                    className={`sidebar-nav-collapsed-item${isActive ? ' active' : ''}`}
                    onClick={() => navigate(item.key)}
                  >
                    <span className="sidebar-nav-icon" style={{
                      fontSize: 22,
                      color: isActive ? '#52b788' : 'rgba(255,255,255,0.45)',
                    }}>
                      {item.icon}
                    </span>
                  </div>
                </Tooltip>
              )
            }
            return (
              <div
                key={item.key}
                className={`sidebar-nav-item${isActive ? ' active' : ''}`}
                onClick={() => navigate(item.key)}
              >
                <span className="sidebar-nav-icon" style={{
                  color: isActive ? '#52b788' : 'rgba(255,255,255,0.45)',
                }}>
                  {item.icon}
                </span>
                <span className="sidebar-nav-label" style={{
                  color: isActive ? '#ffffff' : 'rgba(255,255,255,0.55)',
                  fontWeight: isActive ? 600 : 500,
                }}>
                  {item.label}
                </span>
              </div>
            )
          })}
        </nav>

        {/* 底部区域 — 仪表盘 + 折叠按钮 */}
        <div style={{
          position: 'absolute', bottom: 0, left: 0, right: 0,
          padding: collapsed ? '16px 0' : '16px 12px',
          display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12,
        }}>
          {/* 折叠按钮 */}
          <div
            className="sidebar-collapse-btn"
            onClick={() => setCollapsed(prev => !prev)}
          >
            {collapsed ? <RightOutlined /> : <LeftOutlined />}
          </div>

          {/* 状态指示器（始终显示） */}
          <div style={{
            display: 'flex', alignItems: 'center',
            justifyContent: collapsed ? 'center' : 'flex-start',
            gap: collapsed ? 0 : 10,
            width: collapsed ? 'auto' : '100%',
            padding: collapsed ? 0 : '0 4px',
          }}>
            <div className="sidebar-status-dot" />
            {!collapsed && (
              <Text style={{
                color: 'rgba(255,255,255,0.45)', fontSize: 12,
                fontFamily: "var(--font-body)", letterSpacing: 1.5, fontWeight: 500,
              }}>
                系统运行中
              </Text>
            )}
          </div>
        </div>
      </Sider>

      <Layout>
        <Header style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          padding: '0 32px',
          background: 'rgba(255,255,255,0.8)',
          backdropFilter: 'blur(16px) saturate(180%)',
          borderBottom: '1px solid var(--border)',
          height: 64,
          position: 'sticky', top: 0, zIndex: 10,
        }}>
          <div style={{
            padding: '6px 18px',
            background: 'rgba(45,106,79,0.06)',
            border: '1px solid rgba(45,106,79,0.12)',
            borderRadius: 8,
            color: '#2d6a4f',
            fontSize: 13, letterSpacing: 2,
            fontFamily: "var(--font-body)", fontWeight: 600,
          }}>
            {currentLabel}
          </div>

          <Dropdown menu={{
            items: [{
              key: 'logout',
              icon: <LogoutOutlined />,
              label: '退出登录',
              onClick: onLogout,
              danger: true,
            }],
          }}>
            <Button type="text" style={{
              color: 'var(--text-secondary)',
              display: 'flex', alignItems: 'center', gap: 10,
              height: 44, borderRadius: 10,
            }}>
              <Avatar size={32} icon={<UserOutlined />} style={{
                background: 'linear-gradient(135deg, #dce8e0, #b8d4c4)',
                color: '#5f7a6e',
              }} />
              <span style={{ fontSize: 15, fontWeight: 500 }}>管理员</span>
            </Button>
          </Dropdown>
        </Header>

        <Content style={{
          padding: 32, overflow: 'auto', background: 'var(--bg)',
        }}>
          {children}
        </Content>
      </Layout>
    </Layout>
  )
}
```

- [ ] **步骤 2：验证侧边栏功能**

启动开发服务器（`cd frontend && npm run dev`），在浏览器中打开 http://localhost:3000，检查：
- 侧边栏默认展开（260px），4 个菜单项以玻璃拟态卡片样式显示
- 点击底部折叠按钮，侧边栏平滑收缩到 72px，菜单项变为圆形图标
- 折叠态下 hover 图标显示 Tooltip
- 点击菜单项能正常跳转路由
- 选中项有绿色竖条指示器和高亮效果
- 窗口宽度 < 768px 时自动折叠

- [ ] **步骤 3：提交**

```bash
git add frontend/src/components/AppLayout.tsx
git commit -m "feat(sidebar): 可折叠玻璃拟态导航基础结构"
```

---

### 任务 3：添加底部迷你仪表盘

**文件：**
- 修改：`frontend/src/components/AppLayout.tsx`

**说明：** 在侧边栏底部（折叠按钮上方）添加迷你仪表盘，显示监控状态、今日任务数、AI 提供商。折叠态下隐藏仪表盘，仅保留状态点。

- [ ] **步骤 1：在 AppLayout.tsx 中添加仪表盘数据获取逻辑**

在 `AppLayout` 组件内，`collapsed` state 声明之后添加数据获取逻辑：

```tsx
// 仪表盘数据
const [dashData, setDashData] = useState<{
  todayResults: number
  activeTargets: number
} | null>(null)

useEffect(() => {
  const fetchDash = async () => {
    try {
      const token = localStorage.getItem('token')
      const res = await fetch('/api/dashboard', {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
      if (res.ok) {
        const data = await res.json()
        setDashData({
          todayResults: data.stats?.today_results ?? 0,
          activeTargets: data.stats?.active_targets ?? 0,
        })
      }
    } catch { /* 静默失败 */ }
  }
  fetchDash()
  const timer = setInterval(fetchDash, 60000)
  return () => clearInterval(timer)
}, [])

const aiProvider = (import.meta.env.VITE_AI_PROVIDER || 'minimax').toUpperCase()
```

- [ ] **步骤 2：在底部区域添加仪表盘卡片**

在 `AppLayout.tsx` 的底部区域（折叠按钮上方），在 `{/* 折叠按钮 */}` 注释之前插入仪表盘：

将底部区域的 JSX 替换为：

```tsx
{/* 底部区域 — 仪表盘 + 折叠按钮 */}
<div style={{
  position: 'absolute', bottom: 0, left: 0, right: 0,
  padding: collapsed ? '16px 0' : '16px 12px',
  display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12,
}}>
  {/* 仪表盘（仅展开态显示） */}
  {!collapsed && (
    <div style={{
      width: '100%',
      borderTop: '1px solid rgba(255,255,255,0.06)',
      paddingTop: 14,
      display: 'flex', flexDirection: 'column', gap: 6,
    }}>
      <div className="sidebar-dashboard-card" style={{ animationDelay: '0s' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div className="sidebar-status-dot" />
          <Text style={{ color: 'rgba(255,255,255,0.45)', fontSize: 12, fontFamily: 'var(--font-body)' }}>
            监控运行中
          </Text>
        </div>
      </div>
      <div className="sidebar-dashboard-card" style={{ animationDelay: '0.05s' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <Text style={{ color: 'rgba(255,255,255,0.35)', fontSize: 11, fontFamily: 'var(--font-body)', letterSpacing: 1 }}>
            今日任务
          </Text>
          <Text style={{
            color: 'rgba(255,255,255,0.7)', fontSize: 16,
            fontFamily: 'var(--font-mono)', fontWeight: 600,
          }}>
            {dashData?.todayResults ?? '—'}
          </Text>
        </div>
      </div>
      <div className="sidebar-dashboard-card" style={{ animationDelay: '0.1s' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <Text style={{ color: 'rgba(255,255,255,0.35)', fontSize: 11, fontFamily: 'var(--font-body)', letterSpacing: 1 }}>
            AI 引擎
          </Text>
          <Text style={{
            color: 'rgba(82,183,136,0.8)', fontSize: 12,
            fontFamily: 'var(--font-mono)', fontWeight: 600, letterSpacing: 1,
          }}>
            {aiProvider}
          </Text>
        </div>
      </div>
    </div>
  )}

  {/* 折叠按钮 */}
  <div
    className="sidebar-collapse-btn"
    onClick={() => setCollapsed(prev => !prev)}
  >
    {collapsed ? <RightOutlined /> : <LeftOutlined />}
  </div>

  {/* 状态指示器（始终显示） */}
  <div style={{
    display: 'flex', alignItems: 'center',
    justifyContent: collapsed ? 'center' : 'flex-start',
    gap: collapsed ? 0 : 10,
    width: collapsed ? 'auto' : '100%',
    padding: collapsed ? 0 : '0 4px',
  }}>
    <div className="sidebar-status-dot" />
    {!collapsed && (
      <Text style={{
        color: 'rgba(255,255,255,0.45)', fontSize: 12,
        fontFamily: "var(--font-body)", letterSpacing: 1.5, fontWeight: 500,
      }}>
        系统运行中
      </Text>
    )}
  </div>
</div>
```

- [ ] **步骤 3：验证仪表盘功能**

在浏览器中检查：
- 展开态底部显示 3 张仪表盘卡片（监控状态、今日任务数、AI 引擎）
- 今日任务数显示实际数字（从 `/api/dashboard` 获取）
- AI 引擎显示当前环境变量配置的提供商名称
- 折叠态仪表盘卡片隐藏，仅显示折叠按钮和状态点
- 折叠/展开时仪表盘有淡入淡出过渡效果

- [ ] **步骤 4：提交**

```bash
git add frontend/src/components/AppLayout.tsx
git commit -m "feat(sidebar): 添加底部迷你仪表盘"
```

---

### 任务 4：最终验证与整体提交

**文件：** 无新文件修改

- [ ] **步骤 1：完整功能验证**

在浏览器中完成以下检查清单：
- [ ] 展开态（260px）：Logo + 玻璃拟态菜单项 + 底部仪表盘 + 折叠按钮
- [ ] 折叠态（72px）：圆形图标菜单 + Tooltip + 底部状态点 + 折叠按钮
- [ ] 折叠/展开动画平滑（0.3s）
- [ ] 菜单项 hover 效果（背景变亮 + 图标缩放）
- [ ] 选中项指示器（展开态左侧竖条 / 折叠态底部横条）
- [ ] 菜单点击跳转正常
- [ ] Header 页面标签随路由变化
- [ ] 仪表盘数据每 60 秒刷新
- [ ] 窗口 < 768px 自动折叠
- [ ] 无控制台错误

- [ ] **步骤 2：如有问题，修复后提交**
