import { useEffect, useState, useRef, useCallback } from 'react'
import { Row, Col, Tag, Typography, Skeleton, Select, Popconfirm, message, Tooltip } from 'antd'
import {
  MobileOutlined, GlobalOutlined, CheckCircleOutlined,
  CloseCircleOutlined, ClockCircleOutlined, FilterOutlined, DeleteOutlined,
  RobotOutlined, LinkOutlined, FileTextOutlined, HeartOutlined,
} from '@ant-design/icons'
import { dashboardAPI, resultsAPI } from '../services/api'

const { Text, Paragraph } = Typography

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

function sanitizeContent(html: string): string {
  if (!html) return ''
  let clean = html.replace(/<(script|iframe|style|object|embed)\b[^>]*>[\s\S]*?<\/\1>/gi, '')
  clean = clean.replace(/\s+on\w+\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+)/gi, '')
  clean = clean.replace(/<img\b/gi, '<img style="width:1.2em;height:1.2em;vertical-align:text-bottom;"')
  clean = clean.replace(/<a\b/gi, '<a target="_blank" rel="noopener noreferrer"')
  return clean
}

const platformColors: Record<string, string> = {
  x: '#1DA1F2',
  youtube: '#FF0000',
  xiaohongshu: '#FE2C55',
  douyin: '#000000',
  weibo: '#E6162D',
  website: '#5a7a9a',
}

const platformLabels: Record<string, string> = {
  x: 'X',
  youtube: 'YouTube',
  xiaohongshu: '小红书',
  douyin: '抖音',
  weibo: '微博',
  website: '网站',
}

function relativeTime(dateStr: string | null): string {
  if (!dateStr) return '—'
  const now = new Date()
  const d = new Date(dateStr)
  const diff = Math.floor((now.getTime() - d.getTime()) / 1000)
  if (diff < 60) return '刚刚'
  if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`
  if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`
  if (diff < 604800) return `${Math.floor(diff / 86400)} 天前`
  return dateStr
}

const statCards = [
  { key: 'total_targets', title: '监测目标', icon: <MobileOutlined />, color: '#2d6a4f' },
  { key: 'active_targets', title: '活跃目标', icon: null, color: '#8b6914' },
  { key: 'total_websites', title: '网站监测', icon: <GlobalOutlined />, color: '#5a7a9a' },
  { key: 'today_results', title: '今日监测', icon: <ClockCircleOutlined />, color: '#2d6a4f' },
  { key: 'today_success', title: '成功', icon: <CheckCircleOutlined />, color: '#52b788' },
  { key: 'today_failed', title: '失败', icon: <CloseCircleOutlined />, color: '#c75050' },
]

