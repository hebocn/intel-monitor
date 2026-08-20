import { useEffect, useState, useCallback } from 'react'
import {
  Button, Modal, Form, InputNumber, Select, Switch, Tag, message,
  Popconfirm, Typography, Tooltip, Skeleton, Empty, Space,
} from 'antd'
import {
  PlusOutlined, DeleteOutlined,
  FireOutlined, LinkOutlined, ClockCircleOutlined,
  SyncOutlined, ThunderboltOutlined, GlobalOutlined,
  EditOutlined, DownOutlined, UpOutlined,
} from '@ant-design/icons'
import { hotTopicsAPI } from '../services/api'

const { Text } = Typography

interface Platform {
  key: string
  label: string
  mode: string
}

interface Source {
  id: number
  platform: string
  is_active: boolean
  cron_schedule: string | null
  item_limit: number
  created_at: string
}

interface Topic {
  id: number
  source_id: number
  platform: string
  title: string
  url: string | null
  rank: number | null
  hot_value: string | null
  extra: string | null
  fetched_at: string | null
}

const GREEN = '#22C55E'
const GREEN_LIGHT = '#4ADE80'

const MODE_LABELS: Record<string, string> = {
  public: '公开',
  browser: '浏览器',
}

/* ── Noise texture SVG ───────────────────────────────────── */

const NOISE_SVG = `data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n' x='0' y='0'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.65' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='0.03'/%3E%3C/svg%3E`

/* ── Glassmorphism styles — dark mode frosted glass ──── */

const glassCard: React.CSSProperties = {
  background: 'var(--surface-2)',
  borderRadius: 20,
  border: '1px solid var(--border)',
  boxShadow: 'var(--shadow-md)',
  position: 'relative' as const,
}

const glassCardTexture: React.CSSProperties = {
  position: 'absolute' as const,
  inset: 0,
  borderRadius: 20,
  pointerEvents: 'none' as const,
  background: `url("${NOISE_SVG}")`,
  opacity: 0.15,
  zIndex: 0,
}

const glassItem: React.CSSProperties = {
  background: 'var(--surface-1)',
  borderRadius: 14,
  border: '1px solid var(--border)',
  boxShadow: '0 1px 3px rgba(0,0,0,0.15)',
}

const glassItemHover: React.CSSProperties = {
  background: 'rgba(248,250,252,0.06)',
  border: '1px solid rgba(248,250,252,0.12)',
}

const glassChip: React.CSSProperties = {
  background: 'rgba(248,250,252,0.04)',
  borderRadius: 24,
  border: '1px solid var(--border)',
  boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
}

/* ── Color tokens ────────────────────────────────────────── */

const ACCENT_GREEN = '#22C55E'
const ACCENT_TEAL = '#2DD4BF'
const TEXT_PRIMARY = 'var(--text-primary)'
const TEXT_SECONDARY = 'var(--text-secondary)'
const TEXT_MUTED = 'var(--text-muted)'

/* ── Topic row component ─────────────────────────────────── */

