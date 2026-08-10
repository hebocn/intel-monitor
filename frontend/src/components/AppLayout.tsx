import { Layout, Tooltip, Avatar, Dropdown, Button, Typography } from 'antd'
import {
  DashboardOutlined, MobileOutlined, GlobalOutlined,
  SettingOutlined, LogoutOutlined, RadarChartOutlined,
  LeftOutlined, RightOutlined, FireOutlined, SearchOutlined,
  FileTextOutlined, SwapOutlined, CodeSandboxOutlined,
} from '@ant-design/icons'
import { useNavigate, useLocation } from 'react-router-dom'
import { ReactNode, useState, useEffect, useCallback } from 'react'

// 从 JWT token 解析用户名
function getUsername(): string {
  try {
    const token = localStorage.getItem('token')
    if (!token) return '管理员'
    const payload = JSON.parse(atob(token.split('.')[1]))
    return payload.sub || '管理员'
  } catch { return '管理员' }
}

// DiceBear 生成宠物动漫头像 URL
function getAvatarUrl(name: string): string {
  return `https://api.dicebear.com/9.x/adventurer/svg?seed=${encodeURIComponent(name)}&backgroundColor=b6e3f4,c0aede,d1d4f9,ffd5dc,ffdfbf`
}

const { Sider, Header, Content } = Layout
const { Text } = Typography

interface Props {
  children: ReactNode
  onLogout: () => void
}

const menuItems = [
  // { key: '/', icon: <DashboardOutlined />, label: '仪表盘' },  // 暂时隐藏，保留代码
  { key: '/cockpit', icon: <CodeSandboxOutlined />, label: '首页' },
  { key: '/social', icon: <MobileOutlined />, label: '社交账号' },
  { key: '/websites', icon: <GlobalOutlined />, label: '网站监测' },
  { key: '/hot-topics', icon: <FireOutlined />, label: '热门话题' },
  { key: '/sentiment', icon: <SearchOutlined />, label: '舆情搜索' },
  { key: '/intelligence', icon: <FileTextOutlined />, label: '情报报告' },
  { key: '/account-match', icon: <SwapOutlined />, label: '账号比对' },
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

  // 仪表盘数据
  const [dashData, setDashData] = useState<{
    todayResults: number
    activeTargets: number
  } | null>(null)

  // AI 提供商
  const [aiProviderLabel, setAiProviderLabel] = useState('—')

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
    const fetchAiProvider = async () => {
      try {
        const token = localStorage.getItem('token')
        const res = await fetch('/api/settings/active/provider', {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        })
        if (res.ok) {
          const data = await res.json()
          const labels: Record<string, string> = { minimax: 'MiniMax', deepseek: 'DeepSeek', mimo: 'MiMo' }
          setAiProviderLabel(labels[data.provider] || data.provider)
        }
      } catch { /* 静默失败 */ }
    }
    fetchDash()
    fetchAiProvider()
    const timer = setInterval(fetchDash, 60000)
    const onProviderChange = () => fetchAiProvider()
    window.addEventListener('ai-provider-changed', onProviderChange)
    return () => {
      clearInterval(timer)
      window.removeEventListener('ai-provider-changed', onProviderChange)
    }
  }, [location.pathname])
  const currentLabel = menuItems.find(m => m.key === location.pathname)?.label || '页面'

  const isCockpit = location.pathname === '/cockpit'

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider
        width={260}
        collapsedWidth={72}
        collapsed={collapsed}
        trigger={null}
        style={{
          background: '#0F172A',
          borderRight: 'none',
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
          height: '100vh',
          position: 'sticky',
          top: 0,
          left: 0,
          transition: 'width 0.3s cubic-bezier(0.22, 1, 0.36, 1)',
        }}
      >
        {/* 顶部渐变 */}
        <div style={{
          position: 'absolute', top: 0, left: 0, right: 0, height: 200,
          background: 'linear-gradient(180deg, rgba(34,197,94,0.08) 0%, transparent 100%)',
          pointerEvents: 'none',
        }} />

        {/* Logo 区域 */}
        <div style={{
          flexShrink: 0,
          padding: collapsed ? '24px 0' : '32px 28px 28px',
          display: 'flex', alignItems: 'center',
          justifyContent: collapsed ? 'center' : 'flex-start',
          gap: collapsed ? 0 : 16,
          borderBottom: '1px solid transparent',
          borderImage: 'linear-gradient(to right, rgba(34,197,94,0.15), transparent) 1',
          position: 'relative',
        }}>
          {collapsed ? (
            <Tooltip title="情报监测" placement="right" mouseEnterDelay={0.3}>
              <div style={{
                width: 48, height: 48, borderRadius: '50%',
                background: 'rgba(255,255,255,0.04)',
                border: '1px solid rgba(34,197,94,0.25)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>
                <RadarChartOutlined style={{ fontSize: 22, color: '#22C55E' }} />
              </div>
            </Tooltip>
          ) : (
            <>
              <div style={{
                width: 48, height: 48, borderRadius: 12,
                background: 'rgba(255,255,255,0.04)',
                border: '1px solid rgba(34,197,94,0.25)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                flexShrink: 0,
              }}>
                <RadarChartOutlined style={{ fontSize: 22, color: '#22C55E' }} />
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
          flex: 1,
          padding: collapsed ? '20px 0' : '20px 12px',
          display: 'flex', flexDirection: 'column',
          alignItems: collapsed ? 'center' : 'stretch',
          gap: 6,
          overflowY: 'auto',
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
                      color: isActive ? '#22C55E' : 'rgba(248,250,252,0.55)',
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
                  color: isActive ? '#22C55E' : 'rgba(248,250,252,0.55)',
                }}>
                  {item.icon}
                </span>
                <span className="sidebar-nav-label" style={{
                  color: isActive ? '#F8FAFC' : 'rgba(248,250,252,0.65)',
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
          flexShrink: 0,
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
                    color: 'rgba(34,197,94,0.8)', fontSize: 12,
                    fontFamily: 'var(--font-mono)', fontWeight: 600, letterSpacing: 1,
                  }}>
                    {aiProviderLabel}
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
      </Sider>

      <Layout>
        <Header style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          padding: '0 32px',
          background: 'rgba(15,23,42,0.8)',
          backdropFilter: 'blur(16px) saturate(180%)',
          borderBottom: '1px solid rgba(255,255,255,0.06)',
          height: 64,
          position: 'sticky', top: 0, zIndex: 10,
        }}>
          <div style={{
            padding: '6px 18px',
            background: 'rgba(34,197,94,0.08)',
            border: '1px solid rgba(34,197,94,0.15)',
            borderRadius: 8,
            color: '#22C55E',
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
              <Avatar size={36} src={getAvatarUrl(getUsername())} style={{ flexShrink: 0 }} />
              <span style={{ fontSize: 15, fontWeight: 500, color: 'var(--text-primary)' }}>{getUsername()}</span>
            </Button>
          </Dropdown>
        </Header>

        <Content style={{
          padding: isCockpit ? 0 : 32, overflow: 'auto',
          background: '#0B1120',
          minHeight: '100vh',
        }}>
          {children}
        </Content>
      </Layout>
    </Layout>
  )
}
