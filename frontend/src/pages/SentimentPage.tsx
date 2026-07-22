import { useEffect, useState, useRef, useCallback } from 'react'
import {
  Input, Button, Tag, Space, Select, message, Skeleton, Empty, Spin, Row, Col,
  Image, Badge, Tooltip,
} from 'antd'
import {
  SearchOutlined, ClockCircleOutlined, CheckCircleOutlined,
  SyncOutlined, CloseCircleOutlined, LikeOutlined,
  MessageOutlined, ShareAltOutlined, StarOutlined,
  LinkOutlined, ThunderboltOutlined, BarChartOutlined,
  DeleteOutlined, ReloadOutlined,
} from '@ant-design/icons'
import { sentimentAPI } from '../services/api'

// ── Types ────────────────────────────────────────────────────────────────
interface PlatformInfo { platform: string; label: string; supported_metrics: string[] }
interface SentimentPost {
  id: number; task_id: number; platform: string; post_id: string
  title: string; content: string | null; url: string
  author_name: string | null; author_avatar: string | null; author_followers: number
  published_at: string | null
  views: number; likes: number; comments: number; shares: number; bookmarks: number
  metrics_partial: boolean; engagement_score: number; platform_weight: number
  time_decay: number; impact_score: number
  videos_json: string | null; images_json: string | null; comments_json: string | null; score_detail: string | null
  quoted_tweet_json: string | null; card_json: string | null
  fetched_at: string
  deep_analysis_status?: string | null
}
interface SentimentTask {
  id: number; keyword: string; platforms: string; status: string
  total_posts: number; error_log: string | null
  created_at: string; completed_at: string | null; posts?: SentimentPost[]
}

// ── Constants ────────────────────────────────────────────────────────────
const PLATFORM_COLORS: Record<string, string> = { weibo: '#e6162d', douyin: '#111', xiaohongshu: '#ff2442', toutiao: '#e53333', '108community': '#2563eb', youtube: '#FF0000', x: '#000000', facebook: '#1877F2' }
const PLATFORM_LABELS: Record<string, string> = { weibo: '微博', douyin: '抖音', xiaohongshu: '小红书', toutiao: '今日头条', '108community': '108社区', youtube: 'YouTube', x: 'X', facebook: 'Facebook' }
const STATUS_MAP: Record<string, { color: string; icon: any; text: string }> = {
  pending:   { color: '#f59e0b', icon: <ClockCircleOutlined />,   text: '等待' },
  running:   { color: '#3b82f6', icon: <SyncOutlined spin />,      text: '搜索中' },
  completed: { color: '#10b981', icon: <CheckCircleOutlined />,    text: '完成' },
  failed:    { color: '#ef4444', icon: <CloseCircleOutlined />,    text: '失败' },
}

// Radii
const R = { sm: 8, md: 12, lg: 16, xl: 20 }

// ── Helpers ──────────────────────────────────────────────────────────────
const fmt   = (n: number) => n >= 10000 ? `${(n / 10000).toFixed(1)}万` : n.toLocaleString()
const fmts  = (s: number) => s.toFixed(1)
const fmtDt = (isoString: string | null): string => {
  if (!isoString) return ''
  const date = isoString.endsWith('Z') || isoString.includes('+')
    ? new Date(isoString)
    : new Date(isoString + 'Z')
  return date.toLocaleString('zh-CN', {
    month: 'numeric', day: 'numeric',
    hour: '2-digit', minute: '2-digit',
    timeZone: 'Asia/Shanghai',
  })
}

// ── Sub-Components ───────────────────────────────────────────────────────