function ResultCard({ record, onDelete }: { record: any; onDelete: (id: number) => void }) {
  const [postsExpanded, setPostsExpanded] = useState(false)
  const [summaryExpanded, setSummaryExpanded] = useState(false)
  const cleaned = cleanSummary(record.summary)
  const pColor = platformColors[record.platform] || '#666'
  const pLabel = platformLabels[record.platform] || record.platform
  const isSocial = record.target_type === 'social_media'

  const statusConfig: Record<string, { color: string; bg: string; icon: React.ReactNode; label: string }> = {
    success: { color: '#52b788', bg: 'rgba(82,183,136,0.08)', icon: <CheckCircleOutlined />, label: '成功' },
    failed: { color: '#c75050', bg: 'rgba(199,80,80,0.08)', icon: <CloseCircleOutlined />, label: '失败' },
    pending: { color: '#2d6a4f', bg: 'rgba(45,106,79,0.08)', icon: <ClockCircleOutlined spin />, label: '进行中' },
  }
  const st = statusConfig[record.status] || statusConfig.pending

  return (
    <div style={{
      background: 'var(--surface-0, #fff)',
      borderRadius: 16,
      border: '1px solid var(--border)',
      overflow: 'hidden',
      transition: 'all 0.2s ease',
      position: 'relative',
    }}
      onMouseEnter={e => {
        e.currentTarget.style.boxShadow = '0 8px 32px rgba(0,0,0,0.06)'
        e.currentTarget.style.transform = 'translateY(-2px)'
      }}
      onMouseLeave={e => {
        e.currentTarget.style.boxShadow = 'none'
        e.currentTarget.style.transform = 'translateY(0)'
      }}
    >
      {/* Left accent bar */}
      <div style={{
        position: 'absolute', left: 0, top: 0, bottom: 0, width: 4,
        background: `linear-gradient(180deg, ${pColor}, ${pColor}88)`,
        borderRadius: '4px 0 0 4px',
      }} />

      {/* Header */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '16px 20px 12px 20px',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          {/* Platform badge */}
          <div style={{
            display: 'inline-flex', alignItems: 'center', gap: 6,
            padding: '4px 12px 4px 8px',
            borderRadius: 20,
            background: `${pColor}12`,
            border: `1px solid ${pColor}20`,
          }}>
            <div style={{
              width: 8, height: 8, borderRadius: '50%',
              background: pColor,
            }} />
            <Text style={{ color: pColor, fontSize: 12, fontWeight: 700, fontFamily: 'var(--font-body)' }}>
              {pLabel}
            </Text>
          </div>

          {/* Target name */}
          {record.target_url ? (
            <a
              href={record.target_url}
              target="_blank"
              rel="noopener noreferrer"
              style={{
                color: 'var(--text-primary)', fontWeight: 700, fontSize: 15,
                textDecoration: 'none', display: 'flex', alignItems: 'center', gap: 4,
              }}
            >
              {record.target_name}
              <LinkOutlined style={{ fontSize: 11, color: 'var(--text-muted)', opacity: 0.5 }} />
            </a>
          ) : (
            <Text style={{ color: 'var(--text-primary)', fontWeight: 700, fontSize: 15 }}>
              {record.target_name}
            </Text>
          )}

          {/* Type tag */}
          {!isSocial && <Tag color="blue" style={{ fontSize: 11, lineHeight: '18px', padding: '0 6px' }}>网站</Tag>}
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          {/* Status */}
          <div style={{
            display: 'inline-flex', alignItems: 'center', gap: 5,
            padding: '3px 10px', borderRadius: 12,
            background: st.bg, color: st.color, fontSize: 12, fontWeight: 600,
          }}>
            {st.icon}
            {st.label}
          </div>

          {/* Time */}
          <Tooltip title={record.created_at}>
            <Text style={{ color: 'var(--text-muted)', fontSize: 12, fontFamily: 'var(--font-mono)' }}>
              {relativeTime(record.created_at)}
            </Text>
          </Tooltip>

          {/* Delete */}
          <Popconfirm title="确定删除此记录？" onConfirm={() => onDelete(record.id)} okButtonProps={{ danger: true }}>
            <DeleteOutlined style={{ color: 'var(--text-muted)', fontSize: 13, cursor: 'pointer', opacity: 0.4 }}
              onMouseEnter={e => (e.currentTarget.style.opacity = '1')}
              onMouseLeave={e => (e.currentTarget.style.opacity = '0.4')}
            />
          </Popconfirm>
        </div>
      </div>

      {/* Post Content */}
      {record.raw_content && (() => {
        try {
          const posts = JSON.parse(record.raw_content)
          if (!Array.isArray(posts) || posts.length === 0) return null
          return (
            <div style={{ padding: '0 20px 12px 20px' }}>
              <div style={{
                display: 'flex', alignItems: 'center', gap: 6,
                marginBottom: 8,
              }}>
                <FileTextOutlined style={{ color: 'var(--accent)', fontSize: 12 }} />
                <Text style={{
                  color: 'var(--accent)', fontSize: 10, fontWeight: 700,
                  textTransform: 'uppercase', letterSpacing: 1.5,
                  fontFamily: 'var(--font-body)',
                }}>
                  贴文内容
                </Text>
                <Tag style={{
                  background: 'var(--surface-1)', color: 'var(--text-muted)',
                  border: '1px solid var(--border)', borderRadius: 10, padding: '0 6px',
                  fontSize: 10, lineHeight: '16px',
                }}>
                  {posts.length}
                </Tag>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {(postsExpanded ? posts : posts.slice(0, 3)).map((post: any, i: number) => (
                  <div key={i} style={{
                    padding: '10px 14px',
                    background: 'var(--surface-1, #f8faf9)',
                    borderRadius: 10,
                    border: '1px solid var(--border)',
                  }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4, flexWrap: 'wrap' }}>
                      {post.title && (
                        <span
                          style={{
                            color: 'var(--text-primary)', fontSize: 13, fontWeight: 600,
                            fontFamily: 'var(--font-body)',
                          }}
                          dangerouslySetInnerHTML={{ __html: sanitizeContent(post.title) }}
                        />
                      )}
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginLeft: 'auto' }}>
                        {post.likes > 0 && (
                          <div style={{ display: 'inline-flex', alignItems: 'center', gap: 2, color: '#2d6a4f', fontSize: 10 }}>
                            <HeartOutlined />
                            <Text style={{ color: '#2d6a4f', fontFamily: 'var(--font-mono)', fontSize: 10 }}>{post.likes}</Text>
                          </div>
                        )}
                        {post.comments_count > 0 && (
                          <Text style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', fontSize: 10 }}>
                            {post.comments_count} 评论
                          </Text>
                        )}
                        {post.url && (
                          <a href={post.url} target="_blank" rel="noopener noreferrer"
                            style={{ color: 'var(--accent)', fontSize: 10, opacity: 0.7 }}
                            onClick={e => e.stopPropagation()}
                          >
                            原文
                          </a>
                        )}
                      </div>
                    </div>
                    {post.content && (
                      <div
                        style={{
                          color: 'var(--text-secondary)', fontSize: 12, lineHeight: '18px',
                          maxHeight: postsExpanded ? 'none' : '36px', overflow: 'hidden',
                        }}
                        dangerouslySetInnerHTML={{ __html: sanitizeContent(post.content) }}
                      />
                    )}
                  </div>
                ))}
                {posts.length > 3 && !postsExpanded && (
                  <div
                    onClick={() => setPostsExpanded(true)}
                    style={{
                      color: 'var(--accent)', fontSize: 11, textAlign: 'center',
                      cursor: 'pointer', padding: '4px 0',
                      textDecoration: 'underline',
                    }}
                  >
                    展开全部 {posts.length} 篇贴文
                  </div>
                )}
                {postsExpanded && posts.length > 3 && (
                  <div
                    onClick={() => setPostsExpanded(false)}
                    style={{
                      color: 'var(--text-muted)', fontSize: 11, textAlign: 'center',
                      cursor: 'pointer', padding: '4px 0',
                      textDecoration: 'underline',
                    }}
                  >
                    收起
                  </div>
                )}
              </div>
            </div>
          )
        } catch { return null }
      })()}

      {/* AI Summary */}
      {cleaned ? (
        <div style={{ padding: '0 20px 16px 20px' }}>
          <div style={{
            background: 'linear-gradient(135deg, rgba(45,106,79,0.03), rgba(90,122,154,0.03))',
            border: '1px solid var(--border)',
            borderRadius: 12,
            padding: '14px 18px',
            position: 'relative',
          }}>
            <div style={{
              display: 'flex', alignItems: 'center', gap: 6,
              marginBottom: 8,
            }}>
              <RobotOutlined style={{ color: 'var(--accent)', fontSize: 13 }} />
              <Text style={{
                color: 'var(--accent)', fontSize: 11, fontWeight: 700,
                textTransform: 'uppercase', letterSpacing: 1.5,
                fontFamily: 'var(--font-body)',
              }}>
                AI 分析
              </Text>
            </div>
            <div
              style={{
                color: 'var(--text-primary)',
                fontSize: 14,
                lineHeight: '24px',
                fontFamily: 'var(--font-body)',
                maxHeight: summaryExpanded ? 'none' : 72,
                overflow: 'hidden',
                position: 'relative',
              }}
            >
              {cleaned}
              {!summaryExpanded && cleaned.length > 120 && (
                <div style={{
                  position: 'absolute', bottom: 0, left: 0, right: 0, height: 32,
                  background: 'linear-gradient(transparent, rgba(248,249,250,0.95))',
                }} />
              )}
            </div>
            {cleaned.length > 120 && (
              <div
                onClick={() => setSummaryExpanded(!summaryExpanded)}
                style={{
                  color: 'var(--accent)', fontSize: 12, fontWeight: 600,
                  cursor: 'pointer', marginTop: 6, fontFamily: 'var(--font-body)',
                }}
              >
                {summaryExpanded ? '收起' : '展开全文'}
              </div>
            )}
          </div>
        </div>
      ) : (
        <div style={{ padding: '0 20px 16px 20px' }}>
          <Text style={{ color: 'var(--text-muted)', fontSize: 13, fontStyle: 'italic' }}>
            {record.status === 'pending' ? '正在分析中...' : '暂无总结'}
          </Text>
        </div>
      )}
    </div>
  )
}

