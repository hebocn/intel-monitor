import { useEffect, useState, useRef, useCallback } from 'react'
import {
  Input, Button, Tag, Space, message, Skeleton, Empty, Spin, Row, Col,
  Avatar, Card, Progress, Divider, Tooltip, Radio, Select,
} from 'antd'
import {
  SearchOutlined, ClockCircleOutlined, CheckCircleOutlined,
  SyncOutlined, CloseCircleOutlined, SwapOutlined,
  DeleteOutlined, ReloadOutlined, UserOutlined, TeamOutlined,
  LinkOutlined, AimOutlined, UserSwitchOutlined, ProfileOutlined,
} from '@ant-design/icons'
import { accountMatchAPI } from '../services/api'

// ── Types ────────────────────────────────────────────────────────────────
interface Candidate {
  id: number; task_id: number; platform: string
  platform_uid: string; nickname: string
  avatar_url: string | null; bio: string | null; followers_count: number
  profile_url: string | null; profile_json: string | null; posts_json: string | null
  match_score: number; score_detail_json: string | null; matched_with: string | null
}
interface MatchResult {
  id: number; task_id: number; group_label: string; confidence_score: number
  account_ids_json: string; ai_analysis: string | null; score_detail: string | null
}
interface MatchTask {
  id: number; target_name: string; platforms: string; status: string
  match_mode: string; total_candidates: number; total_groups: number
  error_log: string | null; anchor_profile_json: string | null
  created_at: string; completed_at: string | null
  candidates?: Candidate[]; results?: MatchResult[]
}

// ── Constants ────────────────────────────────────────────────────────────
const PLATFORM_COLORS: Record<string, string> = { weibo: '#e6162d', x: '#000000' }
const PLATFORM_LABELS: Record<string, string> = { weibo: '微博', x: 'X' }
const STATUS_MAP: Record<string, { color: string; icon: any; text: string }> = {
  pending:            { color: '#f59e0b', icon: <ClockCircleOutlined />, text: '等待' },
  searching:          { color: '#3b82f6', icon: <SyncOutlined spin />, text: '搜索中' },
  fetching_posts:     { color: '#3b82f6', icon: <SyncOutlined spin />, text: '抓取帖子' },
  fetching_anchor:    { color: '#3b82f6', icon: <SyncOutlined spin />, text: '获取锚点用户' },
  profiling:          { color: '#8b5cf6', icon: <SyncOutlined spin />, text: '画像分析' },
  comparing:          { color: '#ec4899', icon: <SyncOutlined spin />, text: '相似度计算' },
  completed:          { color: '#10b981', icon: <CheckCircleOutlined />, text: '完成' },
  failed:             { color: '#ef4444', icon: <CloseCircleOutlined />, text: '失败' },
}
const R = { sm: 8, md: 12, lg: 16, xl: 20 }

// ── Helpers ──────────────────────────────────────────────────────────────
const fmt   = (n: number) => n >= 10000 ? `${(n / 10000).toFixed(1)}万` : n.toLocaleString()
const fmtDt = (iso: string | null): string => {
  if (!iso) return ''
  const d = iso.endsWith('Z') || iso.includes('+') ? new Date(iso) : new Date(iso + 'Z')
  return d.toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Shanghai' })
}
const fmtScore = (s: number) => `${(s * 100).toFixed(0)}%`

// ── Sub-Components ───────────────────────────────────────────────────────
function ConfidenceBadge({ score }: { score: number }) {
  const palette = score >= 0.7 ? { bg: '#f0fdf4', c: '#16a34a', b: '#bbf7d0' }
    : score >= 0.5 ? { bg: '#fffbeb', c: '#d97706', b: '#fde68a' }
    : score >= 0.3 ? { bg: '#eff6ff', c: '#2563eb', b: '#bfdbfe' }
    :               { bg: '#f8fafc', c: '#94a3b8', b: '#e2e8f0' }
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 4,
      background: palette.bg, color: palette.c, border: `1px solid ${palette.b}`,
      borderRadius: R.sm, padding: '4px 12px', fontWeight: 700, fontSize: 15,
      fontFamily: "'Fira Code', 'SF Mono', monospace",
    }}><AimOutlined style={{ fontSize: 12 }} />{fmtScore(score)}</span>
  )
}