function ImpactBadge({ score }: { score: number }) {
  const palette = score >= 50 ? { bg: '#fef2f2', c: '#dc2626', b: '#fecaca' }
    : score >= 25 ? { bg: '#fffbeb', c: '#d97706', b: '#fde68a' }
    : score >= 10 ? { bg: '#eff6ff', c: '#2563eb', b: '#bfdbfe' }
    :               { bg: '#f8fafc', c: '#94a3b8', b: '#e2e8f0' }
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 4,
      background: palette.bg, color: palette.c, border: `1px solid ${palette.b}`,
      borderRadius: R.sm, padding: '4px 12px', fontWeight: 700,
      fontSize: 15, fontFamily: "'Fira Code', 'SF Mono', monospace",
    }}><ThunderboltOutlined style={{ fontSize: 12 }} />{fmts(score)}</span>
  )
}

function PostImages({ imagesJson }: { imagesJson: string | null }) {
  if (!imagesJson) return null
  try {
    const imgs: string[] = JSON.parse(imagesJson)
    if (!imgs.length) return null
    return (
      <div style={{ marginBottom: 10 }}>
        <Image.PreviewGroup>
          {imgs.map((src, i) => (
            <Image key={i} src={`/api/tools/proxy/image?url=${encodeURIComponent(src)}`}
              referrerPolicy="no-referrer" width={80} height={80}
              style={{ objectFit: 'cover', borderRadius: 6, marginRight: 6, marginBottom: 6 }} />
          ))}
        </Image.PreviewGroup>
      </div>
    )
  } catch { return null }
}

function PostVideos({ videosJson }: { videosJson: string | null }) {
  if (!videosJson) return null
  try {
    const videos: Array<{ url: string; play_count: string }> = JSON.parse(videosJson)
    if (!videos.length) return null
    return (
      <div style={{ marginBottom: 8 }}>
        {videos.map((v, i) => (
          <Button key={i} size="small" type="link" icon={<span>▶</span>}
            href={v.url} target="_blank" rel="noopener noreferrer"
            style={{ padding: 0, fontSize: 12 }}>{v.play_count || '播放'}</Button>
        ))}
      </div>
    )
  } catch { return null }
}

function PostContent({ title, content }: { title: string; content: string }) {
  const [open, setOpen] = useState(false)
  // Use the longer text; dedupe when content is just a truncated title
  const text = (content && content.length >= title.length) ? content : title
  if (!text) return null
  const limit = 200; const long = text.length > limit
  return (
    <div style={{ fontSize: 14, lineHeight: 1.8, color: '#334155', wordBreak: 'break-word', marginBottom: 8 }}>
      {long && !open ? text.slice(0, limit) + '…' : text}
      {long && (
        <a onClick={(e) => { e.stopPropagation(); setOpen(!open) }}
          style={{ fontSize: 13, marginLeft: 6, whiteSpace: 'nowrap', userSelect: 'none', cursor: 'pointer' }}>
          {open ? '收起 ▲' : '展开全文'}
        </a>
      )}
    </div>
  )
}

function PostComments({ commentsJson }: { commentsJson: string | null }) {
  const [open, setOpen] = useState(false)
  if (!commentsJson) return null
  try {
    const cmts: Array<{ text: string; author: string; likes: number }> = JSON.parse(commentsJson)
    if (!cmts.length) return null
    return (
      <div style={{ marginBottom: 8 }}>
        <div onClick={() => setOpen(!open)}
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 6,
            padding: '6px 14px', borderRadius: 18,
            background: open ? '#eff6ff' : '#f8fafc',
            border: `1px solid ${open ? '#93c5fd' : '#e2e8f0'}`,
            fontSize: 12, color: open ? '#2563eb' : '#64748b',
            cursor: 'pointer', userSelect: 'none',
            fontWeight: 500, transition: 'all 0.15s',
          }}>
          <MessageOutlined />热门评论 <span style={{ fontWeight: 700, color: '#3b82f6' }}>{cmts.length}</span> 条
          {open ? ' ▲' : ' ▼'}
        </div>
        {open && (
          <div style={{ marginTop: 8 }}>
            {cmts.map((c, i) => (
              <div key={i} style={{ padding: '8px 12px', marginBottom: 4, background: '#f8fafc', borderRadius: 8, fontSize: 13, lineHeight: 1.7 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 2 }}>
                  <span style={{ fontWeight: 600, color: '#334155' }}>{c.author}</span>
                  {c.likes > 0 && <span style={{ color: '#94a3b8', fontSize: 12 }}><LikeOutlined style={{ fontSize: 10 }} /> {fmt(c.likes)}</span>}
                </div>
                <div style={{ color: '#475569' }}>{c.text}</div>
              </div>
            ))}
          </div>
        )}
      </div>
    )
  } catch { return null }
}

