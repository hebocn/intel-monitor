import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Tag, Typography, Empty, Select, Popconfirm, message, Image, Tooltip, Skeleton, Button } from 'antd'
import {
  CheckCircleOutlined, CloseCircleOutlined, ClockCircleOutlined,
  DeleteOutlined, FilterOutlined, RobotOutlined, FileTextOutlined,
  HeartOutlined, CommentOutlined, LoadingOutlined,
} from '@ant-design/icons'
import { resultsAPI } from '../services/api'

const { Text } = Typography

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

const statusConfig: Record<string, { color: string; bg: string; icon: React.ReactNode; label: string }> = {
  success: { color: '#52b788', bg: 'rgba(82,183,136,0.08)', icon: <CheckCircleOutlined />, label: '成功' },
  failed: { color: '#c75050', bg: 'rgba(199,80,80,0.08)', icon: <CloseCircleOutlined />, label: '失败' },
  pending: { color: '#2d6a4f', bg: 'rgba(45,106,79,0.08)', icon: <ClockCircleOutlined spin />, label: '进行中' },
}

function ResultCard({
  record,
  selected,
  onClick,
  onDelete,
  idx,
}: {
  record: any
  selected: boolean
  onClick: () => void
  onDelete: () => void
  idx: number
}) {
  const st = statusConfig[record.status] || statusConfig.pending
  const cleaned = cleanSummary(record.summary)

  return (
    <div
      className={`animate-fade-in-up delay-${Math.min(idx + 1, 6)}`}
      onClick={onClick}
      style={{
        background: selected ? 'rgba(45,106,79,0.04)' : 'var(--surface-0, #fff)',
        borderRadius: 14,
        border: selected ? '2px solid rgba(45,106,79,0.3)' : '1px solid var(--border)',
        overflow: 'hidden',
        transition: 'all 0.2s ease',
        position: 'relative',
        cursor: 'pointer',
      }}
      onMouseEnter={e => {
        if (!selected) {
          e.currentTarget.style.boxShadow = '0 4px 20px rgba(0,0,0,0.04)'
          e.currentTarget.style.transform = 'translateY(-1px)'
        }
      }}
      onMouseLeave={e => {
        if (!selected) {
          e.currentTarget.style.boxShadow = 'none'
          e.currentTarget.style.transform = 'translateY(0)'
        }
      }}
    >
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '14px 18px',
        gap: 16,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flex: 1, minWidth: 0 }}>
          {/* Date */}
          <Text style={{
            color: 'var(--accent)', fontFamily: 'var(--font-mono)', fontSize: 14, fontWeight: 600,
            minWidth: 100,
          }}>
            {record.monitor_date}
          </Text>

          {/* Status pill */}
          <div style={{
            display: 'inline-flex', alignItems: 'center', gap: 4,
            padding: '2px 10px', borderRadius: 10,
            background: st.bg, color: st.color, fontSize: 11, fontWeight: 600,
          }}>
            {st.icon}
            {st.label}
          </div>

          {/* Summary preview */}
          <Text style={{
            color: 'var(--text-secondary)', fontSize: 13,
            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
            flex: 1,
          }}>
            {cleaned ? cleaned.slice(0, 80) + (cleaned.length > 80 ? '...' : '') : '暂无总结'}
          </Text>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Text style={{ color: 'var(--text-muted)', fontSize: 11, fontFamily: 'var(--font-mono)' }}>
            {relativeTime(record.created_at)}
          </Text>
          <Popconfirm
            title="确定删除此记录？"
            onConfirm={e => { e?.stopPropagation(); onDelete() }}
            onCancel={e => e?.stopPropagation()}
            okButtonProps={{ danger: true }}
          >
            <DeleteOutlined
              onClick={e => e.stopPropagation()}
              style={{ color: 'var(--text-muted)', fontSize: 12, cursor: 'pointer', opacity: 0.4 }}
              onMouseEnter={e => (e.currentTarget.style.opacity = '1')}
              onMouseLeave={e => (e.currentTarget.style.opacity = '0.4')}
            />
          </Popconfirm>
        </div>
      </div>
    </div>
  )
}