function CandidateCard({ candidate, result }: { candidate: Candidate; result?: MatchResult }) {
  const hasScore = candidate.match_score > 0
  const scorePct = hasScore ? `${(candidate.match_score * 100).toFixed(0)}%` : null
  return (
    <div style={{
      padding: '14px 16px', borderRadius: R.md,
      border: `1px solid ${PLATFORM_COLORS[candidate.platform]}20`,
      borderLeftWidth: 3, borderLeftColor: PLATFORM_COLORS[candidate.platform] || '#3b82f6',
      background: '#fafafa',
    }}>
      {hasScore && (
        <div style={{
          float: 'right', padding: '2px 8px', borderRadius: 10,
          background: '#f0fdf4', border: '1px solid #bbf7d0',
          fontSize: 12, fontWeight: 700, color: '#16a34a',
          fontFamily: "'Fira Code', monospace",
        }}>{scorePct}</div>
      )}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
        <Tag color={PLATFORM_COLORS[candidate.platform]} style={{ margin: 0, borderRadius: 6, fontSize: 11 }}>
          {PLATFORM_LABELS[candidate.platform] || candidate.platform}
        </Tag>
        {candidate.profile_url && (
          <Tooltip title="查看主页">
            <Button type="link" size="small" icon={<LinkOutlined />}
              href={candidate.profile_url} target="_blank" rel="noopener noreferrer" />
          </Tooltip>
        )}
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
        <Avatar size={40} src={candidate.avatar_url} icon={<UserOutlined />} style={{ flexShrink: 0 }} />
        <div style={{ minWidth: 0 }}>
          <div style={{ fontWeight: 600, fontSize: 14, color: '#1e293b', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {candidate.nickname}
          </div>
          <div style={{ fontSize: 11, color: '#94a3b8' }}>
            @{candidate.platform_uid}
            {candidate.followers_count > 0 && ` · ${fmt(candidate.followers_count)} 粉丝`}
          </div>
        </div>
      </div>
      {candidate.bio && (
        <div style={{ fontSize: 12, color: '#64748b', marginBottom: 8, lineHeight: 1.5, display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
          {candidate.bio}
        </div>
      )}
      <ProfileCard profileJson={candidate.profile_json} />
      {candidate.score_detail_json && (
        <div style={{ marginTop: 6, fontSize: 11, color: '#94a3b8', display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          {(() => {
            try {
              const sd = JSON.parse(candidate.score_detail_json)
              const labels: Record<string, string> = { name_similarity: '昵称', content_similarity: '内容', time_pattern_similarity: '时间', ai_judgment: 'AI' }
              return Object.entries(sd).map(([k, v]) => (
                <span key={k}>{labels[k]||k}: {((v as number)*100).toFixed(0)}%</span>
              ))
            } catch { return null }
          })()}
        </div>
      )}
    </div>
  )
}

function ProfileCard({ profileJson, compact }: { profileJson: string | null; compact?: boolean }) {
  if (!profileJson) return null
  try {
    const p = JSON.parse(profileJson)
    if (!p || Object.keys(p).length === 0) return null
    return (
      <div style={{ marginTop: 6, background: '#f8fafc', borderRadius: 8, padding: '8px 12px', fontSize: 12, lineHeight: 1.8 }}>
        {p.summary && <div style={{ color: '#334155', fontWeight: 500, marginBottom: 4 }}>📝 {p.summary}</div>}
        <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', color: '#64748b' }}>
          {p.domain && <span>🏷 {p.domain}</span>}
          {p.tone && <span>💬 {p.tone}</span>}
          {p.lang && <span>🌐 {p.lang.toUpperCase()}</span>}
          {p.activity_level && <span>📊 活跃度: {p.activity_level}</span>}
        </div>
        {p.keywords && p.keywords.length > 0 && (
          <div style={{ marginTop: 4 }}>
            {p.keywords.map((k: string, i: number) => (
              <Tag key={i} style={{ fontSize: 11, marginBottom: 2 }}>{k}</Tag>
            ))}
          </div>
        )}
      </div>
    )
  } catch { return null }
}

function PulsingDot() {
  return <span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: '50%', background: '#3b82f6', marginRight: 8, animation: 'pulse2 1.5s infinite' }} />
}

// ── Main ─────────────────────────────────────────────────────────────────
export default function AccountMatchPage() {
  const [matchMode, setMatchMode] = useState<string>('nickname')
  const [targetName, setTargetName] = useState('')
  const [selectedPlatforms, setSelectedPlatforms] = useState<string[]>(['weibo', 'x'])
  const [anchorPlatform, setAnchorPlatform] = useState<string>('weibo')
  const [searching, setSearching] = useState(false)
  const [tasks, setTasks] = useState<MatchTask[]>([])
  const [selectedTask, setSelectedTask] = useState<MatchTask | null>(null)
  const [loadingTasks, setLoadingTasks] = useState(true)
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const SUPPORTED_PLATFORMS = [
    { platform: 'weibo', label: '微博' },
    { platform: 'x', label: 'X (Twitter)' },
  ]

  useEffect(() => { fetchTasks() }, [])

  const stopPolling = useCallback(() => {
    if (pollingRef.current) { clearInterval(pollingRef.current); pollingRef.current = null }
  }, [])

  const fetchTasks = async () => {
    try { const r = await accountMatchAPI.listTasks(); setTasks(r.data.tasks) } catch { /* ignore */ }
    setLoadingTasks(false)
  }

  const fetchTaskDetail = async (taskId: number) => {
    try {
      const res = await accountMatchAPI.getTask(taskId)
      setSelectedTask(res.data)
      const isPolling = ['pending', 'searching', 'fetching_posts', 'fetching_anchor', 'profiling', 'comparing'].includes(res.data.status)
        || res.data.status?.startsWith('fetching_anchor:')
      if (isPolling) {
        stopPolling()
        pollingRef.current = setInterval(async () => {
          try {
            const r = await accountMatchAPI.getTask(taskId)
            setSelectedTask(r.data)
            if (r.data.status === 'completed' || r.data.status === 'failed') { stopPolling(); fetchTasks() }
          } catch { stopPolling() }
        }, 3000)
      }
    } catch { message.error('加载失败') }
  }

  const handleSearch = async () => {
    if (!targetName.trim()) { message.warning('请输入目标账号名/UID/URL'); return }
    if (!selectedPlatforms.length) { message.warning('至少选一个平台'); return }
    setSearching(true)
    try {
      const res = await accountMatchAPI.search({
        target_name: targetName.trim(),
        platforms: selectedPlatforms,
        match_mode: matchMode,
        anchor_platform: matchMode === 'profile' ? anchorPlatform : undefined,
      })
      message.success(res.data.message)
      fetchTasks()
      setTimeout(() => fetchTaskDetail(res.data.task_id), 800)
    } catch (err: any) { message.error(err.response?.data?.detail || '搜索失败') }
    setSearching(false)
  }

  const handleDelete = async (id: number) => {
    try { await accountMatchAPI.deleteTask(id); message.success('已删除'); if (selectedTask?.id === id) setSelectedTask(null); fetchTasks() } catch { message.error('删除失败') }
  }

  useEffect(() => () => stopPolling(), [stopPolling])

  const getResultCandidates = (result: MatchResult) => {
    if (!selectedTask?.candidates) return []
    try {
      const ids: number[] = JSON.parse(result.account_ids_json)
      return selectedTask.candidates.filter(c => ids.includes(c.id))
    } catch { return [] }
  }

  const getPlaceholder = () => {
    if (matchMode === 'profile') return '输入微博UID/URL 或 X handle/URL，如：1643123917、@elonmusk、https://x.com/elonmusk...'
    return '输入用户昵称，如：张三、elonmusk...'
  }

  // ── Render ──────────────────────────────────────────────────────────────
  return (
    <div>
      <style>{`@keyframes pulse2{0%,100%{opacity:.4}50%{opacity:1}}`}</style>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 24 }}>
        <div>
          <h1 className="page-title animate-fade-in-up">账号比对</h1>
          <div className="page-subtitle animate-fade-in-up" style={{ animationDelay: '0.05s' }}>
            ACCOUNT MATCH · 跨平台身份关联 · AI 画像分析
          </div>
        </div>
        <Button icon={<ReloadOutlined />} size="small" onClick={() => { fetchTasks(); setSelectedTask(null) }}>刷新</Button>
      </div>

      {/* Search Bar */}
      <div style={{ background: '#fff', borderRadius: R.xl, padding: '24px 28px', marginBottom: 24, border: '1px solid #e2e8f0', boxShadow: '0 1px 3px rgba(0,0,0,0.04)' }}>
        {/* Mode selector */}
        <div style={{ marginBottom: 16 }}>
          <Radio.Group value={matchMode} onChange={e => setMatchMode(e.target.value)} buttonStyle="solid" size="middle">
            <Radio.Button value="nickname">
              <SwapOutlined /> 昵称搜索
            </Radio.Button>
            <Radio.Button value="profile">
              <UserSwitchOutlined /> 锚点画像匹配
            </Radio.Button>
          </Radio.Group>
          <span style={{ marginLeft: 16, fontSize: 12, color: '#94a3b8' }}>
            {matchMode === 'profile'
              ? '输入某个平台账号的UID/URL，自动分析画像并在其他平台搜索相似账号'
              : '输入昵称关键词，在两个平台搜索匹配的账号并生成AI画像'}
          </span>
        </div>
        <Row gutter={[12, 12]}>
          {matchMode === 'profile' && (
            <Col xs={24} md={4}>
              <Select value={anchorPlatform} onChange={setAnchorPlatform} size="large"
                style={{ width: '100%', borderRadius: 10 }}
                options={[
                  { value: 'weibo', label: '📱 微博' },
                  { value: 'x', label: '🐦 X (Twitter)' },
                ]} />
            </Col>
          )}
          <Col xs={24} md={matchMode === 'profile' ? 10 : 14}>
            <Input.Search size="large" placeholder={getPlaceholder()} value={targetName}
              onChange={e => setTargetName(e.target.value)} onSearch={handleSearch} loading={searching}
              enterButton={<span><SwapOutlined /> 开始比对</span>} style={{ borderRadius: 10 }} />
          </Col>
          <Col xs={24} md={6}>
            <div style={{ display: 'flex', gap: 8, height: 40 }}>
              {SUPPORTED_PLATFORMS.map(p => {
                const checked = selectedPlatforms.includes(p.platform)
                return (
                  <button key={p.platform}
                    onClick={() => setSelectedPlatforms(checked ? selectedPlatforms.filter(x => x !== p.platform) : [...selectedPlatforms, p.platform])}
                    style={{
                      flex: 1,
                      height: '100%',
                      borderRadius: 10,
                      fontSize: 14,
                      fontWeight: 600,
                      cursor: 'pointer',
                      border: `2px solid ${checked ? PLATFORM_COLORS[p.platform] : '#e2e8f0'}`,
                      background: checked ? `${PLATFORM_COLORS[p.platform]}10` : '#fff',
                      color: checked ? PLATFORM_COLORS[p.platform] : '#64748b',
                      transition: 'all 0.2s',
                      display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
                    }}>
                    {p.label}
                  </button>
                )
              })}
            </div>
          </Col>
        </Row>
      </div>

      <Row gutter={24}>
        {/* Sidebar — History */}
        <Col xs={24} lg={6}>
          <div style={{ background: '#fff', borderRadius: R.lg, padding: '18px 20px', border: '1px solid #e2e8f0', height: 'calc(100vh - 360px)', overflow: 'auto', boxShadow: '0 1px 3px rgba(0,0,0,0.04)' }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: '#475569', marginBottom: 12, display: 'flex', alignItems: 'center', gap: 6 }}>
              <ClockCircleOutlined />比对历史
              {tasks.length > 0 && <span style={{ color: '#94a3b8', fontWeight: 400 }}>({tasks.length})</span>}
            </div>
            {loadingTasks ? <Skeleton active paragraph={{ rows: 6 }} /> : !tasks.length ? (
              <div style={{ textAlign: 'center', padding: 40, color: '#94a3b8', fontSize: 12 }}>暂无记录</div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                {tasks.map(t => {
                  const active = selectedTask?.id === t.id
                  const statusKey = t.status?.startsWith('fetching_anchor:') ? 'fetching_anchor' : t.status
                  const st = STATUS_MAP[statusKey] || STATUS_MAP.pending
                  const modeLabel = t.match_mode === 'profile' ? '🔗' : '🔍'
                  return (
                    <div key={t.id} onClick={() => { stopPolling(); fetchTaskDetail(t.id) }}
                      style={{
                        padding: '10px 12px', borderRadius: 10, cursor: 'pointer',
                        background: active ? '#eff6ff' : 'transparent',
                        border: active ? '1px solid #bfdbfe' : '1px solid transparent',
                        transition: 'all 0.15s',
                      }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <span style={{ fontWeight: 600, fontSize: 13, color: '#1e293b' }}>
                          {modeLabel} {t.target_name}
                        </span>
                        <span style={{ fontSize: 11, color: st.color, fontWeight: 500 }}>{st.text}</span>
                      </div>
                      <div style={{ fontSize: 11, color: '#94a3b8', marginTop: 3, display: 'flex', justifyContent: 'space-between' }}>
                        <span>{t.total_candidates || 0} 候选 · {t.total_groups || 0} 关联</span>
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
          {!selectedTask ? (
            <div style={{ background: '#fff', borderRadius: R.lg, padding: '80px 20px', textAlign: 'center', border: '1px solid #e2e8f0', boxShadow: '0 1px 3px rgba(0,0,0,0.04)' }}>
              <div style={{ width: 56, height: 56, borderRadius: '50%', background: '#f1f5f9', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', marginBottom: 16 }}>
                <SwapOutlined style={{ fontSize: 24, color: '#cbd5e1' }} />
              </div>
              <div style={{ fontSize: 15, color: '#64748b', fontWeight: 500 }}>选择左侧历史比对查看结果</div>
              <div style={{ fontSize: 12, color: '#94a3b8', marginTop: 4 }}>或在上方输入账号名开始新的比对</div>
            </div>
          ) : (['pending', 'searching', 'fetching_posts', 'profiling', 'comparing'].includes(selectedTask.status) || selectedTask.status?.startsWith('fetching_anchor')) ? (
            <div style={{ background: '#fff', borderRadius: R.lg, padding: '60px 20px', textAlign: 'center', border: '1px solid #e2e8f0', boxShadow: '0 1px 3px rgba(0,0,0,0.04)' }}>
              <Spin size="large" />
              <div style={{ marginTop: 16, fontSize: 14, color: '#475569', fontWeight: 600 }}>
                <PulsingDot />正在比对 "{selectedTask.target_name}"
              </div>
              <div style={{ marginTop: 8, fontSize: 13, color: '#94a3b8' }}>
                {STATUS_MAP[selectedTask.status]?.text || '处理中'}
                {selectedTask.match_mode === 'profile' && <span> · 锚点画像模式</span>}
              </div>
              <Progress percent={selectedTask.status === 'comparing' ? 90 : selectedTask.status === 'profiling' ? 70 : selectedTask.status === 'fetching_posts' ? 50 : 20}
                status="active" showInfo={false} style={{ maxWidth: 300, margin: '16px auto' }} />
            </div>
          ) : selectedTask.status === 'failed' ? (
            <div style={{ background: '#fff', borderRadius: R.lg, padding: 24, border: '1px solid #fecaca' }}>
              <div style={{ color: '#dc2626', fontWeight: 600, marginBottom: 8 }}>比对失败</div>
              {selectedTask.error_log && (
                <pre style={{ fontSize: 11, color: '#7f1d1d', background: '#fef2f2', padding: 12, borderRadius: R.sm, maxHeight: 200, overflow: 'auto', whiteSpace: 'pre-wrap' }}>
                  {JSON.stringify(JSON.parse(selectedTask.error_log), null, 2)}
                </pre>
              )}
              <Button style={{ marginTop: 12 }} onClick={handleSearch}>重新比对</Button>
            </div>
          ) : (
            <div>
              {/* KPI Row */}
              <div style={{ display: 'flex', gap: 12, marginBottom: 16, flexWrap: 'wrap' }}>
                <div style={{ flex: '1 1 140px', background: '#fff', borderRadius: R.md, padding: '14px 18px', border: '1px solid #e2e8f0' }}>
                  <div style={{ fontSize: 11, color: '#94a3b8', marginBottom: 4 }}>候选账号</div>
                  <div style={{ fontSize: 20, fontWeight: 700, color: '#1e3a8a' }}>{selectedTask.total_candidates}</div>
                </div>
                <div style={{ flex: '1 1 140px', background: '#fff', borderRadius: R.md, padding: '14px 18px', border: '1px solid #e2e8f0' }}>
                  <div style={{ fontSize: 11, color: '#94a3b8', marginBottom: 4 }}>匹配结果</div>
                  <div style={{ fontSize: 20, fontWeight: 700, color: '#9a3412' }}>{selectedTask.total_groups}</div>
                </div>
                <div style={{ flex: '1 1 140px', background: '#fff', borderRadius: R.md, padding: '14px 18px', border: '1px solid #e2e8f0' }}>
                  <div style={{ fontSize: 11, color: '#94a3b8', marginBottom: 4 }}>
                    模式 · {selectedTask.match_mode === 'profile' ? '锚点画像' : '昵称搜索'}
                  </div>
                  <div style={{ fontSize: 16, fontWeight: 600, color: '#14532d' }}>{selectedTask.target_name}</div>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginLeft: 'auto' }}>
                  <span style={{ fontSize: 11, color: '#94a3b8' }}>{fmtDt(selectedTask.created_at)}</span>
                  <Button size="small" danger type="text" icon={<DeleteOutlined />} onClick={() => handleDelete(selectedTask.id)} />
                </div>
              </div>

              {/* Anchor profile display (Scenario 1) */}
              {selectedTask.match_mode === 'profile' && selectedTask.anchor_profile_json && (
                <div style={{
                  background: '#f0fdf4', borderRadius: R.lg, padding: '16px 20px',
                  marginBottom: 16, border: '1px solid #bbf7d0',
                }}>
                  <div style={{ fontSize: 13, fontWeight: 600, color: '#166534', marginBottom: 8, display: 'flex', alignItems: 'center', gap: 8 }}>
                    <ProfileOutlined /> 锚点用户画像
                  </div>
                  <ProfileCard profileJson={selectedTask.anchor_profile_json} />
                </div>
              )}

              {/* Match Results — Top 5 */}
              <div style={{ marginBottom: 16 }}>
                <div style={{ fontSize: 14, fontWeight: 600, color: '#475569', marginBottom: 12, display: 'flex', alignItems: 'center', gap: 8 }}>
                  <AimOutlined style={{ color: '#52b788' }} />
                  匹配结果（Top 5 相似度最高账号）
                  {selectedTask.match_mode === 'profile' && <span style={{ fontWeight: 400, fontSize: 12, color: '#94a3b8' }}> · 基于画像内容+昵称+发帖时间综合评分</span>}
                </div>
                {(!selectedTask.results || selectedTask.results.length === 0) ? (
                  <div style={{ background: '#fff', borderRadius: R.lg, padding: '40px 20px', textAlign: 'center', border: '1px solid #e2e8f0' }}>
                    <Empty description="未找到匹配账号，请尝试不同关键词" />
                  </div>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                    {selectedTask.results.map((result, gIdx) => {
                      const groupCandidates = getResultCandidates(result)
                      return groupCandidates.map((candidate) => (
                        <Card key={`${result.id}-${candidate.id}`} style={{
                          borderRadius: R.lg, border: '1px solid #e2e8f0',
                          boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
                        }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 16 }}>
                            <div style={{ flex: 1, minWidth: 0 }}>
                              <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 10 }}>
                                <span style={{ fontSize: 12, fontWeight: 700, color: '#94a3b8', fontFamily: "'Fira Code', monospace" }}>#{gIdx + 1}</span>
                                <Tag color={PLATFORM_COLORS[candidate.platform]} style={{ margin: 0, borderRadius: 6, fontSize: 11 }}>
                                  {PLATFORM_LABELS[candidate.platform] || candidate.platform}
                                </Tag>
                                <Avatar size={32} src={candidate.avatar_url} icon={<UserOutlined />} />
                                <div>
                                  <span style={{ fontWeight: 600, fontSize: 15, color: '#1e293b' }}>{candidate.nickname}</span>
                                  <span style={{ fontSize: 12, color: '#94a3b8', marginLeft: 8 }}>@{candidate.platform_uid}</span>
                                </div>
                                {candidate.profile_url && (
                                  <Tooltip title="查看主页">
                                    <Button type="link" size="small" icon={<LinkOutlined />}
                                      href={candidate.profile_url} target="_blank" rel="noopener noreferrer" />
                                  </Tooltip>
                                )}
                              </div>
                              {candidate.bio && (
                                <div style={{ fontSize: 12, color: '#64748b', marginBottom: 8, lineHeight: 1.5 }}>
                                  {candidate.bio}
                                </div>
                              )}
                              <ProfileCard profileJson={candidate.profile_json} />
                            </div>

                            <div style={{ textAlign: 'right', flexShrink: 0, minWidth: 120 }}>
                              <ConfidenceBadge score={candidate.match_score} />
                              {candidate.score_detail_json && (
                                <div style={{ marginTop: 8, fontSize: 11, color: '#94a3b8', display: 'flex', flexDirection: 'column', gap: 4, alignItems: 'flex-end' }}>
                                  {(() => {
                                    try {
                                      const sd = JSON.parse(candidate.score_detail_json)
                                      const labels: Record<string, string> = { name_similarity: '昵称', content_similarity: '内容', time_pattern_similarity: '时间' }
                                      return Object.entries(sd).map(([k, v]) => (
                                        <Tooltip key={k} title={`${labels[k]||k}: ${((v as number) * 100).toFixed(0)}%`}>
                                          <span style={{ display: 'inline-flex', gap: 6 }}>
                                            <span>{labels[k] || k}</span>
                                            <span style={{ fontWeight: 700, color: '#1e293b', fontFamily: "'Fira Code', monospace", minWidth: 36, textAlign: 'right' }}>
                                              {`${((v as number) * 100).toFixed(0)}%`}
                                            </span>
                                          </span>
                                        </Tooltip>
                                      ))
                                    } catch { return null }
                                  })()}
                                </div>
                              )}
                            </div>
                          </div>
                        </Card>
                      ))
                    })}
                  </div>
                )}
              </div>

              {/* All Candidates */}
              {selectedTask.candidates && selectedTask.candidates.length > 0 && (
                <>
                  <Divider style={{ margin: '24px 0 16px', fontSize: 13, color: '#94a3b8' }}>
                    <ClockCircleOutlined /> 全部候选账号 ({selectedTask.candidates.length})
                  </Divider>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))', gap: 10 }}>
                    {selectedTask.candidates.map(c => (
                      <CandidateCard key={c.id} candidate={c} />
                    ))}
                  </div>
                </>
              )}
            </div>
          )}
        </Col>
      </Row>
    </div>
  )
}