function QuotedTweet({ quotedTweetJson }: { quotedTweetJson: string | null }) {
  if (!quotedTweetJson) return null
  try {
    const qt: { author: string; name: string; text: string; url: string } = JSON.parse(quotedTweetJson)
    if (!qt || !qt.text) return null
    return (
      <div style={{
        marginBottom: 10, padding: '10px 14px', borderRadius: 10,
        borderLeft: `3px solid #1DA1F2`, background: '#f8fafc',
        fontSize: 13, lineHeight: 1.7, color: '#475569',
      }}>
        <div style={{ marginBottom: 4, display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{ fontWeight: 600, color: '#1e293b' }}>{qt.name || `@${qt.author}`}</span>
          <span style={{ color: '#94a3b8', fontSize: 11 }}>@{qt.author}</span>
        </div>
        <div style={{ wordBreak: 'break-word' }}>
          {qt.text.length > 200 ? qt.text.slice(0, 200) + '…' : qt.text}
        </div>
        {qt.url && (
          <a href={qt.url} target="_blank" rel="noopener noreferrer"
            style={{ fontSize: 11, color: '#3b82f6', display: 'inline-block', marginTop: 4 }}>
            查看引用推文 ↗
          </a>
        )}
      </div>
    )
  } catch { return null }
}

function LinkCard({ cardJson }: { cardJson: string | null }) {
  if (!cardJson) return null
  try {
    const card: { title?: string; description?: string; url?: string; domain?: string; image_url?: string } = JSON.parse(cardJson)
    if (!card.url && !card.title) return null
    return (
      <a href={card.url || '#'} target="_blank" rel="noopener noreferrer"
        style={{
          display: 'flex', gap: 10, marginBottom: 10, padding: '10px 12px',
          borderRadius: 10, border: '1px solid #e2e8f0', background: '#f8fafc',
          textDecoration: 'none', color: 'inherit', maxWidth: 400,
        }}>
        {card.image_url && (
          <img src={card.image_url} alt="" style={{ width: 60, height: 60, borderRadius: 8, objectFit: 'cover', flexShrink: 0 }} />
        )}
        <div style={{ minWidth: 0 }}>
          {card.domain && <div style={{ fontSize: 11, color: '#94a3b8', marginBottom: 2 }}>{card.domain}</div>}
          {card.title && <div style={{ fontSize: 13, fontWeight: 600, color: '#1e293b', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{card.title}</div>}
          {card.description && <div style={{ fontSize: 12, color: '#64748b', marginTop: 2, display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>{card.description}</div>}
        </div>
      </a>
    )
  } catch { return null }
}

function DeepAnalysisButton({ post }: { post: SentimentPost }) {
  const [status, setStatus] = useState(post.deep_analysis_status || 'idle')
  const [loading, setLoading] = useState(false)

  const handleTrigger = async () => {
    setLoading(true)
    setStatus('processing')
    try {
      await sentimentAPI.triggerDeepAnalysis(post.id)
    } catch (err: any) {
      setLoading(false)
      setStatus('idle')
      return
    }
    setLoading(false)
  }

  // Poll status when processing
  useEffect(() => {
    if (status !== 'processing') return
    const timer = setInterval(async () => {
      try {
        const res = await sentimentAPI.getDeepAnalysisStatus(post.id)
        if (res.data.status === 'completed') {
          setStatus('completed')
          clearInterval(timer)
          // Refresh the page to show new content
          window.location.reload()
        } else if (res.data.status === 'failed') {
          setStatus('failed')
          clearInterval(timer)
          window.location.reload()
        }
      } catch { /* keep polling */ }
    }, 3000)
    return () => clearInterval(timer)
  }, [status, post.id])

  const styleMap: Record<string, { bg: string; border: string; color: string; text: string; hint: string }> = {
    idle: { bg: '#f8fafc', border: '#e2e8f0', color: '#64748b', text: '🎧 深度分析', hint: '下载音频+转录+AI摘要' },
    processing: { bg: '#eff6ff', border: '#93c5fd', color: '#2563eb', text: '⏳ 分析中...', hint: '下载音频 → 转录 → AI摘要' },
    completed: { bg: '#f0fdf4', border: '#86efac', color: '#16a34a', text: '✅ 深度分析已完成', hint: '页面刷新后可见' },
    failed: { bg: '#fef2f2', border: '#fecaca', color: '#dc2626', text: '❌ 深度分析失败', hint: '点击重试' },
  }
  const statusStyle = styleMap[status] || styleMap.idle

  return (
    <div style={{ marginBottom: 10 }}>
      <button
        onClick={status === 'idle' || status === 'failed' ? handleTrigger : undefined}
        disabled={loading || status === 'processing' || status === 'completed'}
        style={{
          display: 'inline-flex', alignItems: 'center', gap: 8,
          padding: '8px 18px', borderRadius: 20,
          background: statusStyle.bg, border: `1px solid ${statusStyle.border}`,
          color: statusStyle.color, fontSize: 13, fontWeight: 600,
          cursor: (status === 'idle' || status === 'failed') && !loading ? 'pointer' : 'default',
          opacity: loading || status === 'processing' ? 0.8 : 1,
          transition: 'all 0.15s',
        }}
      >
        {loading && <SyncOutlined spin />}
        <span>{statusStyle.text}</span>
        <span style={{ fontSize: 11, color: '#94a3b8', fontWeight: 400 }}>{statusStyle.hint}</span>
      </button>
    </div>
  )
}

function MetricRow({ post }: { post: SentimentPost }) {
  const items = [
    { icon: <LikeOutlined />, v: post.likes, label: '点赞' },
    { icon: <MessageOutlined />, v: post.comments, label: '评论' },
    { icon: <ShareAltOutlined />, v: post.shares, label: '转发' },
    ...(post.bookmarks > 0 ? [{ icon: <StarOutlined />, v: post.bookmarks, label: '收藏' }] : []),
  ]
  return (
    <div style={{ display: 'flex', gap: 18, fontSize: 12, color: '#64748b' }}>
      {items.map((m, i) => (
        <Tooltip key={i} title={m.label}>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>{m.icon} {fmt(m.v)}</span>
        </Tooltip>
      ))}
      <Tooltip title={`互动分:${fmts(post.engagement_score)} · 平台权重:${fmts(post.platform_weight)} · 时间衰减:${fmts(post.time_decay)}`}>
        <span style={{ color: '#94a3b8', cursor: 'help', fontSize: 11, marginLeft: 'auto' }}>评分详情</span>
      </Tooltip>
    </div>
  )
}

function KpiCard({ icon, value, label, iconBg, iconColor, valueColor }: {
  icon: React.ReactNode; value: string; label: string; iconBg: string; iconColor: string; valueColor: string
}) {
  return (
    <div style={{ flex: '1 1 140px', background: '#fff', borderRadius: R.md, padding: '14px 18px', border: '1px solid #e2e8f0' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <div style={{ width: 40, height: 40, borderRadius: 10, background: iconBg, display: 'flex', alignItems: 'center', justifyContent: 'center', color: iconColor, fontSize: 18, flexShrink: 0 }}>{icon}</div>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontSize: 20, fontWeight: 700, color: valueColor, lineHeight: 1.2 }}>{value}</div>
          <div style={{ fontSize: 11, color: '#94a3b8' }}>{label}</div>
        </div>
      </div>
    </div>
  )
}

function PulsingDot() {
  return <span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: '50%', background: '#3b82f6', marginRight: 8, animation: 'pulse2 1.5s infinite' }} />
}

// ── Main ─────────────────────────────────────────────────────────────────

export default function SentimentPage() {
  const [platforms, setPlatforms] = useState<PlatformInfo[]>([])
  const [keyword, setKeyword] = useState('')
  const [selectedPlatforms, setSelectedPlatforms] = useState<string[]>([])
  const [postLimit, setPostLimit] = useState(20)
  const [searching, setSearching] = useState(false)
  const [tasks, setTasks] = useState<SentimentTask[]>([])
  const [selectedTask, setSelectedTask] = useState<SentimentTask | null>(null)
  const [loadingTasks, setLoadingTasks] = useState(true)
  const [loadingDetail, setLoadingDetail] = useState(false)
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    sentimentAPI.listPlatforms().then(res => {
      setPlatforms(res.data)
      setSelectedPlatforms(res.data.map((p: PlatformInfo) => p.platform))
    }).catch(() => message.error('加载平台列表失败'))
    fetchTasks()
  }, [])

  const stopPolling = useCallback(() => {
    if (pollingRef.current) { clearInterval(pollingRef.current); pollingRef.current = null }
  }, [])
  const fetchTasks = async () => {
    try { const r = await sentimentAPI.listTasks({ page_size: 50 }); setTasks(r.data.tasks) } catch { /* ignore */ }
    setLoadingTasks(false)
  }
  const fetchTaskDetail = async (taskId: number) => {
    setLoadingDetail(true)
    try {
      const res = await sentimentAPI.getTask(taskId)
      setSelectedTask(res.data)
      if (res.data.status === 'pending' || res.data.status === 'running') {
        stopPolling()
        pollingRef.current = setInterval(async () => {
          try {
            const r = await sentimentAPI.getTask(taskId)
            setSelectedTask(r.data)
            if (r.data.status === 'completed' || r.data.status === 'failed') { stopPolling(); fetchTasks() }
          } catch { stopPolling() }
        }, 3000)
      }
    } catch { message.error('加载失败') }
    setLoadingDetail(false)
  }
  const handleSearch = async () => {
    if (!keyword.trim()) { message.warning('请输入关键词'); return }
    if (!selectedPlatforms.length) { message.warning('至少选一个平台'); return }
    setSearching(true)
    try {
      const res = await sentimentAPI.search({ keyword: keyword.trim(), platforms: selectedPlatforms, post_limit: postLimit })
      message.success(res.data.message)
      fetchTasks()
      setTimeout(() => fetchTaskDetail(res.data.task_id), 800)
    } catch (err: any) { message.error(err.response?.data?.detail || '搜索失败') }
    setSearching(false)
  }
  const handleDeleteTask = async (id: number) => {
    try { await sentimentAPI.deleteTask(id); message.success('已删除'); if (selectedTask?.id === id) setSelectedTask(null); fetchTasks() } catch { message.error('删除失败') }
  }
  useEffect(() => () => stopPolling(), [stopPolling])

  // ── Render ──────────────────────────────────────────────────────────────
  return (
    <div>
      <style>{`@keyframes pulse2{0%,100%{opacity:.4}50%{opacity:1}}`}</style>

      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 24 }}>
        <div>
          <h1 className="page-title animate-fade-in-up">舆情搜索</h1>
          <div className="page-subtitle animate-fade-in-up" style={{ animationDelay: '0.05s' }}>
            SENTIMENT · 跨平台关键词监测 · 影响力智能排序
          </div>
        </div>
        <Button icon={<ReloadOutlined />} size="small" onClick={() => { fetchTasks(); setSelectedTask(null) }}>刷新</Button>
      </div>

      {/* Search Bar */}
      <div style={{ background: '#fff', borderRadius: R.xl, padding: '24px 28px', marginBottom: 24, border: '1px solid #e2e8f0', boxShadow: '0 1px 3px rgba(0,0,0,0.04)' }}>
        <Row gutter={[12, 12]}>
          <Col xs={24} md={12}>
            <Input.Search size="large" placeholder="输入关键词，如：人工智能、贸易政策..." value={keyword} onChange={e => setKeyword(e.target.value)}
              onSearch={handleSearch} loading={searching}
              enterButton={<span><SearchOutlined /> 开始搜索</span>} style={{ borderRadius: 10 }} />
          </Col>
          <Col xs={24} md={8}>
            <Select mode="multiple" size="large" style={{ width: '100%', borderRadius: 10 }} placeholder="选择平台" value={selectedPlatforms} onChange={setSelectedPlatforms}
              options={platforms.map(p => ({ label: p.label, value: p.platform }))} maxTagCount={3} />
          </Col>
          <Col xs={12} md={4}>
            <Select size="large" style={{ width: '100%', borderRadius: 10 }} value={postLimit} onChange={setPostLimit}
              options={[{ label: '10 条/平台', value: 10 }, { label: '20 条/平台', value: 20 }, { label: '50 条/平台', value: 50 }]} />
          </Col>
        </Row>
        <div style={{ marginTop: 12, display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
          {platforms.map(p => {
            const checked = selectedPlatforms.includes(p.platform)
            return (
              <Tag.CheckableTag key={p.platform} checked={checked}
                onChange={c => setSelectedPlatforms(c ? [...selectedPlatforms, p.platform] : selectedPlatforms.filter(x => x !== p.platform))}
                style={{ borderRadius: 20, padding: '2px 14px', fontSize: 12, fontWeight: 500, border: `1px solid ${checked ? PLATFORM_COLORS[p.platform] : '#e2e8f0'}`,
                  background: checked ? `${PLATFORM_COLORS[p.platform]}12` : '#fff', color: checked ? PLATFORM_COLORS[p.platform] : '#64748b' }}>
                {p.label}
              </Tag.CheckableTag>
            )
          })}
          <Tooltip title="影响力 = 互动得分 × 平台权重 × 时间衰减 × 100">
            <span style={{ marginLeft: 'auto', fontSize: 11, color: '#94a3b8', cursor: 'help' }}>评分说明</span>
          </Tooltip>
        </div>
      </div>

      <Row gutter={24}>
        {/* Sidebar — History */}
        <Col xs={24} lg={6}>
          <div style={{ background: '#fff', borderRadius: R.lg, padding: '18px 20px', border: '1px solid #e2e8f0', height: 'calc(100vh - 360px)', overflow: 'auto', boxShadow: '0 1px 3px rgba(0,0,0,0.04)' }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: '#475569', marginBottom: 12, display: 'flex', alignItems: 'center', gap: 6 }}>
              <ClockCircleOutlined />历史搜索
              {tasks.length > 0 && <span style={{ color: '#94a3b8', fontWeight: 400 }}>({tasks.length})</span>}
            </div>
            {loadingTasks ? <Skeleton active paragraph={{ rows: 6 }} /> : !tasks.length ? (
              <div style={{ textAlign: 'center', padding: 40, color: '#94a3b8', fontSize: 12 }}>暂无记录</div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                {tasks.map(t => {
                  const active = selectedTask?.id === t.id
                  return (
                    <div key={t.id} onClick={() => { stopPolling(); fetchTaskDetail(t.id) }}
                      style={{
                        padding: '10px 12px', borderRadius: 10, cursor: 'pointer',
                        background: active ? '#eff6ff' : 'transparent',
                        border: active ? '1px solid #bfdbfe' : '1px solid transparent',
                        transition: 'all 0.15s',
                      }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <span style={{ fontWeight: 600, fontSize: 13, color: '#1e293b' }}>{t.keyword}</span>
                        <Badge status={t.status === 'completed' ? 'success' : t.status === 'running' ? 'processing' : t.status === 'failed' ? 'error' : 'default'} />
                      </div>
                      <div style={{ fontSize: 11, color: '#94a3b8', marginTop: 3, display: 'flex', justifyContent: 'space-between' }}>
                        <span>{t.total_posts || 0} 条</span>
                        <span>{fmtDt(t.created_at)}</span>
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        </Col>

        {/* Main — Results */}
        <Col xs={24} lg={18}>
          {loadingDetail ? (
            <div style={{ background: '#fff', borderRadius: R.lg, padding: 24, border: '1px solid #e2e8f0' }}><Skeleton active paragraph={{ rows: 10 }} /></div>
          ) : !selectedTask ? (
            <div style={{ background: '#fff', borderRadius: R.lg, padding: '80px 20px', textAlign: 'center', border: '1px solid #e2e8f0', boxShadow: '0 1px 3px rgba(0,0,0,0.04)' }}>
              <div style={{ width: 56, height: 56, borderRadius: '50%', background: '#f1f5f9', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', marginBottom: 16 }}>
                <SearchOutlined style={{ fontSize: 24, color: '#cbd5e1' }} />
              </div>
              <div style={{ fontSize: 15, color: '#64748b', fontWeight: 500 }}>选择左侧历史搜索查看结果</div>
              <div style={{ fontSize: 12, color: '#94a3b8', marginTop: 4 }}>或在上方输入关键词开始新的搜索</div>
            </div>
          ) : selectedTask.status === 'pending' || selectedTask.status === 'running' ? (
            <div style={{ background: '#fff', borderRadius: R.lg, padding: '60px 20px', textAlign: 'center', border: '1px solid #e2e8f0', boxShadow: '0 1px 3px rgba(0,0,0,0.04)' }}>
              <Spin size="large" />
              <div style={{ marginTop: 16, fontSize: 14, color: '#475569', fontWeight: 600 }}>
                <PulsingDot />正在搜索 "{selectedTask.keyword}"
              </div>
              <div style={{ fontSize: 12, color: '#94a3b8', marginTop: 4 }}>多平台并发采集 + 影响力计算</div>
            </div>
          ) : selectedTask.status === 'failed' ? (
            <div style={{ background: '#fff', borderRadius: R.lg, padding: 24, border: '1px solid #fecaca', boxShadow: '0 1px 3px rgba(0,0,0,0.04)' }}>
              <div style={{ color: '#dc2626', fontWeight: 600, marginBottom: 8 }}>搜索失败</div>
              {selectedTask.error_log && (
                <pre style={{ fontSize: 11, color: '#7f1d1d', background: '#fef2f2', padding: 12, borderRadius: R.sm, maxHeight: 200, overflow: 'auto', whiteSpace: 'pre-wrap' }}>
                  {JSON.stringify(JSON.parse(selectedTask.error_log), null, 2)}
                </pre>
              )}
              <Button style={{ marginTop: 12 }} onClick={handleSearch}>重新搜索</Button>
            </div>
          ) : (
            <div>
              {/* KPI Row */}
              <div style={{ display: 'flex', gap: 12, marginBottom: 16, flexWrap: 'wrap' }}>
                <KpiCard icon={<SearchOutlined />} value={String(selectedTask.total_posts)} label="搜索结果" iconBg="#eff6ff" iconColor="#3b82f6" valueColor="#1e3a8a" />
                <KpiCard icon={<ThunderboltOutlined />} value={selectedTask.posts?.length ? fmts(selectedTask.posts[0].impact_score) : '-'} label="最高影响力" iconBg="#fff7ed" iconColor="#f97316" valueColor="#9a3412" />
                <KpiCard icon={<BarChartOutlined />} value={(JSON.parse(selectedTask.platforms) as string[]).map((p: string) => PLATFORM_LABELS[p] || p).join('/')} label="已监测" iconBg="#f0fdf4" iconColor="#22c55e" valueColor="#14532d" />
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginLeft: 'auto' }}>
                  <span style={{ fontSize: 11, color: '#94a3b8' }}>{fmtDt(selectedTask.created_at)}</span>
                  <Button size="small" danger type="text" icon={<DeleteOutlined />} onClick={() => handleDeleteTask(selectedTask.id)} />
                </div>
              </div>

              {/* Post Cards */}
              {selectedTask.posts?.length === 0 ? (
                <div style={{ background: '#fff', borderRadius: R.lg, padding: '60px 20px', textAlign: 'center', border: '1px solid #e2e8f0' }}>
                  <Empty description="未找到相关帖子" />
                </div>
              ) : (
                selectedTask.posts?.map((post, idx) => (
                  <div key={post.id}
                    style={{
                      background: '#fff', borderRadius: R.lg, padding: '18px 22px', marginBottom: 10,
                      border: '1px solid #e2e8f0', borderLeftWidth: 4,
                      borderLeftColor: PLATFORM_COLORS[post.platform] || '#3b82f6',
                      boxShadow: '0 1px 2px rgba(0,0,0,0.03)',
                      transition: 'box-shadow 0.15s, border-color 0.15s',
                    }}
                    onMouseEnter={e => { e.currentTarget.style.boxShadow = '0 4px 12px rgba(0,0,0,0.06)'; e.currentTarget.style.borderColor = '#bfdbfe' }}
                    onMouseLeave={e => { e.currentTarget.style.boxShadow = '0 1px 2px rgba(0,0,0,0.03)'; e.currentTarget.style.borderColor = '#e2e8f0' }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 10 }}>
                      <Space size={10}>
                        <span style={{ fontSize: 12, fontWeight: 700, color: '#94a3b8', fontFamily: "'Fira Code', monospace" }}>#{idx + 1}</span>
                        <Tag color={PLATFORM_COLORS[post.platform]} style={{ margin: 0, borderRadius: 6, fontSize: 11 }}>
                          {PLATFORM_LABELS[post.platform] || post.platform}
                        </Tag>
                        {post.metrics_partial && <Tag style={{ borderRadius: 6, fontSize: 11 }}>部分数据</Tag>}
                        {post.author_avatar && (
                          <img src={post.author_avatar} alt="" style={{ width: 20, height: 20, borderRadius: '50%', objectFit: 'cover' }} />
                        )}
                        {post.author_name && <span style={{ color: '#94a3b8', fontSize: 12 }}>@{post.author_name}</span>}
                        {post.published_at && <span style={{ color: '#cbd5e1', fontSize: 11 }}>{fmtDt(post.published_at)}</span>}
                      </Space>
                      <Space size={16}>
                        <ImpactBadge score={post.impact_score} />
                        <Tooltip title="查看原文">
                          <Button type="link" size="small" icon={<LinkOutlined />} href={post.url} target="_blank" rel="noopener noreferrer" />
                        </Tooltip>
                      </Space>
                    </div>
                    <PostContent title={post.title} content={post.content || ''} />
                    {post.platform === 'youtube' && (
                      <DeepAnalysisButton post={post} />
                    )}
                    <QuotedTweet quotedTweetJson={post.quoted_tweet_json} />
                    <LinkCard cardJson={post.card_json} />
                    <PostImages imagesJson={post.images_json} />
                    <PostVideos videosJson={post.videos_json} />
                    <PostComments commentsJson={post.comments_json} />
                    <MetricRow post={post} />
                  </div>
                ))
              )}
            </div>
          )}
        </Col>
      </Row>
    </div>
  )
}