function CommentCard({ comment, rank, compact = false }: { comment: any; rank: number; compact?: boolean }) {
  const isTop3 = rank <= 3
  return (
    <div style={{
      display: 'flex', gap: 14, alignItems: 'flex-start',
      padding: '12px 16px',
      background: isTop3 ? 'rgba(45,106,79,0.03)' : 'var(--surface-0, #fff)',
      borderRadius: 12,
      border: isTop3 ? '1px solid rgba(45,106,79,0.12)' : '1px solid var(--border)',
    }}>
      {/* Rank */}
      <div style={{
        minWidth: 30, height: 30, borderRadius: 10,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        background: isTop3 ? '#2d6a4f' : 'var(--surface-1)',
        color: isTop3 ? '#fff' : 'var(--text-muted)',
        fontFamily: 'var(--font-mono)', fontSize: 12, fontWeight: 700,
      }}>
        {rank}
      </div>

      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
          <Text style={{ color: 'var(--text-primary)', fontWeight: 600, fontSize: 13 }}>
            {comment.author}
          </Text>
          <div style={{
            display: 'inline-flex', alignItems: 'center', gap: 3,
            color: '#2d6a4f', fontSize: 11,
          }}>
            <HeartOutlined />
            <Text style={{ color: '#2d6a4f', fontFamily: 'var(--font-mono)', fontSize: 11 }}>
              {comment.likes_count}
            </Text>
          </div>
          {comment.reply_count > 0 && (
            <Text style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', fontSize: 11 }}>
              {comment.reply_count} 回复
            </Text>
          )}
          {comment.retweet_count > 0 && (
            <Text style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', fontSize: 11 }}>
              {comment.retweet_count} 转发
            </Text>
          )}
        </div>
        <Text style={{
          color: 'var(--text-secondary)', fontSize: 13, lineHeight: '20px',
          display: '-webkit-box', WebkitLineClamp: compact ? 2 : 3, WebkitBoxOrient: 'vertical', overflow: 'hidden',
        }}>
          {comment.comment_text}
        </Text>
      </div>
    </div>
  )
}