function TopicRow({ topic, idx, color, onDelete }: { topic: Topic; idx: number; color: string; onDelete?: (id: number) => void }) {
  const isTop3 = topic.rank && topic.rank <= 3
  const rankStyle = isTop3 ? RANK_COLORS[topic.rank!] : null

  return (
    <div
      style={{
        ...glassItem,
        display: 'flex',
        alignItems: 'center',
        gap: 14,
        padding: '12px 16px',
        cursor: topic.url ? 'pointer' : 'default',
        transition: 'background-color 0.25s cubic-bezier(0.4, 0, 0.2, 1), border-color 0.25s cubic-bezier(0.4, 0, 0.2, 1), color 0.25s cubic-bezier(0.4, 0, 0.2, 1), transform 0.25s cubic-bezier(0.4, 0, 0.2, 1)',
        position: 'relative',
        overflow: 'hidden',
      }}
      onClick={() => topic.url && window.open(topic.url, '_blank')}
      onMouseEnter={e => {
        Object.entries(glassItemHover).forEach(([k, v]) => {
          ;(e.currentTarget.style as any)[k] = v
        })
      }}
      onMouseLeave={e => {
        e.currentTarget.style.background = glassItem.background as string
        e.currentTarget.style.border = glassItem.border as string
        e.currentTarget.style.borderTop = glassItem.borderTop as string
      }}
    >
      {/* Rank badge */}
      <div style={{
        minWidth: 36, height: 36,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        borderRadius: 10,
        background: rankStyle ? rankStyle.bg : 'rgba(248,250,252,0.04)',
        border: rankStyle ? `1px solid ${rankStyle.border}` : '1px solid rgba(248,250,252,0.04)',
        color: rankStyle ? rankStyle.text : 'var(--text-muted)',
        fontWeight: 800,
        fontSize: isTop3 ? 16 : 13,
        fontFamily: 'var(--font-mono)',
        flexShrink: 0,
        boxShadow: rankStyle?.glow || 'none',
      }}>
        {topic.rank || idx + 1}
      </div>

      {/* Title */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <Text style={{
          color: topic.url ? color : TEXT_PRIMARY,
          fontWeight: 500,
          fontSize: 14,
          lineHeight: 1.6,
          display: '-webkit-box',
          WebkitLineClamp: 2,
          WebkitBoxOrient: 'vertical',
          overflow: 'hidden',
          cursor: topic.url ? 'pointer' : 'default',
          textDecoration: 'none',
          borderBottom: topic.url ? '1px solid transparent' : 'none',
          transition: 'border-color 0.2s, color 0.2s',
        }}
        onMouseEnter={e => {
          if (topic.url) e.currentTarget.style.borderBottomColor = color
        }}
        onMouseLeave={e => {
          if (topic.url) e.currentTarget.style.borderBottomColor = 'transparent'
        }}
        >
          {topic.title}
        </Text>
      </div>

      {/* Hot value chip */}
      {topic.hot_value && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 5,
          padding: '4px 12px', borderRadius: 10,
          background: `linear-gradient(135deg, ${hexToRgba(color, 0.12)}, ${hexToRgba(color, 0.06)})`,
          border: `1px solid ${hexToRgba(color, 0.18)}`,
          color: color,
          fontSize: 12, fontWeight: 700,
          fontFamily: 'var(--font-mono)',
          flexShrink: 0,
        }}>
          <FireOutlined style={{ fontSize: 11 }} />
          {topic.hot_value}
        </div>
      )}

      {/* Link indicator */}
      {topic.url && (
        <LinkOutlined style={{ color: 'var(--text-secondary)', fontSize: 13, flexShrink: 0 }} />
      )}

      {/* Delete */}
      {onDelete && (
        <Popconfirm
          title="删除此话题？"
          onConfirm={e => { e?.stopPropagation(); onDelete(topic.id) }}
          onCancel={e => e?.stopPropagation()}
          okButtonProps={{ danger: true }}
        >
          <Button
            type="text" size="small"
            icon={<DeleteOutlined />}
            onClick={e => e.stopPropagation()}
            style={{ color: 'var(--text-secondary)', padding: '0 2px', width: 22, height: 22, flexShrink: 0 }}
          />
        </Popconfirm>
      )}
    </div>
  )
}

/* ── Platform labels map ──────────────────────────────────── */

const PLATFORM_LABELS_MAP: Record<string, string> = {
  weibo: '微博', zhihu: '知乎', bilibili: 'B站', v2ex: 'V2EX',
  hackernews: 'HackerNews', reddit: 'Reddit', twitter: 'Twitter/X',
  douban_movie: '豆瓣电影', douban_book: '豆瓣图书', xueqiu: '雪球',
  'linux-do': 'Linux.do', bbc: 'BBC', google_trends: 'Google Trends',
  stackoverflow: 'StackOverflow', github: 'GitHub',
}

const PLATFORM_COLORS: Record<string, string> = {
  weibo: '#e53e3e',       zhihu: '#3B82F6',
  bilibili: '#fb7299',    v2ex: 'var(--text-muted)',
  hackernews: '#f59e0b',  reddit: '#ff4500',
  twitter: '#1d9bf0',     douban_movie: '#22C55E',
  douban_book: '#65a30d', xueqiu: '#3B82F6',
  'linux-do': '#F59E0B',  bbc: '#b91c1c',
  google_trends: '#4285f4', stackoverflow: '#f48225',
  github: '#A78BFA',
}

function getPlatformColor(platform: string): string {
  return PLATFORM_COLORS[platform] || '#22C55E'
}

