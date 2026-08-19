import { useEffect, useState, useRef, useCallback } from 'react'
import { Tooltip, Tag, Skeleton, Image } from 'antd'
import {
  DashboardOutlined, CheckCircleOutlined, CloseCircleOutlined,
  ClockCircleOutlined, RobotOutlined, GlobalOutlined, MobileOutlined,
  FireOutlined, ThunderboltOutlined, AimOutlined, RadarChartOutlined,
  FileTextOutlined, HeartOutlined, ApiOutlined, ChromeOutlined,
  SearchOutlined, ExperimentOutlined, RiseOutlined,
} from '@ant-design/icons'
import { dashboardAPI, scheduleAPI } from '../services/api'
import { formatBeijingTime } from '../utils/time'

// ══════════════════════════════════════════════════
// 帮助函数
// ══════════════════════════════════════════════════

function relativeTime(dateStr: string | null): string {
  if (!dateStr) return '—'
  const now = new Date()
  const d = new Date(dateStr)
  const diff = Math.floor((now.getTime() - d.getTime()) / 1000)
  if (diff < 60) return '刚刚'
  if (diff < 3600) return `${Math.floor(diff / 60)}m`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h`
  if (diff < 604800) return `${Math.floor(diff / 86400)}d`
  return dateStr
}

function sanitizeContent(html: string): string {
  if (!html) return ''
  let clean = html.replace(/<(script|iframe|style|object|embed)\b[^>]*>[\s\S]*?<\/\1>/gi, '')
  clean = clean.replace(/\s+on\w+\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+)/gi, '')
  clean = clean.replace(/<img\b/gi, '<img style="width:1.2em;height:1.2em;vertical-align:text-bottom;"')
  clean = clean.replace(/<a\b/gi, '<a target="_blank" rel="noopener noreferrer"')
  return clean
}

function cleanSummary(text: string | null | undefined): string {
  if (!text) return ''
  return text
    .replace(/<think>[\s\S]*?<\/think>/g, '')
    .replace(/<think>[\s\S]*/g, '')
    .replace(/<\/think>/g, '')
    .replace(/\*\*/g, '')
    .replace(/^#+\s*/gm, '')
    .trim()
}

const PLATFORM_CONFIG: Record<string, { label: string; color: string; cssClass: string }> = {
  x:            { label: 'X',        color: '#1DA1F2', cssClass: 'cb-x' },
  youtube:      { label: 'YouTube',  color: '#FF0000', cssClass: 'cb-yt' },
  xiaohongshu:  { label: '小红书',   color: '#FE2C55', cssClass: 'cb-rb' },
  douyin:       { label: '抖音',     color: '#FFFFFF', cssClass: 'cb-dy' },
  weibo:        { label: '微博',     color: '#E6162D', cssClass: 'cb-wb' },
  bilibili:     { label: 'B站',      color: '#00A1D6', cssClass: 'cb-bl' },
  reddit:       { label: 'Reddit',   color: '#FF4500', cssClass: 'cb-rd' },
  toutiao:      { label: '头条',     color: '#E13F2E', cssClass: 'cb-tt' },
  website:      { label: '网站',     color: '#6495ED', cssClass: 'cb-ws' },
}

// ══════════════════════════════════════════════════
// KPI 环形卡片
// ══════════════════════════════════════════════════

interface KpiDef {
  key: string
  label: string
  icon: React.ReactNode
  variant: 'green' | 'amber' | 'cyan' | 'rose' | 'purple'
}

const KPI_RING_MAP: Record<string, { dash: string; offset: number }> = {
  green:  { dash: '100 26', offset: 126 },
  amber:  { dash: '80 46',  offset: 126 },
  cyan:   { dash: '70 56',  offset: 126 },
  rose:   { dash: '50 76',  offset: 126 },
  purple: { dash: '90 36',  offset: 126 },
}

function KpiCard({ def, value, delay }: { def: KpiDef; value: number; delay: number }) {
  const v = def.variant
  const ring = KPI_RING_MAP[v]
  const [display, setDisplay] = useState(0)

  useEffect(() => {
    let raf: number
    const step = Math.max(1, Math.floor(value / 40))
    const animate = () => {
      setDisplay(prev => {
        const next = Math.min(value, prev + step)
        if (next >= value) return value
        raf = requestAnimationFrame(animate)
        return next
      })
    }
    raf = requestAnimationFrame(animate)
    return () => cancelAnimationFrame(raf)
  }, [value])

  return (
    <div
      className={`cockpit-kpi cockpit-kpi--${v}`}
      style={{ animationDelay: `${delay * 0.06}s` }}
    >
      <div className="cockpit-kpi__accent" />
      <div className="cockpit-kpi__header">
        <span className="cockpit-kpi__label">{def.label}</span>
        <div className="cockpit-kpi__icon">{def.icon}</div>
      </div>
      <div className="cockpit-kpi__value">{display}</div>
      <svg className="cockpit-kpi__ring" width="48" height="48" viewBox="0 0 48 48">
        <circle cx="24" cy="24" r="20" fill="none" stroke="currentColor" opacity="0.08" strokeWidth="3" />
        <circle cx="24" cy="24" r="20" fill="none" stroke="currentColor" strokeWidth="3"
          strokeDasharray={ring.dash} strokeLinecap="round"
          transform="rotate(-90 24 24)" opacity="0.5" />
      </svg>
    </div>
  )
}

// ══════════════════════════════════════════════════
// 平台监控项（增强版）
// ══════════════════════════════════════════════════

function PlatformItem({ platform, name, count, successCount, totalCount, status }: {
  platform: string; name: string; count: number; successCount: number; totalCount: number; status: 'online' | 'degraded' | 'offline'
}) {
  const successRate = totalCount > 0 ? Math.round((successCount / totalCount) * 100) : 0

  return (
    <div className="cockpit-platform-item">
      <div className={`cockpit-platform-item__dot cockpit-platform-item__dot--${status}`}>
        <div className="cockpit-platform-item__dot-ring" />
      </div>
      <div className="cockpit-platform-item__info">
        <div className="cockpit-platform-item__name">{name}</div>
        <div className="cockpit-platform-item__meta-row">
          <span className="cockpit-platform-item__rate">{successRate}% SR</span>
        </div>
        <div className="cockpit-platform-item__mini-bar">
          <div className="cockpit-platform-item__mini-fill" style={{
            width: `${successRate}%`,
            background: status === 'online'
              ? 'linear-gradient(90deg, #22C55E, #22C55E88)'
              : status === 'degraded'
              ? 'linear-gradient(90deg, #F59E0B, #F59E0B88)'
              : 'linear-gradient(90deg, #EF4444, #EF444488)',
          }} />
        </div>
      </div>
      <div className="cockpit-platform-item__count">{count}</div>
    </div>
  )
}

// ══════════════════════════════════════════════════
// 24H 监测趋势 (真实数据 SVG)
// ══════════════════════════════════════════════════

function TrendChart({ trendData }: { trendData: { date: string; total: number; success: number; failed: number }[] }) {
  const svgW = 600; const svgH = 160; const padX = 20; const padY = 16
  const plotW = svgW - padX * 2; const plotH = svgH - padY * 2

  const maxVal = Math.max(...trendData.map(d => d.total), 1)

  // success area + line
  const successPath = trendData.map((d, i) => {
    const x = padX + (i / Math.max(trendData.length - 1, 1)) * plotW
    const y = padY + (1 - d.success / maxVal) * plotH
    return `${i === 0 ? 'M' : 'L'}${x},${y}`
  }).join(' ')

  const successArea = successPath + ` L${padX + plotW},${svgH - padY} L${padX},${svgH - padY} Z`

  // failed line
  const failedPath = trendData.map((d, i) => {
    const x = padX + (i / Math.max(trendData.length - 1, 1)) * plotW
    const y = padY + (1 - d.failed / maxVal) * plotH
    return `${i === 0 ? 'M' : 'L'}${x},${y}`
  }).join(' ')

  return (
    <svg width="100%" height="100%" viewBox={`0 0 ${svgW} ${svgH}`} preserveAspectRatio="none" style={{ display: 'block' }}>
      {/* grid lines */}
      {[0.25, 0.5, 0.75].map(r => (
        <line key={r} x1="0" y1={padY + r * plotH} x2={svgW} y2={padY + r * plotH}
          stroke="rgba(255,255,255,0.03)" strokeWidth="1" />
      ))}

      {/* gradient defs */}
      <defs>
        <linearGradient id="trend-success-grad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#22C55E" stopOpacity="0.2" />
          <stop offset="100%" stopColor="#22C55E" stopOpacity="0" />
        </linearGradient>
        <linearGradient id="trend-failed-grad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#EF4444" stopOpacity="0.12" />
          <stop offset="100%" stopColor="#EF4444" stopOpacity="0" />
        </linearGradient>
      </defs>

      {/* success area + line */}
      <path d={successArea} fill="url(#trend-success-grad)" />
      <path d={successPath} fill="none" stroke="#22C55E" strokeWidth="2" opacity="0.7" />

      {/* failed line (thin, dashed) */}
      <path d={failedPath} fill="none" stroke="#EF4444" strokeWidth="1.5" strokeDasharray="4 3" opacity="0.5" />

      {/* date labels */}
      {trendData.map((d, i) => {
        if (i % 2 !== 0) return null
        const x = padX + (i / Math.max(trendData.length - 1, 1)) * plotW
        return (
          <text key={i} x={x} y={svgH - 4} textAnchor="middle"
            fill="var(--cockpit-text-dim)" fontSize="9" fontFamily="var(--font-mono)">
            {d.date}
          </text>
        )
      })}
    </svg>
  )
}

// ══════════════════════════════════════════════════
// 平台分布环形图（SVG Donut）
// ══════════════════════════════════════════════════

function PlatformDonut({ items }: { items: { label: string; color: string; value: number }[] }) {
  const SIZE = 120; const CX = SIZE / 2; const CY = SIZE / 2
  const OUTER_R = 52; const INNER_R = 34
  const total = items.reduce((s, i) => s + i.value, 0) || 1

  // 科技感冷色配色 (取代原来的平台原生配色)
  const DONUT_COLORS = ['#22C55E', '#06B6D4', '#8B5CF6', '#60A5FA', '#2DD4BF', '#F59E0B']

  let cumulativeAngle = -Math.PI / 2
  const slices = items.map((item, idx) => {
    const sliceAngle = (item.value / total) * Math.PI * 2
    const startAngle = cumulativeAngle
    cumulativeAngle += sliceAngle

    const x1 = CX + OUTER_R * Math.cos(startAngle)
    const y1 = CY + OUTER_R * Math.sin(startAngle)
    const x2 = CX + OUTER_R * Math.cos(startAngle + sliceAngle)
    const y2 = CY + OUTER_R * Math.sin(startAngle + sliceAngle)
    const x3 = CX + INNER_R * Math.cos(startAngle + sliceAngle)
    const y3 = CY + INNER_R * Math.sin(startAngle + sliceAngle)
    const x4 = CX + INNER_R * Math.cos(startAngle)
    const y4 = CY + INNER_R * Math.sin(startAngle)

    const large = sliceAngle > Math.PI ? 1 : 0
    const d = [
      `M ${x1} ${y1}`,
      `A ${OUTER_R} ${OUTER_R} 0 ${large} 1 ${x2} ${y2}`,
      `L ${x3} ${y3}`,
      `A ${INNER_R} ${INNER_R} 0 ${large} 0 ${x4} ${y4}`,
      'Z',
    ].join(' ')
    const color = DONUT_COLORS[idx % DONUT_COLORS.length]

    return { ...item, d, color }
  })

  return (
    <div className="cockpit-donut cockpit-donut--compact">
      <svg width={SIZE} height={SIZE} viewBox={`0 0 ${SIZE} ${SIZE}`} className="cockpit-donut__svg">
        <circle cx={CX} cy={CY} r={OUTER_R} fill="none" stroke="rgba(255,255,255,0.04)" strokeWidth="4" />
        <circle cx={CX} cy={CY} r={INNER_R} fill="none" stroke="rgba(255,255,255,0.04)" strokeWidth="4" />
        {slices.map((s, i) => (
          <g key={s.label} className="cockpit-donut__slice">
            <path d={s.d} fill={s.color} opacity="0.82" style={{ transition: 'opacity 0.3s ease' }} />
            <path d={s.d} fill="url(#donut-shine)" style={{ mixBlendMode: 'overlay' as any, pointerEvents: 'none' }} />
          </g>
        ))}
        <defs>
          <linearGradient id="donut-shine" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#ffffff" stopOpacity="0.18" />
            <stop offset="40%" stopColor="#ffffff" stopOpacity="0.03" />
            <stop offset="100%" stopColor="#000000" stopOpacity="0.12" />
          </linearGradient>
        </defs>
        <text x={CX} y={CY - 2} textAnchor="middle"
          fill="var(--cockpit-text-primary)" fontSize="18" fontWeight="700"
          fontFamily="'Orbitron', var(--font-display), sans-serif" letterSpacing="1">
          {total}
        </text>
        <text x={CX} y={CY + 12} textAnchor="middle"
          fill="var(--cockpit-text-muted)" fontSize="8" fontWeight="600"
          fontFamily="var(--font-mono)" letterSpacing="1.5">
          EVENTS
        </text>
      </svg>
      <div className="cockpit-donut__legend">
        {items.slice(0, 6).map((item, idx) => {
          const pct = Math.round((item.value / total) * 100)
          const color = DONUT_COLORS[idx % DONUT_COLORS.length]
          return (
            <div className="cockpit-donut__legend-item" key={item.label}>
              <span className="cockpit-donut__legend-dot" style={{ background: color, boxShadow: `0 0 6px ${color}50` }} />
              <span className="cockpit-donut__legend-label">{item.label}</span>
              <span className="cockpit-donut__legend-value">{item.value}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ══════════════════════════════════════════════════
// 实时热点 TOP5 面板
// ══════════════════════════════════════════════════

function HotTopicsPanel({ topics }: { topics: { title: string; platform: string; platform_label: string; hot_value: number | null; rank: number | null; url: string | null }[] }) {
  if (!topics || topics.length === 0) {
    return (
      <div className="cockpit-panel">
        <div className="cockpit-panel__head">
          <div className="cockpit-panel__title">
            <span className="cockpit-panel__title-dot" style={{ background: 'var(--cockpit-rose)', boxShadow: '0 0 6px rgba(244,63,94,0.4)' }} />
            实时热点 TOP5
          </div>
          <span className="cockpit-panel__badge">HOT TOPICS</span>
        </div>
        <div className="cockpit-panel__body">
          <div className="cockpit-empty">暂无热点数据</div>
        </div>
      </div>
    )
  }

  return (
    <div className="cockpit-panel">
      <div className="cockpit-panel__head">
        <div className="cockpit-panel__title">
          <span className="cockpit-panel__title-dot" style={{ background: 'var(--cockpit-rose)', boxShadow: '0 0 6px rgba(244,63,94,0.4)' }} />
          实时热点 TOP5
        </div>
        <span className="cockpit-panel__badge">{topics.length} TOPICS</span>
      </div>
      <div className="cockpit-panel__body">
        <div className="cockpit-hot-list">
          {topics.map((topic, idx) => {
            const cfg = PLATFORM_CONFIG[topic.platform] || PLATFORM_CONFIG.website
            return (
              <a key={idx} className="cockpit-hot-item"
                href={topic.url || '#'}
                target="_blank" rel="noopener noreferrer"
              >
                <div className="cockpit-hot-item__rank" style={{
                  color: idx < 3 ? ['#FFD700', '#C0C0C0', '#CD7F32'][idx] : 'var(--cockpit-text-dim)',
                }}>
                  {idx + 1}
                </div>
                <div className="cockpit-hot-item__content">
                  <div className="cockpit-hot-item__title">{topic.title}</div>
                  <div className="cockpit-hot-item__meta">
                    <span className={`cockpit-platform-badge ${cfg.cssClass}`} style={{ fontSize: 9, padding: '1px 6px' }}>
                      {topic.platform_label}
                    </span>
                    {topic.hot_value != null && (
                      <span className="cockpit-hot-item__heat">
                        <RiseOutlined style={{ fontSize: 9 }} /> {topic.hot_value}
                      </span>
                    )}
                  </div>
                </div>
              </a>
            )
          })}
        </div>
      </div>
    </div>
  )
}

// ══════════════════════════════════════════════════
// 系统健康 & 舆情概况面板
// ══════════════════════════════════════════════════

function SystemHealthPanel({ health, sentiment, intelligence }: {
  health: { opencli_installed: boolean; opencli_running: boolean; cdp_connected: boolean; ai_provider: string; ai_model: string }
  sentiment: { total_tasks: number; total_posts: number; this_week_tasks: number }
  intelligence: { total_reports: number; in_progress: number; completed: number }
}) {
  // 惰性加载网络依赖的健康状态
  const [liveHealth, setLiveHealth] = useState<{
    opencli_installed: boolean; opencli_running: boolean; cdp_connected: boolean
  } | null>(null)

  useEffect(() => {
    let cancelled = false
    dashboardAPI.health().then(res => {
      if (!cancelled && res.data) {
        setLiveHealth({
          opencli_installed: res.data.opencli_installed,
          opencli_running: res.data.opencli_running,
          cdp_connected: res.data.cdp_connected,
        })
      }
    }).catch(() => {})
    return () => { cancelled = true }
  }, [])

  const opencliRunning = liveHealth?.opencli_running ?? health.opencli_running
  const opencliInstalled = liveHealth?.opencli_installed ?? health.opencli_installed
  const cdpConnected = liveHealth?.cdp_connected ?? health.cdp_connected

  const healthItems = [
    { label: 'OpenCLI', running: opencliRunning, installed: opencliInstalled, loading: !liveHealth },
    { label: 'Chrome CDP', running: cdpConnected, installed: cdpConnected, loading: !liveHealth },
    { label: `AI: ${health.ai_provider || 'N/A'}`, running: !!health.ai_provider, installed: !!health.ai_provider, detail: health.ai_model, loading: false },
  ]

  return (
    <div className="cockpit-panel">
      <div className="cockpit-panel__head">
        <div className="cockpit-panel__title">
          <span className="cockpit-panel__title-dot" style={{ background: 'var(--cockpit-cyan)', boxShadow: '0 0 6px rgba(6,182,212,0.4)' }} />
          系统健康 & 舆情概况
        </div>
        <span className="cockpit-panel__badge">STATUS</span>
      </div>
      <div className="cockpit-panel__body">
        {/* 系统组件状态 */}
        <div className="cockpit-sub-header" style={{ marginBottom: 10 }}>
          <span>系统组件</span>
        </div>
        <div className="cockpit-health-grid">
          {healthItems.map(item => (
            <div key={item.label} className="cockpit-health-item">
              <div className={`cockpit-health-item__dot ${item.running ? 'cockpit-health-item__dot--on' : 'cockpit-health-item__dot--off'}`} />
              <div className="cockpit-health-item__info">
                <span className="cockpit-health-item__label">{item.label}</span>
                {item.detail && <span className="cockpit-health-item__detail">{item.detail}</span>}
              </div>
              <span className={`cockpit-health-item__state ${item.running ? 'cockpit-health-item__state--on' : 'cockpit-health-item__state--off'}`}>
                {item.loading ? '···' : item.running ? '● ON' : '○ OFF'}
              </span>
            </div>
          ))}
        </div>

        {/* 舆情 + 情报统计 */}
        <div className="cockpit-sub-header" style={{ marginTop: 18, marginBottom: 10 }}>
          <span>数据概览</span>
        </div>
        <div className="cockpit-stats-mini-grid">
          <div className="cockpit-stat-mini">
            <SearchOutlined style={{ color: 'var(--cockpit-accent)', fontSize: 14 }} />
            <div className="cockpit-stat-mini__value">{sentiment.total_tasks}</div>
            <div className="cockpit-stat-mini__label">舆情任务</div>
          </div>
          <div className="cockpit-stat-mini">
            <FileTextOutlined style={{ color: 'var(--cockpit-purple)', fontSize: 14 }} />
            <div className="cockpit-stat-mini__value">{sentiment.total_posts}</div>
            <div className="cockpit-stat-mini__label">采集帖子</div>
          </div>
          <div className="cockpit-stat-mini">
            <ExperimentOutlined style={{ color: 'var(--cockpit-cyan)', fontSize: 14 }} />
            <div className="cockpit-stat-mini__value">{intelligence.total_reports}</div>
            <div className="cockpit-stat-mini__label">情报报告</div>
          </div>
          <div className="cockpit-stat-mini">
            <RiseOutlined style={{ color: 'var(--cockpit-amber)', fontSize: 14 }} />
            <div className="cockpit-stat-mini__value">{intelligence.in_progress}</div>
            <div className="cockpit-stat-mini__label">进行中</div>
          </div>
        </div>
        {intelligence.in_progress > 0 && (
          <div className="cockpit-progress-note">
            <span className="cockpit-progress-note__dot" />
            {intelligence.in_progress} 份情报报告正在生成中...
          </div>
        )}
      </div>
    </div>
  )
}

// ══════════════════════════════════════════════════
// 信号馈送条目
// ══════════════════════════════════════════════════

function FeedItem({ record, idx }: { record: any; idx: number }) {
  const [expanded, setExpanded] = useState(false)
  const cfg = PLATFORM_CONFIG[record.platform] || PLATFORM_CONFIG.website
  const cleaned = cleanSummary(record.summary)

  const statusClass = `feed-status--${record.status}`
  const statusLabel: string = ({ success: 'SUCCESS', failed: 'FAILED', pending: 'PENDING' } as Record<string, string>)[record.status] || 'PENDING'

  let posts: any[] = []
  if (record.raw_content) {
    try {
      const parsed = JSON.parse(record.raw_content)
      if (Array.isArray(parsed)) posts = parsed
    } catch { /* ignore */ }
  }

  return (
    <div
      className={`cockpit-feed-item${expanded ? ' cockpit-feed-item--expanded' : ''}`}
      style={{ animationDelay: `${idx * 0.04}s` }}
      onClick={() => setExpanded(!expanded)}
    >
      <div className="cockpit-feed-item__timeline">
        <span className="cockpit-feed-item__time">
          {record.created_at ? record.created_at.slice(11, 19) : '--:--:--'}
        </span>
        <div className="cockpit-feed-item__dot-line" />
      </div>
      <span className={`cockpit-platform-badge ${cfg.cssClass}`}>
        {cfg.label}
      </span>
      <div className="cockpit-feed-item__body">
        <div className="cockpit-feed-item__target">
          {record.target_name}
          {record.target_url && (
            <a href={record.target_url} target="_blank" rel="noopener noreferrer"
              className="cockpit-feed-item__link" onClick={e => e.stopPropagation()}>
              ↗
            </a>
          )}
          <span className="cockpit-feed-item__expand-hint">
            {expanded ? '收起 ▴' : '展开 ▾'}
          </span>
        </div>

        {!expanded && cleaned && (
          <div className="cockpit-feed-item__summary">{cleaned}</div>
        )}
        {!expanded && !cleaned && record.status === 'pending' && (
          <div className="cockpit-feed-item__summary" style={{ opacity: 0.5 }}>正在分析中...</div>
        )}

        {expanded && (
          <div className="cockpit-feed-item__detail">
            {cleaned ? (
              <div className="cockpit-feed-detail__ai">
                <div className="cockpit-feed-detail__ai-head">
                  <RobotOutlined style={{ color: 'var(--cockpit-accent)', fontSize: 12 }} />
                  <span>AI 分析</span>
                </div>
                <div className="cockpit-feed-detail__ai-body">{cleaned}</div>
              </div>
            ) : (
              <div className="cockpit-feed-detail__ai" style={{ opacity: 0.5, fontStyle: 'italic' }}>
                {record.status === 'pending' ? '正在分析中...' : '暂无总结'}
              </div>
            )}

            {posts.length > 0 && (
              <div className="cockpit-feed-detail__posts">
                <div className="cockpit-feed-detail__posts-head">
                  <FileTextOutlined style={{ color: 'var(--cockpit-accent)', fontSize: 12 }} />
                  <span>贴文内容</span>
                  <span className="cockpit-feed-detail__badge">{posts.length}</span>
                </div>
                <div className="cockpit-feed-detail__posts-list">
                  {posts.map((post: any, i: number) => (
                    <div key={i} className="cockpit-feed-post-card">
                      {(post.author_name || post.author_avatar) && (
                        <div className="cockpit-feed-post-card__author">
                          {post.author_avatar && (
                            <img src={post.author_avatar} alt={post.author_name}
                              className="cockpit-feed-post-card__avatar" />
                          )}
                          {post.author_name && <span>{post.author_name}</span>}
                        </div>
                      )}
                      <div className="cockpit-feed-post-card__header">
                        {post.title && (
                          <span className="cockpit-feed-post-card__title"
                            dangerouslySetInnerHTML={{ __html: sanitizeContent(post.title) }} />
                        )}
                        <div className="cockpit-feed-post-card__meta">
                          {post.published_at && (
                            <span className="cockpit-feed-post-card__time">{formatBeijingTime(post.published_at)}</span>
                          )}
                          {post.likes > 0 && (
                            <span className="cockpit-feed-post-card__stat"><HeartOutlined /> {post.likes}</span>
                          )}
                          {post.comments_count > 0 && (
                            <span className="cockpit-feed-post-card__stat">{post.comments_count} 评论</span>
                          )}
                        </div>
                      </div>
                      {post.content && (
                        <div className="cockpit-feed-post-card__content"
                          dangerouslySetInnerHTML={{ __html: sanitizeContent(post.content) }} />
                      )}
                      {post.url && (
                        <a href={post.url} target="_blank" rel="noopener noreferrer"
                          className="cockpit-feed-post-card__link" onClick={e => e.stopPropagation()}>
                          查看原文 ↗
                        </a>
                      )}
                      {post.images && post.images.length > 0 && (
                        <div className="cockpit-feed-post-card__images">
                          <Image.PreviewGroup>
                            {post.images.slice(0, 9).map((url: string, imgIdx: number) => (
                              <Image key={imgIdx} src={url} width={72} height={72}
                                style={{ objectFit: 'cover', borderRadius: 6 }}
                                fallback="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAACklEQVR4nGMAAQAABQABDQottAAAAABJRU5ErkJggg==" />
                            ))}
                          </Image.PreviewGroup>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
      <span className={`cockpit-feed-status ${statusClass}`}>
        {statusLabel}
      </span>
    </div>
  )
}

// ══════════════════════════════════════════════════
// 主页面组件
// ══════════════════════════════════════════════════

const KPI_DEFS: KpiDef[] = [
  { key: 'total_targets',   label: '监测目标', icon: <AimOutlined />,             variant: 'green' },
  { key: 'active_targets',  label: '活跃目标', icon: <ThunderboltOutlined />,     variant: 'amber' },
  { key: 'total_websites',  label: '网站监测', icon: <GlobalOutlined />,          variant: 'cyan' },
  { key: 'today_results',   label: '今日监测', icon: <ClockCircleOutlined />,     variant: 'green' },
  { key: 'today_success',   label: '成功',      icon: <CheckCircleOutlined />,    variant: 'purple' },
  { key: 'today_failed',    label: '失败',      icon: <CloseCircleOutlined />,    variant: 'rose' },
]

export default function CockpitPage() {
  const [data, setData] = useState<any>(null)
  const [overview, setOverview] = useState<any>(null)
  const [jobData, setJobData] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [uptimeSeconds, setUptimeSeconds] = useState(0)
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // 运行时间计时器
  useEffect(() => {
    const timer = setInterval(() => setUptimeSeconds(s => s + 1), 1000)
    return () => clearInterval(timer)
  }, [])

  const formatUptime = (s: number) => {
    const h = String(Math.floor(s / 3600)).padStart(2, '0')
    const m = String(Math.floor((s % 3600) / 60)).padStart(2, '0')
    const sec = String(s % 60).padStart(2, '0')
    return `${h}:${m}:${sec}`
  }

  // 时钟
  const [clock, setClock] = useState('')
  useEffect(() => {
    const tick = () => {
      const now = new Date()
      setClock(now.toLocaleTimeString('zh-CN', { hour12: false }) + ' · ' +
        now.toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' }).replace(/\//g, '-'))
    }
    tick()
    const t = setInterval(tick, 1000)
    return () => clearInterval(t)
  }, [])

  const stopPolling = useCallback(() => {
    if (pollingRef.current) { clearInterval(pollingRef.current); pollingRef.current = null }
  }, [])

  const fetchData = useCallback(async (isPoll = false) => {
    if (!isPoll) setLoading(true)
    try {
      const [dashRes, overviewRes, schedRes] = await Promise.all([
        dashboardAPI.get(),
        dashboardAPI.overview().catch(() => ({ data: null })),
        scheduleAPI.status().catch(() => ({ data: { jobs: [] } })),
      ])
      setData(dashRes.data)
      setOverview(overviewRes.data)
      setJobData(schedRes.data?.jobs || [])
      const hasPending = dashRes.data?.recent_results?.some((r: any) => r.status === 'pending')
      if (hasPending && !pollingRef.current) {
        pollingRef.current = setInterval(() => fetchData(true), 5000)
      } else if (!hasPending) {
        stopPolling()
      }
    } catch { /* 静默失败 */ } finally {
      if (!isPoll) setLoading(false)
    }
  }, [stopPolling])

  useEffect(() => { fetchData(); return stopPolling }, [])

  if (loading) {
    return (
      <div style={{ padding: '40px' }}>
        <Skeleton.Input active style={{ width: 260, height: 48, borderRadius: 8, marginBottom: 24 }} />
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', gap: 16, marginBottom: 32 }}>
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} style={{ background: 'var(--cockpit-bg-card)', border: '1px solid #1E293B', borderRadius: 16, padding: '22px 20px', height: 140 }}>
              <Skeleton.Input active size="small" style={{ width: 70, marginBottom: 16 }} />
              <Skeleton.Input active style={{ width: 50, height: 38 }} />
            </div>
          ))}
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} style={{ background: 'var(--cockpit-bg-card)', border: '1px solid #1E293B', borderRadius: 20, height: 300 }} />
          ))}
        </div>
      </div>
    )
  }

  if (!data) return null

  const { stats, recent_results, trend_data } = data
  const overviewData = overview || {
    hot_topics: [],
    sentiment: { total_tasks: 0, total_posts: 0, this_week_tasks: 0 },
    intelligence: { total_reports: 0, in_progress: 0, completed: 0 },
    system_health: { opencli_installed: false, opencli_running: false, cdp_connected: false, ai_provider: '', ai_model: '' },
  }

  // 平台统计
  const platformMap = new Map<string, { name: string; count: number; success: number; status: 'online' | 'degraded' | 'offline' }>()
  recent_results.forEach((r: any) => {
    const p = r.platform || 'website'
    if (!platformMap.has(p)) {
      platformMap.set(p, { name: PLATFORM_CONFIG[p]?.label || p, count: 0, success: 0, status: 'online' })
    }
    const entry = platformMap.get(p)!
    entry.count++
    if (r.status === 'success') entry.success++
  })
  platformMap.forEach(entry => {
    if (entry.count === 0) entry.status = 'offline'
    else if (entry.success / entry.count < 0.5) entry.status = 'degraded'
    else entry.status = 'online'
  })

  const platforms = Array.from(platformMap.entries()).slice(0, 6)
  const totalPlatformResults = Array.from(platformMap.values()).reduce((sum, v) => sum + v.count, 0)

  // 平台分布
  const platformBars = Array.from(platformMap.entries()).map(([key, val]) => ({
    label: PLATFORM_CONFIG[key]?.label || key,
    color: PLATFORM_CONFIG[key]?.color || '#6495ED',
    value: val.count,
  })).sort((a, b) => b.value - a.value)

  const runningJobs = jobData.filter((j: any) => j.next_run_time)
  const hasRunningJobs = runningJobs.length > 0

  return (
    <div className="cockpit-root">
      {/* ═══ 背景层 ═══ */}
      <div className="cockpit-bg-grid" />
      <div className="cockpit-ambient cockpit-ambient--top" />
      <div className="cockpit-ambient cockpit-ambient--bottom" />

      {/* ═══ 顶部状态栏 ═══ */}
      <div className="cockpit-topbar">
        <div className="cockpit-topbar__title">
          <span style={{ color: 'var(--cockpit-accent)' }}>◆</span> INTEL <span style={{ color: 'var(--cockpit-accent)' }}>COCKPIT</span>
        </div>
        <div className="cockpit-topbar__meta">
          <div className="cockpit-topbar__status">
            <div className="cockpit-topbar__status-dot" />
            SYSTEM OPERATIONAL
          </div>
          <div className="cockpit-topbar__clock">{clock}</div>
        </div>
      </div>

      {/* ═══ KPI 卡片 ═══ */}
      <div className="cockpit-section-header">
        <span>◈</span>
        <span>实时指标 · LIVE METRICS</span>
        <span className="cockpit-section-header__line" />
      </div>

      <div className="cockpit-kpi-grid">
        {KPI_DEFS.map((def, idx) => (
          <KpiCard key={def.key} def={def} value={stats[def.key] || 0} delay={idx + 1} />
        ))}
      </div>

      {/* ═══ 内容网格：新布局 ═══ */}
      <div className="cockpit-content-grid">
        {/* ── 左上：平台监测状态 ── */}
        <div className="cockpit-panel">
          <div className="cockpit-panel__head">
            <div className="cockpit-panel__title">
              <span className="cockpit-panel__title-dot" />
              平台监测状态
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <div className="cockpit-platform-live-indicator">
                <span className="cockpit-platform-live-indicator__dot" />
                <span className="cockpit-platform-live-indicator__label">LIVE</span>
              </div>
              <span className="cockpit-panel__badge">{platforms.length} ACTIVE</span>
            </div>
          </div>
          <div className="cockpit-panel__body cockpit-panel__body--compact">
            {/* 平台摘要条 + 环形图并排 */}
            <div className="cockpit-platform-top-row">
              <div className="cockpit-platform-summary cockpit-platform-summary--compact">
                <div className="cockpit-platform-summary__item">
                  <span className="cockpit-platform-summary__value">{platforms.length}</span>
                  <span className="cockpit-platform-summary__label">Platforms</span>
                </div>
                <div className="cockpit-platform-summary__divider" />
                <div className="cockpit-platform-summary__item">
                  <span className="cockpit-platform-summary__value">{totalPlatformResults}</span>
                  <span className="cockpit-platform-summary__label">Events</span>
                </div>
                <div className="cockpit-platform-summary__divider" />
                <div className="cockpit-platform-summary__item">
                  <span className="cockpit-platform-summary__value" style={{ color: 'var(--cockpit-accent)' }}>
                    {totalPlatformResults > 0
                      ? Math.round((Array.from(platformMap.values()).reduce((s, v) => s + v.success, 0) / totalPlatformResults) * 100)
                      : 0}%
                  </span>
                  <span className="cockpit-platform-summary__label">Success</span>
                </div>
              </div>
              <div className="cockpit-platform-donut-wrap">
                <PlatformDonut items={platformBars.length > 0 ? platformBars : [{ label: '', color: '#22C55E', value: 1 }]} />
              </div>
            </div>

            {/* 平台网格 */}
            <div className="cockpit-platform-grid">
              {platforms.length > 0 ? platforms.map(([key, val]) => (
                <PlatformItem key={key} platform={key} name={val.name}
                  count={val.count} successCount={val.success} totalCount={val.count}
                  status={val.status} />
              )) : (
                <div style={{ gridColumn: '1/-1', textAlign: 'center', padding: 40, color: 'var(--cockpit-text-muted)', fontSize: 13 }}>
                  暂无平台数据
                </div>
              )}
            </div>

            {/* 7日趋势图 */}
            <div className="cockpit-trend-section">
              <div className="cockpit-sub-header">
                <span>7日监测趋势</span>
                <div className="cockpit-legend">
                  <div className="cockpit-legend__item">
                    <div className="cockpit-legend__line" style={{ background: 'var(--cockpit-accent)' }} /> 成功
                  </div>
                  <div className="cockpit-legend__item">
                    <div className="cockpit-legend__line" style={{ background: 'var(--cockpit-danger)' }} /> 失败
                  </div>
                </div>
              </div>
              <div className="cockpit-chart-wrap cockpit-chart-wrap--compact">
                {trend_data && trend_data.length > 0 ? (
                  <TrendChart trendData={trend_data} />
                ) : (
                  <div className="cockpit-empty" style={{ padding: '40px 0' }}>暂无趋势数据</div>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* ── 右上：系统健康 & 舆情概况 ── */}
        <SystemHealthPanel
          health={overviewData.system_health || { opencli_installed: false, opencli_running: false, cdp_connected: false, ai_provider: '', ai_model: '' }}
          sentiment={overviewData.sentiment || { total_tasks: 0, total_posts: 0, this_week_tasks: 0 }}
          intelligence={overviewData.intelligence || { total_reports: 0, in_progress: 0, completed: 0 }}
        />

        {/* ── 全宽：信号馈送 ── */}
        <div className="cockpit-panel cockpit-panel--full">
          <div className="cockpit-panel__head">
            <div className="cockpit-panel__title">
              <span className="cockpit-panel__title-dot" />
              最近监测结果 · SIGNAL FEED
            </div>
            <span className="cockpit-panel__badge">{recent_results.length} RESULTS</span>
          </div>
          <div className="cockpit-panel__body">
            {recent_results.length > 0 ? (
              <div className="cockpit-feed-list">
                {recent_results.map((record: any, idx: number) => (
                  <FeedItem key={record.id} record={record} idx={idx} />
                ))}
              </div>
            ) : (
              <div className="cockpit-empty">暂无监测结果</div>
            )}
          </div>
        </div>
      </div>

      {/* ═══ 底部状态栏 ═══ */}
      <div className="cockpit-statusbar">
        <div className="cockpit-statusbar__item">
          <span>SYS.ID</span>
          <span className="cockpit-statusbar__value">IM-COCKPIT-01</span>
        </div>
        <div className="cockpit-statusbar__item">
          <span>UPTIME</span>
          <span className="cockpit-statusbar__value">{formatUptime(uptimeSeconds)}</span>
        </div>
        <div className="cockpit-statusbar__item">
          <span>AI ENGINE</span>
          <span className="cockpit-statusbar__value">
            {overviewData.system_health?.ai_provider || '—'}
          </span>
        </div>
        <div className="cockpit-statusbar__item">
          <span>TOTAL TARGETS</span>
          <span className="cockpit-statusbar__value">{stats.total_targets}</span>
        </div>
        <div className="cockpit-statusbar__item">
          <span>TODAY</span>
          <span className="cockpit-statusbar__value">{stats.today_results} RESULTS</span>
        </div>
        <div className="cockpit-statusbar__item">
          <span>SUCCESS RATE</span>
          <span className="cockpit-statusbar__value">
            {stats.today_results > 0
              ? `${Math.round((stats.today_success / stats.today_results) * 100)}%`
              : '—'}
          </span>
        </div>
      </div>
    </div>
  )
}