export default function MonitorDetailPage() {
  const { type, id } = useParams<{ type: string; id: string }>()
  const [results, setResults] = useState<any[]>([])
  const [selectedResult, setSelectedResult] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [statusFilter, setStatusFilter] = useState<string | undefined>(undefined)
  const [fetchingUrls, setFetchingUrls] = useState<Record<string, boolean>>({})
  const [cooldownUrls, setCooldownUrls] = useState<Record<string, number>>({})

  const fetchResults = () => {
    if (!id) return
    setLoading(true)
    const params: any = { target_id: Number(id), target_type: type }
    if (statusFilter) params.status = statusFilter
    resultsAPI.list(params)
      .then(res => setResults(res.data))
      .finally(() => setLoading(false))
  }

  useEffect(() => { fetchResults() }, [id, type, statusFilter])

  const loadDetail = async (resultId: number) => {
    const res = await resultsAPI.detail(resultId)
    setSelectedResult(res.data)
  }

  // 点击「获取评论」：抓取 + 存库 + 触发后台 AI 精选；成功后刷新详情
  const handleFetchComments = async (resultId: number, postUrl: string) => {
    setFetchingUrls(prev => ({ ...prev, [postUrl]: true }))
    try {
      await resultsAPI.fetchComments(resultId, postUrl)
      message.success('评论获取成功')
      setCooldownUrls(prev => ({ ...prev, [postUrl]: Date.now() + 5000 }))
      await loadDetail(resultId)
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '评论获取失败')
    } finally {
      setFetchingUrls(prev => ({ ...prev, [postUrl]: false }))
    }
  }

  // AI 精选状态轮询：selecting 时每 3s 刷新详情，直到 done
  useEffect(() => {
    if (!selectedResult || selectedResult.comments_ai_status !== 'selecting') return
    const timer = setInterval(async () => {
      const res = await resultsAPI.detail(selectedResult.id)
      setSelectedResult(res.data)
      if (res.data.comments_ai_status === 'done') clearInterval(timer)
    }, 3000)
    return () => clearInterval(timer)
  }, [selectedResult?.id, selectedResult?.comments_ai_status])

  const handleDelete = async (resultId: number) => {
    try {
      await resultsAPI.delete(resultId)
      message.success('删除成功')
      if (selectedResult?.id === resultId) setSelectedResult(null)
      fetchResults()
    } catch {
      message.error('删除失败')
    }
  }

  return (
    <div>
      <div style={{ marginBottom: 28 }}>
        <h1 className="page-title animate-fade-in-up">监测详情</h1>
        <div className="page-subtitle animate-fade-in-up" style={{ animationDelay: '0.05s' }}>
          {type === 'social_media' ? 'SOCIAL' : 'WEBSITE'} · TARGET #{id}
        </div>
      </div>

      {/* Results list */}
      <div className="animate-fade-in-up" style={{ animationDelay: '0.1s', marginBottom: 24 }}>
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          marginBottom: 16,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{
              fontSize: 16, fontWeight: 700, color: 'var(--text-primary)',
              fontFamily: 'var(--font-body)',
            }}>
              监测记录
            </span>
            <Tag style={{
              background: 'var(--surface-1)', color: 'var(--text-muted)',
              border: '1px solid var(--border)', borderRadius: 10, padding: '1px 10px',
              fontSize: 12,
            }}>
              {results.length}
            </Tag>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <FilterOutlined style={{ color: 'var(--text-muted)', fontSize: 13 }} />
            <Select
              value={statusFilter}
              onChange={v => { setStatusFilter(v); setSelectedResult(null) }}
              placeholder="全部状态"
              allowClear
              style={{ width: 120 }}
              size="small"
              options={[
                { value: 'success', label: '成功' },
                { value: 'failed', label: '失败' },
                { value: 'pending', label: '进行中' },
              ]}
            />
          </div>
        </div>

        {loading ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} style={{
                background: '#fff', borderRadius: 14, border: '1px solid var(--border)', padding: '16px 18px',
              }}>
                <div style={{ display: 'flex', gap: 12 }}>
                  <Skeleton.Input active style={{ width: 100, height: 18, borderRadius: 4 }} />
                  <Skeleton.Input active style={{ width: 50, height: 18, borderRadius: 10 }} />
                  <Skeleton.Input active style={{ width: 200, height: 18, borderRadius: 4 }} />
                </div>
              </div>
            ))}
          </div>
        ) : results.length === 0 ? (
          <div style={{
            textAlign: 'center', padding: '60px 0',
            color: 'var(--text-muted)', fontSize: 14,
          }}>
            暂无监测记录
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {results.map((record, idx) => (
              <ResultCard
                key={record.id}
                record={record}
                selected={selectedResult?.id === record.id}
                onClick={() => loadDetail(record.id)}
                onDelete={() => handleDelete(record.id)}
                idx={idx}
              />
            ))}
          </div>
        )}
      </div>

      {/* Detail panel */}
      {selectedResult && (
        <div className="animate-fade-in-up" style={{ animationDelay: '0.05s' }}>
          <div style={{
            display: 'flex', alignItems: 'center', gap: 8,
            marginBottom: 20,
          }}>
            <FileTextOutlined style={{ color: 'var(--accent)', fontSize: 16 }} />
            <span style={{
              fontSize: 16, fontWeight: 700, color: 'var(--text-primary)',
              fontFamily: 'var(--font-body)',
            }}>
              结果详情
            </span>
            <Tag style={{
              background: 'var(--surface-1)', color: 'var(--accent)',
              border: '1px solid var(--border)', borderRadius: 10, padding: '1px 10px',
              fontSize: 12, fontFamily: 'var(--font-mono)',
            }}>
              {selectedResult.monitor_date}
            </Tag>
            <div style={{
              display: 'inline-flex', alignItems: 'center', gap: 4,
              padding: '2px 10px', borderRadius: 10,
              background: (statusConfig[selectedResult.status] || statusConfig.pending).bg,
              color: (statusConfig[selectedResult.status] || statusConfig.pending).color,
              fontSize: 11, fontWeight: 600,
            }}>
              {(statusConfig[selectedResult.status] || statusConfig.pending).icon}
              {(statusConfig[selectedResult.status] || statusConfig.pending).label}
            </div>
          </div>

          {/* Post Content */}
          {selectedResult.raw_content && (() => {
            try {
              const posts = JSON.parse(selectedResult.raw_content)
              if (!Array.isArray(posts) || posts.length === 0) return null
              return (
                <div style={{ marginBottom: 20 }}>
                  <div style={{
                    display: 'flex', alignItems: 'center', gap: 6,
                    marginBottom: 12,
                  }}>
                    <FileTextOutlined style={{ color: 'var(--accent)', fontSize: 13 }} />
                    <Text style={{
                      color: 'var(--accent)', fontSize: 11, fontWeight: 700,
                      textTransform: 'uppercase', letterSpacing: 1.5,
                      fontFamily: 'var(--font-body)',
                    }}>
                      贴文内容
                    </Text>
                    <Tag style={{
                      background: 'var(--surface-1)', color: 'var(--text-muted)',
                      border: '1px solid var(--border)', borderRadius: 10, padding: '0 8px',
                      fontSize: 11,
                    }}>
                      {posts.length}
                    </Tag>
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                    {posts.map((post: any, i: number) => (
                      <div key={i} style={{
                        padding: '16px 20px',
                        background: 'var(--surface-0, #fff)',
                        borderRadius: 14,
                        border: '1px solid var(--border)',
                      }}>
                        {/* 作者头像 + 名字 */}
                        {(post.author_name || post.author_avatar) && (
                          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                            {post.author_avatar && (
                              <img
                                src={post.author_avatar}
                                alt={post.author_name}
                                style={{ width: 24, height: 24, borderRadius: '50%', objectFit: 'cover' }}
                              />
                            )}
                            {post.author_name && (
                              <span style={{ color: 'var(--text-secondary)', fontSize: 12, fontWeight: 500 }}>
                                {post.author_name}
                              </span>
                            )}
                          </div>
                        )}
                        {/* 帖子标题 + 元信息 */}
                        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8, flexWrap: 'wrap' }}>
                          {post.title && (
                            <span
                              style={{
                                color: 'var(--text-primary)', fontSize: 14, fontWeight: 600,
                                fontFamily: 'var(--font-body)',
                              }}
                              dangerouslySetInnerHTML={{ __html: sanitizeContent(post.title) }}
                            />
                          )}
                          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginLeft: 'auto' }}>
                            {post.published_at && (
                              <Text style={{
                                color: 'var(--text-muted)', fontSize: 11,
                                fontFamily: 'var(--font-mono)',
                              }}>
                                {post.published_at}
                              </Text>
                            )}
                            {post.likes > 0 && (
                              <div style={{ display: 'inline-flex', alignItems: 'center', gap: 3, color: '#2d6a4f', fontSize: 11 }}>
                                <HeartOutlined />
                                <Text style={{ color: '#2d6a4f', fontFamily: 'var(--font-mono)', fontSize: 11 }}>
                                  {post.likes}
                                </Text>
                              </div>
                            )}
                            {post.comments_count > 0 && (
                              <div style={{ display: 'inline-flex', alignItems: 'center', gap: 3, color: 'var(--text-muted)', fontSize: 11 }}>
                                <Text style={{ fontFamily: 'var(--font-mono)', fontSize: 11 }}>
                                  {post.comments_count} 评论
                                </Text>
                              </div>
                            )}
                          </div>
                        </div>
                        {/* 帖子正文 */}
                        {post.content && (
                          <div
                            style={{
                              color: 'var(--text-secondary)', fontSize: 13, lineHeight: '22px',
                            }}
                            dangerouslySetInnerHTML={{ __html: sanitizeContent(post.content) }}
                          />
                        )}
                        {/* 帖子链接 */}
                        {post.url && (
                          <a
                            href={post.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            style={{
                              color: 'var(--accent)', fontSize: 12,
                              marginTop: 8, display: 'inline-block',
                              opacity: 0.7,
                            }}
                            onClick={e => e.stopPropagation()}
                          >
                            查看原文
                          </a>
                        )}

                        {/* 帖子图片 */}
                        {post.images && post.images.length > 0 && (
                          <div style={{ marginTop: 12 }}>
                            <Image.PreviewGroup>
                              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                                {post.images.slice(0, 9).map((url: string, imgIdx: number) => (
                                  <Image
                                    key={imgIdx}
                                    src={url}
                                    width={96}
                                    height={96}
                                    style={{ objectFit: 'cover', borderRadius: 10 }}
                                    fallback="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAACklEQVR4nGMAAQAABQABDQottAAAAABJRU5ErkJggg=="
                                  />
                                ))}
                              </div>
                            </Image.PreviewGroup>
                          </div>
                        )}

                        {/* 获取评论按钮 */}
                        {post.url && (
                          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 12 }}>
                            <Button
                              size="small"
                              icon={fetchingUrls[post.url] ? <LoadingOutlined /> : <CommentOutlined />}
                              onClick={() => handleFetchComments(selectedResult.id, post.url)}
                              disabled={!!fetchingUrls[post.url] || Date.now() < (cooldownUrls[post.url] || 0)}
                            >
                              {fetchingUrls[post.url] ? '获取中...' : (Date.now() < (cooldownUrls[post.url] || 0) ? '冷却中' : '获取评论')}
                            </Button>
                            {(selectedResult.hot_comments || []).some((c: any) => c.post_url === post.url) && (
                              <Text style={{ color: 'var(--text-muted)', fontSize: 12 }}>
                                {(selectedResult.hot_comments || []).filter((c: any) => c.post_url === post.url).length} 条评论
                              </Text>
                            )}
                          </div>
                        )}

                        {/* 帖内热门评论 TOP10 */}
                        {(selectedResult.hot_comments || []).filter((c: any) => c.post_url === post.url).length > 0 && (
                          <div style={{ marginTop: 14 }}>
                            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                              {(selectedResult.hot_comments || [])
                                .filter((c: any) => c.post_url === post.url)
                                .sort((a: any, b: any) => a.rank - b.rank)
                                .slice(0, 10)
                                .map((comment: any) => (
                                  <CommentCard key={comment.id} comment={comment} rank={comment.rank} compact />
                                ))}
                            </div>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )
            } catch { return null }
          })()}

          {/* AI Summary */}
          {selectedResult.summary && (
            <div style={{ marginBottom: 20 }}>
              <div style={{
                background: 'linear-gradient(135deg, rgba(45,106,79,0.03), rgba(90,122,154,0.03))',
                border: '1px solid var(--border)',
                borderRadius: 16,
                padding: '20px 24px',
                position: 'relative',
              }}>
                <div style={{
                  display: 'flex', alignItems: 'center', gap: 6,
                  marginBottom: 12,
                }}>
                  <RobotOutlined style={{ color: 'var(--accent)', fontSize: 14 }} />
                  <Text style={{
                    color: 'var(--accent)', fontSize: 11, fontWeight: 700,
                    textTransform: 'uppercase', letterSpacing: 1.5,
                    fontFamily: 'var(--font-body)',
                  }}>
                    AI 分析
                  </Text>
                </div>
                <div style={{
                  color: 'var(--text-primary)',
                  fontSize: 14,
                  lineHeight: '26px',
                  fontFamily: 'var(--font-body)',
                }}>
                  {selectedResult.summary}
                </div>
              </div>
            </div>
          )}

          {/* Hot Comments (global TOP10) */}
          {(() => {
            const all = (selectedResult.hot_comments || []) as any[]
            const global = all.filter((c: any) => c.global_rank > 0).sort((a: any, b: any) => a.global_rank - b.global_rank)
            const empty = all.length === 0
            return (
              <div style={{ marginBottom: 20 }}>
                <div style={{
                  display: 'flex', alignItems: 'center', gap: 6,
                  marginBottom: 12,
                }}>
                  <HeartOutlined style={{ color: '#2d6a4f', fontSize: 13 }} />
                  <Text style={{
                    color: 'var(--accent)', fontSize: 11, fontWeight: 700,
                    textTransform: 'uppercase', letterSpacing: 1.5,
                    fontFamily: 'var(--font-body)',
                  }}>
                    热门评论
                  </Text>
                  {!empty && global.length > 0 && (
                    <Tag style={{
                      background: 'var(--surface-1)', color: 'var(--text-muted)',
                      border: '1px solid var(--border)', borderRadius: 10, padding: '0 8px',
                      fontSize: 11,
                    }}>
                      TOP {Math.min(global.length, 10)}
                    </Tag>
                  )}
                  {!empty && selectedResult.comments_ai_status === 'selecting' && (
                    <Tag color="processing" style={{ fontSize: 11, borderRadius: 10 }}>
                      <LoadingOutlined /> AI 精选中...
                    </Tag>
                  )}
                </div>
                {empty ? (
                  <div style={{
                    padding: '20px 24px',
                    background: 'var(--surface-0, #fff)',
                    borderRadius: 14,
                    border: '1px dashed var(--border)',
                    textAlign: 'center',
                    color: 'var(--text-muted)',
                    fontSize: 13,
                  }}>
                    暂无评论，点击帖子下方的「获取评论」按钮抓取
                  </div>
                ) : global.length > 0 ? (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    {global.slice(0, 10).map((comment: any, i: number) => (
                      <CommentCard key={comment.id} comment={comment} rank={comment.global_rank} />
                    ))}
                  </div>
                ) : (
                  <div style={{
                    padding: '20px 24px',
                    background: 'var(--surface-0, #fff)',
                    borderRadius: 14,
                    border: '1px dashed var(--border)',
                    textAlign: 'center',
                    color: 'var(--text-muted)',
                    fontSize: 13,
                  }}>
                    AI 精选进行中，稍后自动更新...
                  </div>
                )}
              </div>
            )
          })()}

          {/* Error message */}
          {selectedResult.error_message && (
            <div style={{ marginBottom: 20 }}>
              <div style={{
                display: 'flex', alignItems: 'center', gap: 6,
                marginBottom: 12,
              }}>
                <CloseCircleOutlined style={{ color: '#c75050', fontSize: 13 }} />
                <Text style={{
                  color: '#c75050', fontSize: 11, fontWeight: 700,
                  textTransform: 'uppercase', letterSpacing: 1.5,
                  fontFamily: 'var(--font-body)',
                }}>
                  错误信息
                </Text>
              </div>
              <div style={{
                color: '#c75050',
                padding: '18px 22px',
                background: 'rgba(199,80,80,0.04)',
                borderRadius: 14,
                border: '1px solid rgba(199,80,80,0.1)',
                fontSize: 14, lineHeight: '22px',
              }}>
                {selectedResult.error_message}
              </div>
            </div>
          )}
        </div>
      )}

      {!selectedResult && !loading && results.length > 0 && (
        <div style={{
          textAlign: 'center', padding: '60px 0',
          color: 'var(--text-muted)', fontSize: 14,
        }}>
          点击上方记录查看详情
        </div>
      )}
    </div>
  )
}