const PLATFORM_EMOJI: Record<string, string> = {
  weibo: '🔥',        zhihu: '🦉',
  bilibili: '📺',     v2ex: '💬',
  hackernews: '🧡',   reddit: '👽',
  twitter: '🐦',      douban_movie: '🎬',
  douban_book: '📚',  xueqiu: '📈',
  'linux-do': '🐧',   bbc: '📡',
  google_trends: '📊', stackoverflow: '📦',
  github: '🐙',
}

function getPlatformEmoji(platform: string): string {
  return PLATFORM_EMOJI[platform] || '📌'
}

function formatBeijingTime(isoString: string | null): string {
  if (!isoString) return ''
  // If no timezone info, treat as UTC explicitly
  const date = isoString.endsWith('Z') || isoString.includes('+') || isoString.includes('[')
    ? new Date(isoString)
    : new Date(isoString + 'Z')
  return date.toLocaleString('zh-CN', {
    month: 'numeric', day: 'numeric',
    hour: '2-digit', minute: '2-digit',
    timeZone: 'Asia/Shanghai',
  })
}

function hexToRgba(hex: string, alpha: number): string {
  const r = parseInt(hex.slice(1, 3), 16)
  const g = parseInt(hex.slice(3, 5), 16)
  const b = parseInt(hex.slice(5, 7), 16)
  return `rgba(${r},${g},${b},${alpha})`
}

const RANK_COLORS: Record<number, { bg: string; border: string; text: string; glow: string }> = {
  1: { bg: 'rgba(245,158,11,0.12)', border: 'rgba(245,158,11,0.30)', text: '#F59E0B', glow: '0 0 12px rgba(245,158,11,0.12)' },
  2: { bg: 'rgba(148,163,184,0.10)', border: 'rgba(148,163,184,0.28)', text: 'var(--text-muted)', glow: 'none' },
  3: { bg: 'rgba(217,119,6,0.08)',  border: 'rgba(217,119,6,0.22)',  text: '#F59E0B', glow: 'none' },
}

const CARD_DEFAULT_LIMIT = 10

/* ── Platform card component ──────────────────────────────── */