export default function DashboardPage() {
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [targetFilter, setTargetFilter] = useState<string | undefined>(undefined)
  const [typeFilter, setTypeFilter] = useState<string | undefined>(undefined)
  const [statusFilter, setStatusFilter] = useState<string | undefined>(undefined)
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const stopPolling = useCallback(() => {
    if (pollingRef.current) {
      clearInterval(pollingRef.current)
      pollingRef.current = null
    }
  }, [])

  const fetchData = useCallback(async (isPoll = false) => {
    if (!isPoll) setLoading(true)
    try {
      const res = await dashboardAPI.get()
      setData(res.data)
      // Check if we need to start/stop polling
      const hasPending = res.data?.recent_results?.some((r: any) => r.status === 'pending')
      if (hasPending && !pollingRef.current) {
        pollingRef.current = setInterval(() => fetchData(true), 5000)
      } else if (!hasPending) {
        stopPolling()
      }
    } finally {
      if (!isPoll) setLoading(false)
    }
  }, [stopPolling])

  useEffect(() => {
    fetchData()
    return stopPolling
  }, [])

  const handleDelete = async (id: number) => {
    try {
      await resultsAPI.delete(id)
      message.success('删除成功')
      setData((prev: any) => prev ? {
        ...prev,
        recent_results: prev.recent_results.filter((r: any) => r.id !== id),
      } : prev)
    } catch {
      message.error('删除失败')
    }
  }

  if (loading) return (
    <div>
      <div style={{ marginBottom: 32 }}>
        <Skeleton.Input active style={{ width: 200, height: 40, borderRadius: 8 }} />
        <div style={{ height: 8 }} />
        <Skeleton.Input active style={{ width: 260, height: 16, borderRadius: 4 }} />
      </div>
      <Row gutter={[16, 16]} style={{ marginBottom: 32 }}>
        {Array.from({ length: 6 }).map((_, i) => (
          <Col span={4} key={i}>
            <div style={{
              background: '#ffffff', border: '1px solid var(--border)',
              borderRadius: 14, padding: '24px 22px', boxShadow: 'var(--shadow-sm)',
            }}>
              <Skeleton.Input active style={{ width: 80, height: 14, borderRadius: 4 }} />
              <div style={{ height: 12 }} />
              <Skeleton.Input active style={{ width: 60, height: 40, borderRadius: 6 }} />
            </div>
          </Col>
        ))}
      </Row>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} style={{
            background: '#fff', borderRadius: 16, border: '1px solid var(--border)', padding: '20px',
          }}>
            <div style={{ display: 'flex', gap: 12, marginBottom: 12 }}>
              <Skeleton.Input active style={{ width: 60, height: 22, borderRadius: 12 }} />
              <Skeleton.Input active style={{ width: 120, height: 22, borderRadius: 4 }} />
            </div>
            <Skeleton.Input active style={{ width: '100%', height: 60, borderRadius: 8 }} />
          </div>
        ))}
      </div>
    </div>
  )
  if (!data) return null

  const { stats, recent_results } = data

  const targetOptions = Array.from(
    new Map(recent_results.map((r: any) => [r.target_name, r.target_name])).entries()
  ).map(([label]) => ({ value: label as string, label: label as string }))

  const filtered = recent_results.filter((r: any) => {
    if (targetFilter && r.target_name !== targetFilter) return false
    if (typeFilter && r.target_type !== typeFilter) return false
    if (statusFilter && r.status !== statusFilter) return false
    return true
  })

  return (
    <div>
      <div style={{ marginBottom: 32 }}>
        <h1 className="page-title animate-fade-in-up">仪表盘</h1>
        <div className="page-subtitle animate-fade-in-up" style={{ animationDelay: '0.05s' }}>OVERVIEW · 实时监测概览</div>
      </div>

      {/* Stat cards */}
      <Row gutter={[16, 16]} style={{ marginBottom: 32 }}>
        {statCards.map((card, idx) => (
          <Col span={4} key={card.key}>
            <div className={`stat-card animate-fade-in-up delay-${idx + 1}`} style={{
              background: '#ffffff',
              border: '1px solid var(--border)',
              borderRadius: 14,
              padding: '26px 24px',
              position: 'relative',
              overflow: 'hidden',
              boxShadow: 'var(--shadow-sm)',
            }}>
              <div style={{
                position: 'absolute', top: 0, right: 0,
                width: 100, height: 100,
                background: `radial-gradient(circle at top right, ${card.color}08, transparent 70%)`,
                pointerEvents: 'none',
              }} />
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', position: 'relative' }}>
                <div>
                  <Text style={{
                    color: 'var(--text-muted)', fontSize: 11, display: 'block', marginBottom: 12,
                    fontFamily: "var(--font-body)", textTransform: 'uppercase',
                    letterSpacing: 2.5, fontWeight: 600,
                  }}>
                    {card.title}
                  </Text>
                  <div style={{
                    color: card.color, fontSize: 36, fontWeight: 700,
                    fontFamily: "var(--font-mono)", lineHeight: 1,
                  }}>
                    {stats[card.key]}
                  </div>
                </div>
                {card.icon && (
                  <div style={{
                    width: 50, height: 50, borderRadius: 12,
                    background: `${card.color}0a`, border: `1px solid ${card.color}12`,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    color: card.color, fontSize: 22,
                  }}>
                    {card.icon}
                  </div>
                )}
              </div>
            </div>
          </Col>
        ))}
      </Row>

      {/* Monitoring results */}
      <div className="animate-fade-in-up" style={{ animationDelay: '0.3s' }}>
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          marginBottom: 20,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{
              fontSize: 16, fontWeight: 700, color: 'var(--text-primary)',
              fontFamily: 'var(--font-body)',
            }}>
              最近监测结果
            </span>
            <Tag style={{
              background: 'var(--surface-1)', color: 'var(--text-muted)',
              border: '1px solid var(--border)', borderRadius: 10, padding: '1px 10px',
              fontSize: 12,
            }}>
              {filtered.length}
            </Tag>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <FilterOutlined style={{ color: 'var(--text-muted)', fontSize: 13 }} />
            <Select
              value={targetFilter}
              onChange={v => setTargetFilter(v)}
              placeholder="全部目标"
              allowClear
              style={{ width: 140 }}
              size="small"
              options={targetOptions}
            />
            <Select
              value={typeFilter}
              onChange={v => setTypeFilter(v)}
              placeholder="全部类型"
              allowClear
              style={{ width: 100 }}
              size="small"
              options={[
                { value: 'social_media', label: '社交' },
                { value: 'website', label: '网站' },
              ]}
            />
            <Select
              value={statusFilter}
              onChange={v => setStatusFilter(v)}
              placeholder="全部状态"
              allowClear
              style={{ width: 100 }}
              size="small"
              options={[
                { value: 'success', label: '成功' },
                { value: 'failed', label: '失败' },
                { value: 'pending', label: '进行中' },
              ]}
            />
          </div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {filtered.length === 0 ? (
            <div style={{
              textAlign: 'center', padding: '60px 0',
              color: 'var(--text-muted)', fontSize: 14,
            }}>
              暂无监测结果
            </div>
          ) : (
            filtered.map((record: any) => (
              <ResultCard key={record.id} record={record} onDelete={handleDelete} />
            ))
          )}
        </div>
      </div>
    </div>
  )
}