function PlatformCard({
  platform, topics, color, fetchedAt, onDeleteTopic, onDeleteSource,
  draggable, onDragStart, onDragOver, onDrop, isDragging, isOver,
}: {
  platform: string; topics: Topic[]; color: string; fetchedAt: string | null;
  onDeleteTopic?: (id: number) => void;
  onDeleteSource?: () => void;
  draggable?: boolean;
  onDragStart?: (e: React.DragEvent) => void;
  onDragOver?: (e: React.DragEvent) => void;
  onDrop?: (e: React.DragEvent) => void;
  isDragging?: boolean;
  isOver?: boolean;
}) {
  const [expanded, setExpanded] = useState(false)
  const visibleTopics = expanded ? topics : topics.slice(0, CARD_DEFAULT_LIMIT)
  const hasMore = topics.length > CARD_DEFAULT_LIMIT

  return (
    <div
      draggable={draggable}
      onDragStart={onDragStart}
      onDragOver={onDragOver}
      onDrop={onDrop}
      style={{
        ...glassCard,
        padding: 0,
        overflow: 'hidden',
        cursor: draggable ? 'grab' : 'default',
        opacity: isDragging ? 0.35 : 1,
        transform: isDragging ? 'scale(0.96)' : 'scale(1)',
        outline: isOver ? `2px solid ${hexToRgba(color, 0.45)}` : 'none',
        outlineOffset: -2,
        transition: 'opacity 0.25s, transform 0.25s, outline 0.2s, box-shadow 0.3s',
        userSelect: 'none',
      }}
    >
      {/* Noise texture overlay */}
      <div style={glassCardTexture} />

      {/* Card header */}
      <div style={{
        position: 'relative', zIndex: 1,
        padding: '16px 18px 14px',
        background: 'rgba(248,250,252,0.03)',
        borderBottom: `1px solid var(--border)`,
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          {/* Drag handle */}
          {draggable && (
            <div style={{
              color: 'rgba(248,250,252,0.2)', fontSize: 14, cursor: 'grab',
              lineHeight: 0, flexShrink: 0,
            }}>
              ⋮⋮
            </div>
          )}

          {/* Platform emoji */}
          <div style={{
            width: 40, height: 40, borderRadius: 14,
            background: `
              linear-gradient(135deg,
                ${hexToRgba(color, 0.14)} 0%,
                ${hexToRgba(color, 0.04)} 100%)
            `,
            border: `1px solid ${hexToRgba(color, 0.12)}`,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 22, lineHeight: 1,
            flexShrink: 0,
          }}>
            {getPlatformEmoji(platform)}
          </div>

          <div>
            <Text style={{
              fontWeight: 700, fontSize: 16, color: TEXT_PRIMARY,
              display: 'block', lineHeight: 1.2,
            }}>
              {PLATFORM_LABELS_MAP[platform] || platform}
            </Text>
            <Text style={{
              color: TEXT_MUTED, fontSize: 11,
              fontFamily: 'var(--font-mono)', letterSpacing: 1.5,
            }}>
              {topics.length} TOPICS
            </Text>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {fetchedAt && (
            <Text style={{
              color: TEXT_MUTED, fontSize: 11,
              fontFamily: 'var(--font-mono)',
            }}>
              <ClockCircleOutlined style={{ marginRight: 4 }} />
              {formatBeijingTime(fetchedAt)}
            </Text>
          )}
          {onDeleteSource && (
            <Popconfirm
              title="删除此平台及所有话题？"
              onConfirm={onDeleteSource}
              okButtonProps={{ danger: true }}
            >
              <Button
                type="text" size="small"
                icon={<DeleteOutlined />}
                onClick={e => e.stopPropagation()}
                style={{ color: 'var(--text-secondary)', width: 24, height: 24 }}
              />
            </Popconfirm>
          )}
        </div>
      </div>

      {/* Topic list */}
      <div style={{
        position: 'relative', zIndex: 1,
        padding: '14px 16px',
        display: 'flex', flexDirection: 'column', gap: 8,
      }}>
        {visibleTopics.map((topic, idx) => (
          <TopicRow key={topic.id} topic={topic} idx={idx} color={color} onDelete={onDeleteTopic} />
        ))}

        {hasMore && (
          <div
            onClick={() => setExpanded(!expanded)}
            style={{
              display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
              padding: '10px 0 2px', cursor: 'pointer',
              color, fontSize: 13, fontWeight: 600,
              opacity: 0.6, transition: 'opacity 0.2s',
            }}
            onMouseEnter={e => e.currentTarget.style.opacity = '1'}
            onMouseLeave={e => e.currentTarget.style.opacity = '0.6'}
          >
            {expanded ? <UpOutlined /> : <DownOutlined />}
            {expanded ? '收起' : `展开剩余 ${topics.length - CARD_DEFAULT_LIMIT} 条`}
          </div>
        )}
      </div>
    </div>
  )
}

/* ── Main page ───────────────────────────────────────────── */

export default function HotTopicsPage() {
  const [platforms, setPlatforms] = useState<Platform[]>([])
  const [sources, setSources] = useState<Source[]>([])
  const [topics, setTopics] = useState<Topic[]>([])
  const [loading, setLoading] = useState(true)
  const [fetchingId, setFetchingId] = useState<number | 'all' | null>(null)
  const [modalOpen, setModalOpen] = useState(false)
  const [editModalOpen, setEditModalOpen] = useState(false)
  const [editingSource, setEditingSource] = useState<Source | null>(null)
  const [activePlatform, setActivePlatform] = useState<string>('all')
  const [cardOrder, setCardOrder] = useState<string[]>(() => {
    try {
      const saved = localStorage.getItem('hot-topic-card-order')
      return saved ? JSON.parse(saved) : []
    } catch { return [] }
  })
  const [dragIdx, setDragIdx] = useState<number | null>(null)
  const [overIdx, setOverIdx] = useState<number | null>(null)
  const [form] = Form.useForm()
  const [editForm] = Form.useForm()

  const fetchPlatforms = async () => {
    try {
      const res = await hotTopicsAPI.listPlatforms()
      setPlatforms(res.data)
    } catch { /* silent */ }
  }

  const fetchSources = async () => {
    try {
      const res = await hotTopicsAPI.listSources()
      setSources(res.data)
    } catch { /* silent */ }
  }

  const fetchTopics = useCallback(async () => {
    try {
      const params: any = {}
      if (activePlatform !== 'all') params.platform = activePlatform
      const res = await hotTopicsAPI.listTopics(params)
      setTopics(res.data)
    } catch { /* silent */ }
  }, [activePlatform])

  useEffect(() => {
    const init = async () => {
      setLoading(true)
      await Promise.all([fetchPlatforms(), fetchSources()])
      setLoading(false)
    }
    init()
  }, [])

  useEffect(() => { fetchTopics() }, [fetchTopics])

  const handleAddSource = async () => {
    const values = await form.validateFields()
    try {
      await hotTopicsAPI.createSource(values)
      message.success('平台添加成功')
      setModalOpen(false)
      form.resetFields()
      fetchSources()
    } catch (err: any) {
      message.error(err.response?.data?.detail || '添加失败')
    }
  }

  const handleUpdateSource = async () => {
    const values = await editForm.validateFields()
    if (!editingSource) return
    try {
      await hotTopicsAPI.updateSource(editingSource.id, values)
      message.success('更新成功')
      setEditModalOpen(false)
      setEditingSource(null)
      editForm.resetFields()
      fetchSources()
    } catch (err: any) {
      message.error(err.response?.data?.detail || '更新失败')
    }
  }

  const handleDeleteSource = async (id: number) => {
    await hotTopicsAPI.deleteSource(id)
    message.success('已删除')
    fetchSources()
    fetchTopics()
  }

  const handleDeleteTopic = async (id: number) => {
    await hotTopicsAPI.deleteTopic(id)
    message.success('已删除')
    fetchTopics()
  }

  const handleFetch = async (sourceId?: number) => {
    setFetchingId(sourceId ?? 'all')
    try {
      const res = await hotTopicsAPI.triggerFetch({ source_id: sourceId })
      const data = res.data
      message.info(data.message || '抓取已启动')

      // Poll every 3s, max 60s
      for (let i = 0; i < 20; i++) {
        await new Promise(r => setTimeout(r, 3000))
        await fetchTopics()
      }
    } catch (err: any) {
      message.error(err.response?.data?.detail || '抓取失败')
    } finally {
      setFetchingId(null)
    }
  }

  const handleFetchAll = async () => {
    setFetchingId('all')
    try {
      const res = await hotTopicsAPI.triggerFetch({})
      const data = res.data
      message.info(data.message || '抓取已启动')

      // Poll every 3s, max 60s
      for (let i = 0; i < 20; i++) {
        await new Promise(r => setTimeout(r, 3000))
        await fetchTopics()
      }
    } catch (err: any) {
      message.error(err.response?.data?.detail || '抓取失败')
    } finally {
      setFetchingId(null)
    }
  }

  const getPlatformLabel = (key: string) =>
    platforms.find(p => p.key === key)?.label || key

  const getTopicsForSource = (sourceId: number) =>
    topics.filter(t => t.source_id === sourceId)

  const filteredTopics = activePlatform === 'all'
    ? topics
    : topics.filter(t => t.platform === activePlatform)

  const topicsByPlatform = filteredTopics.reduce((acc, t) => {
    if (!acc[t.platform]) acc[t.platform] = []
    acc[t.platform].push(t)
    return acc
  }, {} as Record<string, Topic[]>)

  const platformEntries = Object.entries(topicsByPlatform)
  const sortedEntries = cardOrder.length > 0
    ? [...platformEntries].sort((a, b) => {
        const ia = cardOrder.indexOf(a[0])
        const ib = cardOrder.indexOf(b[0])
        return (ia === -1 ? 999 : ia) - (ib === -1 ? 999 : ib)
      })
    : platformEntries

  // Drag handlers
  const handleDragStart = (idx: number) => (e: React.DragEvent) => {
    setDragIdx(idx)
    e.dataTransfer.effectAllowed = 'move'
    e.dataTransfer.setData('text/plain', String(idx))
  }
  const handleDragOver = (idx: number) => (e: React.DragEvent) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
    setOverIdx(idx)
  }
  const handleDrop = (idx: number) => (e: React.DragEvent) => {
    e.preventDefault()
    if (dragIdx === null || dragIdx === idx) {
      setDragIdx(null)
      setOverIdx(null)
      return
    }
    const newOrder = sortedEntries.map(([p]) => p)
    const [moved] = newOrder.splice(dragIdx, 1)
    newOrder.splice(idx, 0, moved)
    setCardOrder(newOrder)
    localStorage.setItem('hot-topic-card-order', JSON.stringify(newOrder))
    setDragIdx(null)
    setOverIdx(null)
  }
  const handleDragEnd = () => {
    setDragIdx(null)
    setOverIdx(null)
  }

  const hasSources = sources.length > 0

  return (
    <div style={{
      minHeight: '100vh',
      background: 'linear-gradient(170deg, var(--surface-1) 0%, var(--surface-1) 25%, #050B14 55%, #050B14 80%, #050B14 100%)',
      margin: -32, padding: 32,
      position: 'relative',
    }}>
      {/* Global noise texture */}
      <div style={{
        position: 'fixed', inset: 0,
        background: `url("${NOISE_SVG}")`,
        pointerEvents: 'none', zIndex: 0,
        opacity: 0.15,
      }} />


      <div style={{ position: 'relative', zIndex: 1 }}>
        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: 28 }}>
          <div>
            <h1 className="page-title animate-fade-in-up" style={{
              color: 'var(--text-primary)',
              fontWeight: 800,
              letterSpacing: 1,
            }}>
              热门话题
            </h1>
            <div className="page-subtitle" style={{
              color: 'var(--text-secondary)',
              letterSpacing: 1.5,
            }}>
              HOT TOPICS · AutoCLI · {sources.length} 个平台
            </div>
          </div>
          <Space>
            {hasSources && (
              <Button
                icon={<SyncOutlined spin={fetchingId === 'all'} />}
                onClick={handleFetchAll}
                loading={fetchingId === 'all'}
                style={{
                  ...glassChip,
                  height: 38, fontWeight: 600,
                  color: ACCENT_GREEN,
                }}
              >
                全部抓取
              </Button>
            )}
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={() => { form.resetFields(); setModalOpen(true) }}
              style={{
                borderRadius: 24, height: 38, fontWeight: 600,
                  background: 'var(--accent)',
                border: 'none',
              }}
            >
              添加平台
            </Button>
          </Space>
        </div>

        {loading ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            {Array.from({ length: 3 }).map((_, i) => (
              <div key={i} style={{ ...glassCard, padding: 22 }}>
                <div style={glassCardTexture} />
                <div style={{ position: 'relative', zIndex: 1 }}>
                  <Skeleton.Input active style={{ width: 200, height: 22, borderRadius: 4 }} />
                </div>
              </div>
            ))}
          </div>
        ) : !hasSources ? (
          <div style={{
            ...glassCard,
            textAlign: 'center', padding: '80px 40px',
            maxWidth: 480, margin: '80px auto',
          }}>
            <div style={glassCardTexture} />
            <div style={{ position: 'relative', zIndex: 1 }}>
              <FireOutlined style={{ fontSize: 52, color: ACCENT_GREEN, marginBottom: 20, display: 'block', opacity: 0.3 }} />
              <Text style={{ color: TEXT_SECONDARY, fontSize: 15, display: 'block' }}>
                还没有添加平台
              </Text>
              <Text style={{ color: TEXT_MUTED, fontSize: 13, display: 'block', marginTop: 8 }}>
                点击「添加平台」开始追踪各平台热门话题
              </Text>
            </div>
          </div>
        ) : (
          <>
            {/* Platform filter chips */}
            <div style={{
              display: 'flex', flexWrap: 'wrap', gap: 10, marginBottom: 28,
            }}>
              {/* "All" chip */}
              <div
                style={{
                  ...glassChip,
                  display: 'flex', alignItems: 'center', gap: 6,
                  padding: '9px 18px',
                  cursor: 'pointer',
                  transition: 'background-color 0.25s cubic-bezier(0.4, 0, 0.2, 1), border-color 0.25s cubic-bezier(0.4, 0, 0.2, 1), color 0.25s cubic-bezier(0.4, 0, 0.2, 1), transform 0.25s cubic-bezier(0.4, 0, 0.2, 1)',
                  background: activePlatform === 'all'
                    ? 'rgba(96,165,250,0.12)' : glassChip.background,
                  border: activePlatform === 'all'
                    ? '1px solid rgba(96,165,250,0.3)' : glassChip.border,
                  borderTop: activePlatform === 'all'
                    ? '1px solid rgba(96,165,250,0.3)' : glassChip.borderTop,
                  boxShadow: activePlatform === 'all'
                    ? '0 2px 12px rgba(248,250,252,0.06), inset 0 1px 0 rgba(96,165,250,0.08), 0 0 16px rgba(96,165,250,0.08)'
                    : glassChip.boxShadow,
                }}
                onClick={() => setActivePlatform('all')}
              >
                <GlobalOutlined style={{
                  fontSize: 13,
                  color: activePlatform === 'all' ? '#60A5FA' : TEXT_MUTED,
                }} />
                <Text style={{
                  fontWeight: activePlatform === 'all' ? 700 : 500,
                  fontSize: 13,
                  color: activePlatform === 'all' ? '#93C5FD' : TEXT_SECONDARY,
                }}>
                  全部
                </Text>
              </div>

              {sources.map(source => {
                const isActive = activePlatform === source.platform
                const count = getTopicsForSource(source.id).length
                const pColor = getPlatformColor(source.platform)
                return (
                  <div
                    key={source.id}
                    style={{
                      ...glassChip,
                      display: 'flex', alignItems: 'center', gap: 8,
                      padding: '9px 16px',
                      cursor: 'pointer',
                      transition: 'background-color 0.25s cubic-bezier(0.4, 0, 0.2, 1), border-color 0.25s cubic-bezier(0.4, 0, 0.2, 1), color 0.25s cubic-bezier(0.4, 0, 0.2, 1), transform 0.25s cubic-bezier(0.4, 0, 0.2, 1)',
                      background: isActive ? hexToRgba(pColor, 0.10) : glassChip.background,
                      border: isActive ? `1px solid ${hexToRgba(pColor, 0.28)}` : glassChip.border,
                      borderTop: isActive ? `1px solid ${hexToRgba(pColor, 0.28)}` : glassChip.borderTop,
                      boxShadow: isActive
                        ? `0 2px 12px rgba(0,0,0,0.4), inset 0 1px 0 ${hexToRgba(pColor, 0.06)}, 0 0 16px ${hexToRgba(pColor, 0.08)}`
                        : glassChip.boxShadow,
                    }}
                    onClick={() => setActivePlatform(isActive ? 'all' : source.platform)}
                  >
                    <div style={{
                      width: 8, height: 8, borderRadius: '50%',
                      background: source.is_active ? pColor : 'var(--text-secondary)',
                      boxShadow: source.is_active ? `0 0 8px ${hexToRgba(pColor, 0.5)}` : 'none',
                    }} />
                    <Text style={{
                      fontWeight: isActive ? 700 : 500,
                      fontSize: 13,
                      color: isActive ? pColor : TEXT_SECONDARY,
                    }}>
                      {getPlatformLabel(source.platform)}
                    </Text>
                    {count > 0 && (
                      <span style={{
                        background: hexToRgba(pColor, 0.10), color: pColor,
                        fontSize: 10, fontWeight: 800,
                        padding: '2px 8px', borderRadius: 10,
                        fontFamily: 'var(--font-mono)',
                      }}>
                        {count}
                      </span>
                    )}

                    {/* Action buttons */}
                    <div style={{
                      display: 'flex', alignItems: 'center', gap: 8,
                      marginLeft: 4,
                      borderLeft: '1px solid rgba(248,250,252,0.06)',
                      paddingLeft: 6,
                    }}>
                      <Tooltip title="抓取">
                        <Button
                          type="text" size="small"
                          icon={<ThunderboltOutlined />}
                          onClick={e => { e.stopPropagation(); handleFetch(source.id) }}
                          loading={fetchingId === source.id}
                          style={{ color: pColor, padding: '0 3px', width: 24, height: 24 }}
                        />
                      </Tooltip>
                      <Tooltip title="编辑">
                        <Button
                          type="text" size="small"
                          icon={<EditOutlined />}
                          onClick={e => {
                            e.stopPropagation()
                            setEditingSource(source)
                            editForm.setFieldsValue(source)
                            setEditModalOpen(true)
                          }}
                          style={{ color: TEXT_MUTED, padding: '0 3px', width: 24, height: 24 }}
                        />
                      </Tooltip>
                      <Popconfirm
                        title="删除此平台及所有话题？"
                        onConfirm={() => handleDeleteSource(source.id)}
                        okButtonProps={{ danger: true }}
                      >
                        <Tooltip title="删除">
                          <Button
                            type="text" size="small"
                            icon={<DeleteOutlined />}
                            onClick={e => e.stopPropagation()}
                            style={{ color: TEXT_MUTED, padding: '0 3px', width: 24, height: 24 }}
                          />
                        </Tooltip>
                      </Popconfirm>
                    </div>
                  </div>
                )
              })}
            </div>

            {/* Platform topic cards — 2 column grid */}
            {sortedEntries.length === 0 ? (
              <div style={{
                ...glassCard,
                textAlign: 'center', padding: '60px 40px',
              }}>
                <div style={glassCardTexture} />
                <div style={{ position: 'relative', zIndex: 1 }}>
                  <Empty description={<span style={{ color: TEXT_MUTED }}>暂无话题数据，点击抓取按钮获取</span>} />
                </div>
              </div>
            ) : (
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fill, minmax(420px, 1fr))',
                  gap: 20,
                }}
                onDragEnd={handleDragEnd}
              >
                {sortedEntries.map(([platform, platformTopics], idx) => {
                  const source = sources.find(s => s.platform === platform)
                  return (
                  <PlatformCard
                    key={platform}
                    platform={platform}
                    topics={platformTopics}
                    color={getPlatformColor(platform)}
                    fetchedAt={platformTopics[0]?.fetched_at || null}
                    onDeleteTopic={handleDeleteTopic}
                    onDeleteSource={source ? () => handleDeleteSource(source.id) : undefined}
                    draggable
                    onDragStart={handleDragStart(idx)}
                    onDragOver={handleDragOver(idx)}
                    onDrop={handleDrop(idx)}
                    isDragging={dragIdx === idx}
                    isOver={overIdx === idx && dragIdx !== idx}
                  />
                )})}
              </div>
            )}
          </>
        )}
      </div>

      {/* Add source modal */}
      <Modal
        title="添加平台"
        open={modalOpen}
        onOk={handleAddSource}
        onCancel={() => { setModalOpen(false); form.resetFields() }}
        width={460}
      >
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item name="platform" label="平台" rules={[{ required: true, message: '请选择平台' }]}>
            <Select
              placeholder="选择要追踪的平台"
              options={platforms
                .filter(p => !sources.find(s => s.platform === p.key))
                .map(p => ({
                  value: p.key,
                  label: (
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <div style={{
                        width: 8, height: 8, borderRadius: '50%',
                        background: GREEN,
                      }} />
                      <span>{p.label}</span>
                      <Tag style={{
                        marginLeft: 'auto', fontSize: 10,
                        background: p.mode === 'public' ? 'rgba(34,197,94,0.1)' : 'rgba(255,152,0,0.1)',
                        color: p.mode === 'public' ? '#22C55E' : '#f57c00',
                        border: 'none', borderRadius: 6,
                      }}>
                        {MODE_LABELS[p.mode] || p.mode}
                      </Tag>
                    </div>
                  ),
                }))}
              showSearch
              optionFilterProp="label"
            />
          </Form.Item>
          <Form.Item name="item_limit" label="每次抓取条数" initialValue={30}>
            <InputNumber min={5} max={100} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="cron_schedule" label="定时抓取 (可选)">
            <Select
              placeholder="选择频率，或留空仅手动抓取"
              allowClear
              options={[
                { value: '0 */1 * * *', label: '每小时' },
                { value: '0 */3 * * *', label: '每 3 小时' },
                { value: '0 */6 * * *', label: '每 6 小时' },
                { value: '0 9 * * *', label: '每天 9:00' },
                { value: '0 9,18 * * *', label: '每天 9:00, 18:00' },
              ]}
            />
          </Form.Item>
        </Form>
      </Modal>

      {/* Edit source modal */}
      <Modal
        title="编辑平台"
        open={editModalOpen}
        onOk={handleUpdateSource}
        onCancel={() => { setEditModalOpen(false); setEditingSource(null); editForm.resetFields() }}
        width={460}
      >
        <Form form={editForm} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item name="is_active" label="启用" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item name="item_limit" label="每次抓取条数">
            <InputNumber min={5} max={100} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="cron_schedule" label="定时抓取">
            <Select
              placeholder="选择频率，或留空仅手动抓取"
              allowClear
              options={[
                { value: '0 */1 * * *', label: '每小时' },
                { value: '0 */3 * * *', label: '每 3 小时' },
                { value: '0 */6 * * *', label: '每 6 小时' },
                { value: '0 9 * * *', label: '每天 9:00' },
                { value: '0 9,18 * * *', label: '每天 9:00, 18:00' },
              ]}
            />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
