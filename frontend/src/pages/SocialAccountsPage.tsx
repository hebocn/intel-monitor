import { useEffect, useState } from 'react'
import { Button, Modal, Drawer, Segmented, Form, Input, Select, InputNumber, Switch, Tag, message, Popconfirm, Typography, Tooltip, Skeleton, Upload, Alert, DatePicker, Table } from 'antd'
import {
  PlusOutlined, EditOutlined, DeleteOutlined, PlayCircleOutlined,
  ClockCircleOutlined, LinkOutlined, PauseCircleOutlined,
  CheckCircleOutlined, SettingOutlined, SyncOutlined, DownloadOutlined, LoadingOutlined,
  SearchOutlined, TagsOutlined,
  UploadOutlined, FileExcelOutlined,
  HolderOutlined, PushpinOutlined, DownOutlined, RightOutlined, CloseCircleOutlined, VerticalAlignTopOutlined,
} from '@ant-design/icons'
import { targetsAPI, scheduleAPI, resultsAPI, facebookAPI, platformPrefsAPI, accountPrefsAPI, tagsAPI } from '../services/api'
import { TagPill, type TagItem } from '../components/TagPill'
import { TagSelectPopover } from '../components/TagSelectPopover'
import { TagManageModal, type ManagedTag } from '../components/TagManageModal'
import { useNavigate } from 'react-router-dom'
import dayjs from 'dayjs'
import { formatBeijingTime, formatBeijingDate } from '../utils/time'

const { Text } = Typography

const platformOptions = [
  { value: 'x', label: 'X (Twitter)', color: '#1DA1F2' },
  { value: 'facebook', label: 'Facebook', color: '#1877F2' },
  { value: 'youtube', label: 'YouTube', color: '#FF0000' },
  { value: 'weibo', label: '微博', color: '#E6162D' },
  { value: 'xiaohongshu', label: '小红书', color: '#FE2C55' },
  { value: 'douyin', label: '抖音', color: '#000000' },
  { value: 'toutiao', label: '今日头条', color: '#E53333' },
  { value: '108community', label: '108社区', color: '#2563EB' },
]

const importanceOptions = [
  { value: 'high', label: '高', color: '#cf1322' },
  { value: 'medium', label: '中', color: '#d48806' },
  { value: 'low', label: '低', color: '#8c8c8c' },
]

const importanceMap = Object.fromEntries(importanceOptions.map(i => [i.value, i]))
const platformMap = Object.fromEntries(platformOptions.map(p => [p.value, p]))

// 立即执行：时间范围快捷预设（默认近24小时）
const runTimePresets = [
  { label: '近1小时', hours: 1 },
  { label: '近24小时', hours: 24 },
  { label: '近7天', hours: 24 * 7 },
  { label: '近30天', hours: 24 * 30 },
]

// 卡片上最多完整显示的标签数，超出折叠为 +N
const MAX_VISIBLE_TAGS = 3

function AccountCard({
  target,
  running,
  syncing,
  allTags,
  onRun,
  onSync,
  onEdit,
  onDelete,
  onDetail,
  onToggleActive,
  togglingActive,
  onSetTags,
  onCreateTag,
  onCardDragStart,
  onCardDragOver,
  onCardDrop,
  onCardDragEnd,
  onPin,
  pinDisabled,
  isDragOver,
  idx,
}: {
  target: any
  running: boolean
  syncing: boolean
  allTags: TagItem[]
  onRun: () => void
  onSync: () => void
  onEdit: () => void
  onDelete: () => void
  onDetail: () => void
  onToggleActive: (checked: boolean) => void
  togglingActive: boolean
  onSetTags: (tagIds: number[]) => void
  onCreateTag: (name: string, color: string) => Promise<TagItem | null>
  onCardDragStart: (e: any) => void
  onCardDragOver: (e: any) => void
  onCardDrop: (e: any) => void
  onCardDragEnd: () => void
  onPin: () => void
  pinDisabled: boolean
  isDragOver: boolean
  idx: number
}) {
  const [tagsExpanded, setTagsExpanded] = useState(false)
  const plat = platformMap[target.platform] || { label: target.platform, color: '#666' }
  const imp = target.importance ? importanceMap[target.importance] : null

  const targetTags: TagItem[] = target.tags || []
  const visibleTags = tagsExpanded ? targetTags : targetTags.slice(0, MAX_VISIBLE_TAGS)
  const hiddenCount = targetTags.length - (tagsExpanded ? 0 : Math.min(targetTags.length, MAX_VISIBLE_TAGS))
  const selectedTagIds = targetTags.map(t => t.id)

  const scheduleDisplay = target.cron_schedule
    ? target.cron_schedule.split(';').filter(Boolean)
    : null

  return (
    <div
      data-account-id={target.id}
      style={{
          background: 'transparent',
          borderRadius: 0,
          border: 'none',
          borderBottom: isDragOver ? `1px dashed ${plat.color}` : '1px solid var(--border)',
          overflow: 'visible',
          opacity: target.is_active ? 1 : 0.6,
          transition: 'background-color 0.2s ease, border-color 0.2s ease, color 0.2s ease',
          position: 'relative',
        }}
      onDragOver={onCardDragOver}
      onDrop={onCardDrop}
    >

      {/* Header */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '14px 0 10px 0',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          {/* 拖拽手柄(分区内排序) */}
          <span
            draggable
            onDragStart={onCardDragStart}
            onDragEnd={onCardDragEnd}
            onClick={e => e.stopPropagation()}
            title="拖拽排序"
            style={{ cursor: 'grab', color: 'var(--text-muted)', display: 'inline-flex', alignItems: 'center' }}
          >
            <HolderOutlined />
          </span>

          {/* Platform badge */}
          <div style={{
            display: 'inline-flex', alignItems: 'center', gap: 6,
            padding: '5px 14px 5px 10px',
            borderRadius: 20,
            background: `${plat.color}12`,
            border: `1px solid ${plat.color}20`,
          }}>
            <div style={{
              width: 8, height: 8, borderRadius: '50%',
              background: plat.color,
            }} />
            <Text style={{ color: plat.color, fontSize: 12, fontWeight: 700, fontFamily: 'var(--font-body)' }}>
              {plat.label}
            </Text>
          </div>

          {/* Importance badge */}
          {imp && (
            <div style={{
              display: 'inline-flex', alignItems: 'center', gap: 4,
              padding: '3px 10px', borderRadius: 12,
              background: `${imp.color}10`,
              border: `1px solid ${imp.color}18`,
              fontSize: 11, fontWeight: 700, color: imp.color,
              fontFamily: 'var(--font-body)',
            }}>
              {imp.label}
            </div>
          )}

          {/* Account name */}
          <Text style={{ color: 'var(--text-primary)', fontWeight: 700, fontSize: 16 }}>
            {target.account_name}
          </Text>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          {/* 一键启停 */}
          <div style={{
            display: 'inline-flex', alignItems: 'center', gap: 6,
            padding: '3px 12px', borderRadius: 12,
            background: target.is_active ? 'rgba(34,197,94,0.08)' : 'rgba(140,140,140,0.08)',
            color: target.is_active ? '#22C55E' : '#8c8c8c',
            fontSize: 12, fontWeight: 600,
          }}>
            <Switch size="small" checked={target.is_active} loading={togglingActive} onChange={onToggleActive} />
            <span style={{ minWidth: 26, textAlign: 'center' }}>
              {target.is_active ? <CheckCircleOutlined /> : <PauseCircleOutlined />} {target.is_active ? '启用' : '停用'}
            </span>
          </div>

          {/* Actions */}
          <Tooltip title="置顶该账号（分区内）">
            <Button
              type="text"
              size="small"
              icon={<PushpinOutlined />}
              disabled={pinDisabled}
              onClick={onPin}
              style={{ color: '#0f766e' }}
            />
          </Tooltip>
          <Tooltip title="立即执行">
            <Button
              type="text"
              size="small"
              icon={<PlayCircleOutlined />}
              onClick={onRun}
              loading={running}
              style={{ color: '#0f766e' }}
            />
          </Tooltip>
          {(target.platform === 'x' || target.platform === 'weibo' || target.platform === 'facebook') && (
            <Tooltip title="同步（拉取正文存档，可选条数）">
              <Button
                type="text"
                size="small"
                icon={<SyncOutlined />}
                onClick={onSync}
                loading={syncing}
                style={{ color: '#3370ff' }}
              />
            </Tooltip>
          )}
          <Tooltip title="编辑">
            <Button type="text" size="small" icon={<EditOutlined />} onClick={onEdit} />
          </Tooltip>
          <Tooltip title="查看详情">
            <Button type="text" size="small" icon={<SettingOutlined />} onClick={onDetail} />
          </Tooltip>
          <Popconfirm title="确定删除此账号？" onConfirm={onDelete} okButtonProps={{ danger: true }}>
            <Tooltip title="删除">
              <Button type="text" size="small" icon={<DeleteOutlined />} style={{ color: '#c75050' }} />
            </Tooltip>
          </Popconfirm>
        </div>
      </div>

      {/* Tags row：标签药丸（最多3个，超出 +N 展开）+ 打标签入口 */}
      <div style={{ padding: '0 22px 12px 22px' }}>
        <div style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 6 }}>
          {visibleTags.map(tag => (
            <TagPill key={tag.id} tag={tag} />
          ))}
          {hiddenCount > 0 && (
            <span
              onClick={() => setTagsExpanded(true)}
              title={`还有 ${hiddenCount} 个标签`}
              style={{
                display: 'inline-flex', alignItems: 'center',
                padding: '3px 10px', borderRadius: 12,
                background: 'rgba(248,250,252,0.06)', border: '1px solid var(--border)',
                color: 'var(--text-muted)', fontSize: 11, fontWeight: 700,
                cursor: 'pointer', lineHeight: '16px', whiteSpace: 'nowrap',
                fontFamily: 'var(--font-body)',
              }}
            >
              +{hiddenCount}
            </span>
          )}
          {tagsExpanded && targetTags.length > MAX_VISIBLE_TAGS && (
            <span
              onClick={() => setTagsExpanded(false)}
              style={{
                fontSize: 11, color: 'var(--text-muted)', cursor: 'pointer',
                textDecoration: 'underline', textUnderlineOffset: 3,
                opacity: 0.7, padding: '0 2px',
              }}
            >
              收起
            </span>
          )}
          <TagSelectPopover
            tags={allTags}
            selectedIds={selectedTagIds}
            onChange={onSetTags}
            onCreateTag={onCreateTag}
          >
            <span
              title="打标签"
              style={{
                display: 'inline-flex', alignItems: 'center', gap: 4,
                padding: '3px 10px', borderRadius: 12,
                border: '1px dashed var(--border-strong)',
                color: 'var(--text-muted)', fontSize: 11, fontWeight: 600,
                cursor: 'pointer', lineHeight: '16px', whiteSpace: 'nowrap',
                fontFamily: 'var(--font-body)', transition: 'background-color 0.2s ease, border-color 0.2s ease, color 0.2s ease',
              }}
              onMouseEnter={e => {
                e.currentTarget.style.borderColor = 'var(--accent)'
                e.currentTarget.style.color = 'var(--accent)'
              }}
              onMouseLeave={e => {
                e.currentTarget.style.borderColor = 'var(--border-strong)'
                e.currentTarget.style.color = 'var(--text-muted)'
              }}
            >
              <PlusOutlined style={{ fontSize: 10 }} />
              {targetTags.length === 0 ? '标签' : ''}
            </span>
          </TagSelectPopover>
        </div>
      </div>

      {/* Details */}
        <div style={{ padding: '0 0 18px 0' }}>
        <div style={{
          display: 'flex', alignItems: 'center', gap: 20,
          flexWrap: 'wrap',
        }}>
          {/* URL */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <LinkOutlined style={{ color: 'var(--text-muted)', fontSize: 12 }} />
            <a
              href={target.account_url}
              target="_blank"
              rel="noopener noreferrer"
              style={{
                color: 'var(--text-secondary)', fontSize: 13,
                textDecoration: 'none', maxWidth: 320,
                overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                fontFamily: 'var(--font-mono)',
              }}
            >
              {target.account_url}
            </a>
          </div>

          {/* Schedule */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <ClockCircleOutlined style={{ color: 'var(--text-muted)', fontSize: 12 }} />
            {scheduleDisplay ? (
              <div style={{ display: 'flex', gap: 4 }}>
                {scheduleDisplay.map((e: string, i: number) => (
                  <Tag key={i} style={{
                    fontFamily: 'var(--font-mono)', fontSize: 11, margin: 0,
                    background: 'var(--surface-1)', border: '1px solid var(--border)',
                    borderRadius: 8, padding: '1px 8px',
                  }}>
                    {e}
                  </Tag>
                ))}
              </div>
            ) : (
              <Text style={{
                color: 'var(--accent)', fontFamily: 'var(--font-mono)', fontSize: 13, fontWeight: 600,
              }}>
                {String(target.monitor_hour).padStart(2, '0')}:{String(target.monitor_minute).padStart(2, '0')}
              </Text>
            )}
          </div>

          {/* Running indicator */}
          {running && (
            <div style={{
              display: 'inline-flex', alignItems: 'center', gap: 6,
              padding: '3px 12px', borderRadius: 12,
              background: 'rgba(15,118,110,0.08)',
              color: '#0f766e', fontSize: 12, fontWeight: 600,
            }}>
              <ClockCircleOutlined spin />
              执行中...
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default function SocialAccountsPage() {
  const [targets, setTargets] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [modalOpen, setModalOpen] = useState(false)
  const [editingTarget, setEditingTarget] = useState<any>(null)
  const [runningId, setRunningId] = useState<number | null>(null)
  // 立即执行：时间范围筛选（默认近24小时）
  const [runModalOpen, setRunModalOpen] = useState(false)
  const [runTarget, setRunTarget] = useState<any>(null)
  const [runRange, setRunRange] = useState<[dayjs.Dayjs, dayjs.Dayjs] | null>(null)
  const [runPreset, setRunPreset] = useState('近24小时')
  const [syncingId, setSyncingId] = useState<number | null>(null)
  const [syncModalOpen, setSyncModalOpen] = useState(false)
  const [syncTarget, setSyncTarget] = useState<any>(null)
  const [syncLimit, setSyncLimit] = useState<number>(200)
  const [syncDrawerOpen, setSyncDrawerOpen] = useState(false)
  const [syncPosts, setSyncPosts] = useState<any[] | null>(null)
  const [syncSyncedAt, setSyncSyncedAt] = useState<string | null>(null)
  const [syncElapsed, setSyncElapsed] = useState(0)
  const [searchQuery, setSearchQuery] = useState('')
  const [batchOpen, setBatchOpen] = useState(false)
  const [batchActive, setBatchActive] = useState<'keep' | 'on' | 'off'>('keep')
  const [batchPush, setBatchPush] = useState<'keep' | 'on' | 'off'>('keep')
  const [batchSaving, setBatchSaving] = useState(false)
  const [importOpen, setImportOpen] = useState(false)
  const [importing, setImporting] = useState(false)
  const [importResult, setImportResult] = useState<any>(null)
  const [form] = Form.useForm()
  const navigate = useNavigate()
  const [scheduleMode, setScheduleMode] = useState<'simple' | 'cron'>('simple')
  const [cronExpressions, setCronExpressions] = useState<string[]>([''])
  // Facebook 昵称反查候选
  const [fbSearching, setFbSearching] = useState(false)
  const [fbCandidates, setFbCandidates] = useState<{ nickname: string; url: string; snippet?: string }[]>([])
  const [fbSearchOpen, setFbSearchOpen] = useState(false)
  const fbPlatform = Form.useWatch('platform', form) === 'facebook'
  // 平台分区：自定义排序 / 折叠 / 拖拽
  const [platformOrder, setPlatformOrder] = useState<string[] | null>(null)
  const [collapsedSections, setCollapsedSections] = useState<Record<string, boolean>>(() => {
    try { return JSON.parse(localStorage.getItem('soc_section_collapsed') || '{}') } catch { return {} }
  })
  const [dragPlatform, setDragPlatform] = useState<string | null>(null)
  const [dragOverPlatform, setDragOverPlatform] = useState<string | null>(null)
  const [orderSaving, setOrderSaving] = useState(false)
  // 单卡启停切换中
  const [togglingIds, setTogglingIds] = useState<number[]>([])
  // 整平台批量立即执行
  const [batchRunPlatform, setBatchRunPlatform] = useState<string | null>(null)
  const [batchRunStatuses, setBatchRunStatuses] = useState<Record<number, 'pending' | 'running' | 'success' | 'failed' | 'skipped'>>({})
  const [batchRunErrors, setBatchRunErrors] = useState<Record<number, string>>({})
  const [batchRunDrawerOpen, setBatchRunDrawerOpen] = useState(false)
  const [batchRunRange, setBatchRunRange] = useState<[dayjs.Dayjs, dayjs.Dayjs] | null>(null)
  // 平台分区内账号排序(platform -> 已排序的 target id 列表)
  const [accountOrders, setAccountOrders] = useState<Record<string, number[]>>({})
  const [accountDragId, setAccountDragId] = useState<number | null>(null)
  const [accountDragOverId, setAccountDragOverId] = useState<number | null>(null)
  // 标签
  const [tags, setTags] = useState<ManagedTag[]>([])
  const [tagManageOpen, setTagManageOpen] = useState(false)
  const [filterTagIds, setFilterTagIds] = useState<number[]>([])
  const [filterPlatform, setFilterPlatform] = useState<string | undefined>(undefined)
  const [batchTagIds, setBatchTagIds] = useState<number[]>([])
  const [batchTagMode, setBatchTagMode] = useState<'add' | 'remove'>('add')

  const handleFbSearch = async () => {
    const nickname = form.getFieldValue('account_name')
    if (!nickname || !nickname.trim()) {
      message.warning('请先填写账号名称（昵称）再搜索')
      return
    }
    setFbSearching(true)
    try {
      const res = await facebookAPI.searchAccounts(nickname.trim())
      const candidates = res.data?.candidates || []
      if (candidates.length === 0) {
        message.warning('未找到匹配的 Facebook 主页，请检查昵称或改用 URL 直接添加')
        return
      }
      setFbCandidates(candidates)
      setFbSearchOpen(true)
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '搜索失败')
    } finally {
      setFbSearching(false)
    }
  }

  const handleFbPick = (c: { nickname: string; url: string }) => {
    form.setFieldsValue({ account_name: c.nickname, account_url: c.url })
    setFbSearchOpen(false)
    message.success('已填充账号信息，可继续设置调度')
  }

  const fetchTargets = async (silent = false) => {
    if (!silent) setLoading(true)
    try {
      const res = await targetsAPI.list()
      setTargets(res.data)
    } finally {
      if (!silent) setLoading(false)
    }
  }

  const fetchTags = async () => {
    try {
      const res = await tagsAPI.list()
      setTags(res.data)
    } catch { /* 静默失败，不打断页面 */ }
  }

  useEffect(() => { fetchTargets(); fetchTags() }, [])

  // 加载平台分区自定义排序（无则默认：账号数量降序）
  useEffect(() => {
    platformPrefsAPI.list().then(res => {
      if (Array.isArray(res.data) && res.data.length > 0) {
        setPlatformOrder(res.data.map((i: any) => i.platform))
      }
    }).catch(() => {})
  }, [])

  // 加载平台分区内账号排序
  useEffect(() => {
    accountPrefsAPI.list().then(res => {
      if (Array.isArray(res.data) && res.data.length > 0) {
        const map: Record<string, number[]> = {}
        for (const item of res.data) {
          if (!map[item.platform]) map[item.platform] = []
          map[item.platform].push(item.target_id)
        }
        setAccountOrders(map)
      }
    }).catch(() => {})
  }, [])

  useEffect(() => {
    if (syncingId == null) return
    const timer = setInterval(() => setSyncElapsed(prev => prev + 1), 1000)
    return () => clearInterval(timer)
  }, [syncingId])

  const handleDownloadTemplate = async () => {
    try {
      const res = await targetsAPI.importTemplate()
      const blob = new Blob([res.data], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'target_import_template.xlsx'
      a.click()
      URL.revokeObjectURL(url)
    } catch {
      message.error('模板下载失败')
    }
  }

  const handleImportFile = async (file: File) => {
    setImporting(true)
    setImportResult(null)
    try {
      const formData = new FormData()
      formData.append('file', file)
      const res = await targetsAPI.importBatch(formData)
      setImportResult(res.data)
      message.success(`导入完成：成功 ${res.data.created} 条`)
      fetchTargets()
    } catch (err: any) {
      message.error(err.response?.data?.detail || '导入失败')
      setImportResult(null)
    } finally {
      setImporting(false)
    }
    return false
  }

  const handleSubmit = async () => {
    let values: any
    try {
      values = await form.validateFields()
    } catch {
      return
    }

    if (scheduleMode === 'cron') {
      const valid = cronExpressions.filter(e => e.trim())
      if (valid.length === 0) {
        message.warning('请至少添加一个 Cron 表达式')
        return
      }
      values.cron_schedule = valid.join(';')
      values.monitor_hour = 9
      values.monitor_minute = 0
    } else {
      values.cron_schedule = null
    }

    if (!values.importance) delete values.importance
    if (!values.avatar_url) delete values.avatar_url
    const tagIds: number[] = values.tag_ids || []
    delete values.tag_ids

    try {
      if (editingTarget) {
        await targetsAPI.update(editingTarget.id, values)
        await targetsAPI.setTags(editingTarget.id, tagIds)
        message.success('更新成功')
      } else {
        const res = await targetsAPI.create(values)
        if (tagIds.length > 0 && res.data?.id) await targetsAPI.setTags(res.data.id, tagIds)
        message.success('添加成功')
      }
      setModalOpen(false)
      form.resetFields()
      setEditingTarget(null)
      setCronExpressions([''])
      setScheduleMode('simple')
      fetchTargets()
    } catch (err: any) {
      const detail = err.response?.data?.detail
      if (Array.isArray(detail)) {
        message.error(detail.map((d: any) => d.msg).join('; '))
      } else {
        message.error(detail || '操作失败')
      }
    }
  }

  const openSyncModal = (target: any) => {
    setSyncTarget(target)
    setSyncLimit(200)
    setSyncModalOpen(true)
  }

  const handleSync = async () => {
    if (!syncTarget) return
    const limit = syncLimit
    setSyncingId(syncTarget.id)
    setSyncElapsed(0)
    try {
      const res = await scheduleAPI.sync(syncTarget.id, limit)
      const { result_id, status, error_message } = res.data
      if (status === 'failed') {
        message.error(error_message || '同步失败')
        setSyncModalOpen(false)
        setSyncingId(null)
        return
      }
      const detailRes = await resultsAPI.detail(result_id)
      const result = detailRes.data
      let posts: any[] = []
      if (result.raw_content) {
        try { posts = JSON.parse(result.raw_content) } catch {}
      }
      setSyncPosts(posts)
      setSyncSyncedAt(result.created_at || null)
      setSyncModalOpen(false)
      setSyncDrawerOpen(true)
      message.success(`同步完成：${posts.length} 条`)
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '同步失败')
      setSyncModalOpen(false)
    } finally {
      setSyncingId(null)
    }
  }

  const buildMarkdown = (posts: any[], target: any) => {
    const plat = platformMap[target.platform]?.label || target.platform
    const now = new Date().toLocaleString('zh-CN', { hour12: false })
    const lines: string[] = [
      `# 账号同步存档：${plat} @${target.account_name}`,
      '',
      `- 平台：${plat}`,
      `- 账号：${target.account_name}`,
      `- 账号链接：${target.account_url}`,
      `- 同步时间：${now}`,
      `- 条数：${posts.length}`,
      '',
      '---',
      '',
    ]
    posts.forEach((p: any, i: number) => {
      const timeTitle = fmtPostTime(p.published_at)
      lines.push(`## ${i + 1}. ${timeTitle || p.title || '(无时间)'}`, '')
      const meta: string[] = []
      if (p.author_name) meta.push(`作者：${p.author_name}`)
      if (p.published_at) meta.push(`时间：${fmtPostTime(p.published_at)}`)
      if (p.likes) meta.push(`点赞：${p.likes}`)
      if (p.comments_count) meta.push(`评论：${p.comments_count}`)
      if (p.shares) meta.push(`转发：${p.shares}`)
      if (p.views) meta.push(`浏览：${p.views}`)
      if (meta.length) lines.push(`> ${meta.join(' | ')}`, '')
      lines.push(p.content || '', '')
      if (p.url) lines.push(`> 链接：${p.url}`, '')
      if (Array.isArray(p.images) && p.images.length) {
        p.images.forEach((img: string) => lines.push(`![图片](${img})`))
        lines.push('')
      }
      lines.push('---', '')
    })
    return lines.join('\n')
  }

  const handleExportMd = () => {
    if (!syncPosts?.length || !syncTarget) return
    const md = buildMarkdown(syncPosts, syncTarget)
    const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `sync-${syncTarget.account_name || 'account'}-${new Date().toISOString().slice(0, 10)}.md`
    a.click()
    URL.revokeObjectURL(url)
    message.success('已导出 Markdown')
  }

  const buildNDJSON = (posts: any[]) => posts.map(p => JSON.stringify(p)).join('\n')

  const handleExportNdjson = () => {
    if (!syncPosts?.length || !syncTarget) return
    const blob = new Blob([buildNDJSON(syncPosts)], { type: 'application/x-ndjson;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `sync-${syncTarget.account_name || 'account'}-${new Date().toISOString().slice(0, 10)}.ndjson`
    a.click()
    URL.revokeObjectURL(url)
    message.success('已导出 NDJSON')
  }

  // 帖子 ID：X 取 /status/<id>，微博取 URL 末段
  const extractPostId = (p: any) => {
    const u = p.url || ''
    const m = u.match(/\/status\/([^/?#]+)/)
    if (m) return m[1]
    const seg = u.split('/').filter(Boolean).pop()
    return seg || ''
  }

  // published_at 为后端存储的 naive UTC，统一按北京时间展示
  const fmtPostTime = (iso?: string) => formatBeijingTime(iso)

  const syncRange = (() => {
    if (!syncPosts?.length) return { earliest: '-', latest: '-' }
    const times = syncPosts.map(p => p.published_at).filter(Boolean).sort()
    const fmt = (t: string) => (t ? formatBeijingDate(t) : '-')
    return {
      earliest: times.length ? fmt(times[0]) : '-',
      latest: times.length ? fmt(times[times.length - 1]) : '-',
    }
  })()

  const handleDelete = async (id: number) => {
    await targetsAPI.delete(id)
    message.success('删除成功')
    fetchTargets()
  }

  // 点击「立即执行」：先弹出时间范围选择，确认后按窗口执行
  const openRunModal = (target: any) => {
    setRunTarget(target)
    setBatchRunPlatform(null)
    setRunPreset('近24小时')
    setRunRange([dayjs().subtract(24, 'hour'), dayjs()])
    setRunModalOpen(true)
  }

  // 整平台「全部立即执行」：同一时间范围弹窗，逐个账号执行
  const openBatchRunModal = (platform: string) => {
    setBatchRunPlatform(platform)
    setRunTarget(null)
    setRunPreset('近24小时')
    setRunRange([dayjs().subtract(24, 'hour'), dayjs()])
    setRunModalOpen(true)
  }

  const confirmRun = async () => {
    if (!runTarget && !batchRunPlatform) return
    if (!runRange || !runRange[0] || !runRange[1]) {
      message.warning('请选择时间范围')
      return
    }
    const [start, end] = runRange
    if (end.isBefore(start)) {
      message.warning('结束时间不能早于开始时间')
      return
    }

    // 批量模式：对平台内启用账号逐个执行（限并发3）
    if (batchRunPlatform) {
      const accounts = (grouped[batchRunPlatform] || []).filter((t: any) => t.is_active)
      if (accounts.length === 0) {
        message.warning('该平台没有启用中的账号')
        return
      }
      setRunModalOpen(false)
      setBatchRunRange([start, end])
      startBatchRun(accounts, start, end)
      return
    }

    const id = runTarget.id
    setRunModalOpen(false)
    setRunningId(id)
    message.info('开始监测（时间范围：' + start.format('MM-DD HH:mm') + ' ~ ' + end.format('MM-DD HH:mm') + '）...')
    try {
      const res = await scheduleAPI.runNow(id, 'social_media', start.toISOString(), end.toISOString())
      const { result_id } = res.data

      const pollResult = async () => {
        for (let i = 0; i < 60; i++) {
          await new Promise(r => setTimeout(r, 2000))
          try {
            const detailRes = await resultsAPI.detail(result_id)
            const result = detailRes.data
            if (result.status === 'success') {
              message.success('监测完成')
              fetchTargets()
              setRunningId(null)
              return
            } else if (result.status === 'failed') {
              message.warning(result.error_message || '监测失败')
              fetchTargets()
              setRunningId(null)
              return
            }
          } catch {}
        }
        fetchTargets()
        setRunningId(null)
      }
      pollResult()
    } catch (err: any) {
      message.error(err.response?.data?.detail || '监测启动失败')
      setRunningId(null)
    }
  }

  // 批量执行：并发3个worker，逐个触发+轮询结果
  const startBatchRun = async (accounts: any[], start: dayjs.Dayjs, end: dayjs.Dayjs, merge = false) => {
    const statuses: Record<number, 'pending' | 'running' | 'success' | 'failed' | 'skipped'> = {}
    accounts.forEach((t: any) => { statuses[t.id] = t.is_active ? 'pending' : 'skipped' })
    setBatchRunStatuses(prev => (merge ? { ...prev, ...statuses } : statuses))
    setBatchRunErrors({})
    setBatchRunDrawerOpen(true)
    const activeCount = accounts.filter((t: any) => t.is_active).length
    message.info('开始批量执行 ' + activeCount + ' 个账号（限并发3）...')

    const queue = accounts.filter((t: any) => t.is_active)
    const worker = async () => {
      while (true) {
        const t = queue.shift()
        if (!t) return
        setBatchRunStatuses(prev => ({ ...prev, [t.id]: 'running' }))
        try {
          const res = await scheduleAPI.runNow(t.id, 'social_media', start.toISOString(), end.toISOString())
          const { result_id } = res.data
          let settled = false
          for (let i = 0; i < 60; i++) {
            await new Promise(r => setTimeout(r, 2000))
            try {
              const detailRes = await resultsAPI.detail(result_id)
              const status = detailRes.data?.status
              if (status === 'success') {
                setBatchRunStatuses(prev => ({ ...prev, [t.id]: 'success' }))
                settled = true
                break
              }
              if (status === 'failed') {
                setBatchRunStatuses(prev => ({ ...prev, [t.id]: 'failed' }))
                setBatchRunErrors(prev => ({ ...prev, [t.id]: detailRes.data?.error_message || '监测失败' }))
                settled = true
                break
              }
            } catch {}
          }
          if (!settled) {
            setBatchRunStatuses(prev => ({ ...prev, [t.id]: 'failed' }))
            setBatchRunErrors(prev => ({ ...prev, [t.id]: '轮询超时，结果未在2分钟内写入' }))
          }
        } catch (e: any) {
          setBatchRunStatuses(prev => ({ ...prev, [t.id]: 'failed' }))
          setBatchRunErrors(prev => ({ ...prev, [t.id]: e?.response?.data?.detail || '监测启动失败' }))
        }
      }
    }
    await Promise.all(Array.from({ length: 3 }, () => worker()))
    fetchTargets()
    message.success('批量执行完成')
  }

  const retryBatchFailed = () => {
    if (!batchRunRange) return
    const failedIds = Object.entries(batchRunStatuses)
      .filter(([, s]) => s === 'failed')
      .map(([id]) => Number(id))
    if (failedIds.length === 0) {
      message.info('没有失败的账号')
      return
    }
    const accounts = filtered.filter((t: any) => failedIds.includes(t.id))
    startBatchRun(accounts, batchRunRange[0], batchRunRange[1], true)
  }

  const openEditModal = (target: any) => {
    setEditingTarget(target)
    form.setFieldsValue({ ...target, tag_ids: (target.tags || []).map((t: any) => t.id) })
    if (target.cron_schedule) {
      setScheduleMode('cron')
      setCronExpressions(target.cron_schedule.split(';').filter(Boolean))
    } else {
      setScheduleMode('simple')
      setCronExpressions([''])
    }
    setModalOpen(true)
  }

  // 前端本地过滤：按账号名搜索 + 按标签筛选（选中的标签须全部命中）
  const q = searchQuery.trim().toLowerCase()
  const filtered = targets.filter((t: any) => {
    if (filterPlatform && t.platform !== filterPlatform) return false
    if (q && !(t.account_name || '').toLowerCase().includes(q)) return false
    if (filterTagIds.length > 0) {
      const ids = (t.tags || []).map((tg: any) => tg.id)
      if (!filterTagIds.every(id => ids.includes(id))) return false
    }
    return true
  })

  // ── 平台分区 ─────────────────────────────────────────────
  const grouped = (() => {
    const map: Record<string, any[]> = {}
    for (const t of filtered) {
      const key = t.platform || 'other'
      if (!map[key]) map[key] = []
      map[key].push(t)
    }
    return map
  })()

  const sectionPlatforms = (() => {
    const known = Object.keys(grouped).filter(key => platformMap[key])
    const others = Object.keys(grouped).filter(key => !platformMap[key])
    if (platformOrder) {
      const ordered = platformOrder.filter(key => known.includes(key))
      const rest = known.filter(key => !platformOrder.includes(key))
      rest.sort((a, b) => grouped[b].length - grouped[a].length)
      return [...ordered, ...rest, ...others]
    }
    known.sort((a, b) => grouped[b].length - grouped[a].length)
    return [...known, ...others]
  })()

  const activeCountOf = (key: string) => (grouped[key] || []).filter((t: any) => t.is_active).length

  // 应用已保存的账号排序:已排序的在前,其余按原顺序(created_at desc)接续
  const orderedAccountsFor = (platform: string, accounts: any[]) => {
    const saved = accountOrders[platform] || []
    if (!saved.length) return accounts
    const byId = new Map<number, any>(accounts.map((a: any) => [a.id, a]))
    const ordered = saved.map(id => byId.get(id)).filter((a): a is any => !!a)
    const rest = accounts.filter((a: any) => !saved.includes(a.id))
    return [...ordered, ...rest]
  }

  // 该平台的全部账号(不受搜索过滤影响,用于拖拽/置顶时计算完整顺序)
  const fullAccountsOf = (platform: string) => targets.filter((t: any) => t.platform === platform)

  const toggleCollapse = (key: string) => {
    setCollapsedSections(prev => {
      const next = { ...prev, [key]: !prev[key] }
      try { localStorage.setItem('soc_section_collapsed', JSON.stringify(next)) } catch {}
      return next
    })
  }

  const persistOrder = async (order: string[]) => {
    setPlatformOrder(order)
    setOrderSaving(true)
    try {
      await platformPrefsAPI.save(order.map((key, i) => ({ platform: key, sort_order: i })))
    } catch {
      message.error('排序保存失败')
    } finally {
      setOrderSaving(false)
    }
  }

  const pinPlatform = (key: string) => {
    const idx = sectionPlatforms.indexOf(key)
    if (idx <= 0) return
    const rest = sectionPlatforms.filter(k => k !== key)
    persistOrder([key, ...rest])
  }

  const handleDragStart = (e: any, key: string) => {
    setDragPlatform(key)
    e.dataTransfer.effectAllowed = 'move'
    try { e.dataTransfer.setData('text/plain', key) } catch {}
  }

  const handleDropOnSection = (e: any, targetKey: string) => {
    e.preventDefault()
    const from = dragPlatform
    setDragPlatform(null)
    setDragOverPlatform(null)
    if (!from || from === targetKey) return
    const next = [...sectionPlatforms]
    const fromIdx = next.indexOf(from)
    const toIdx = next.indexOf(targetKey)
    if (fromIdx < 0 || toIdx < 0) return
    next.splice(fromIdx, 1)
    next.splice(toIdx, 0, from)
    persistOrder(next)
  }

  const resetOrder = async () => {
    setPlatformOrder(null)
    try {
      await platformPrefsAPI.reset()
      message.success('已恢复默认排序')
    } catch {
      message.error('恢复默认排序失败')
    }
  }

  // ── 一键启停 ─────────────────────────────────────────────
  const handleToggleActive = async (target: any, checked: boolean) => {
    setTogglingIds(prev => [...prev, target.id])
    try {
      await targetsAPI.update(target.id, { is_active: checked })
      setTargets(prev => prev.map(t => (t.id === target.id ? { ...t, is_active: checked } : t)))
      message.success(target.account_name + (checked ? ' 已启用' : ' 已停用'))
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '切换失败，已还原')
    } finally {
      setTogglingIds(prev => prev.filter(id => id !== target.id))
    }
  }

  // ── 标签 ────────────────────────────────────────────────
  // 卡片打标签：乐观更新，失败回滚
  const handleSetTargetTags = async (target: any, tagIds: number[]) => {
    const prevTags = target.tags
    const nextTags = tags.filter(t => tagIds.includes(t.id))
    setTargets(prev => prev.map(t => (t.id === target.id ? { ...t, tags: nextTags } : t)))
    try {
      await targetsAPI.setTags(target.id, tagIds)
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '标签设置失败')
      setTargets(prev => prev.map(t => (t.id === target.id ? { ...t, tags: prevTags } : t)))
    }
  }

  // 就地新建标签（选择器内），成功后加入标签库
  const handleCreateTag = async (name: string, color: string): Promise<TagItem | null> => {
    try {
      const res = await tagsAPI.create({ name, color })
      const tag = res.data
      setTags(prev => [...prev, tag])
      return tag
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '标签创建失败')
      return null
    }
  }

  // 标签库变更（改名/换色/删除）后：静默刷新标签与账号（卡片上药丸同步）
  const handleTagsChanged = () => {
    fetchTags()
    fetchTargets(true)
  }

  // ── 分区内账号排序(拖拽/置顶) ──────────────────────────────
  const persistAccountOrder = async (platform: string, ids: number[]) => {
    setAccountOrders(prev => ({ ...prev, [platform]: ids }))
    try {
      await accountPrefsAPI.save(platform, ids.map((id, i) => ({ target_id: id, sort_order: i })))
    } catch {
      message.error('账号排序保存失败')
    }
  }

  const handleAccountDragStart = (e: any, target: any) => {
    setAccountDragId(target.id)
    e.dataTransfer.effectAllowed = 'move'
    try { e.dataTransfer.setData('text/plain', String(target.id)) } catch {}
  }

  const handleAccountDragOver = (e: any, target: any) => {
    if (accountDragId && accountDragId !== target.id) {
      e.preventDefault()
      setAccountDragOverId(target.id)
    }
  }

  const handleAccountDrop = (e: any, target: any) => {
    e.preventDefault()
    const from = accountDragId
    const to = target.id
    setAccountDragId(null)
    setAccountDragOverId(null)
    if (!from || from === to) return
    const platform = target.platform
    const full = orderedAccountsFor(platform, fullAccountsOf(platform))
    const fromIdx = full.findIndex((a: any) => a.id === from)
    const toIdx = full.findIndex((a: any) => a.id === to)
    if (fromIdx < 0 || toIdx < 0) return
    const [moved] = full.splice(fromIdx, 1)
    full.splice(toIdx, 0, moved)
    persistAccountOrder(platform, full.map((a: any) => a.id))
  }

  const handleAccountDragEnd = () => {
    setAccountDragId(null)
    setAccountDragOverId(null)
  }

  const pinAccount = (target: any) => {
    const platform = target.platform
    const full = orderedAccountsFor(platform, fullAccountsOf(platform))
    const idx = full.findIndex((a: any) => a.id === target.id)
    if (idx <= 0) return
    const [moved] = full.splice(idx, 1)
    full.unshift(moved)
    persistAccountOrder(platform, full.map((a: any) => a.id))
  }

  const handleBatchUpdate = async () => {
    if (filtered.length === 0) return
    const payload: any = { target_ids: filtered.map((t: any) => t.id) }
    if (batchActive !== 'keep') payload.is_active = batchActive === 'on'
    if (batchPush !== 'keep') payload.push_enabled = batchPush === 'on'
    const hasSwitch = payload.is_active !== undefined || payload.push_enabled !== undefined
    const hasTags = batchTagIds.length > 0
    if (!hasSwitch && !hasTags) {
      message.warning('请至少选择一项要修改的开关或标签')
      return
    }
    setBatchSaving(true)
    try {
      let updated = 0
      if (hasSwitch) {
        const res = await targetsAPI.batchUpdate(payload)
        updated = res.data.updated
      }
      if (hasTags) {
        await targetsAPI.batchTags({
          target_ids: payload.target_ids,
          ...(batchTagMode === 'add' ? { add_tag_ids: batchTagIds } : { remove_tag_ids: batchTagIds }),
        })
        updated = payload.target_ids.length
      }
      message.success(`已批量更新 ${updated} 个账号`)
      setBatchOpen(false)
      setBatchActive('keep')
      setBatchPush('keep')
      setBatchTagIds([])
      setBatchTagMode('add')
      fetchTargets(true)
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '批量更新失败')
    } finally {
      setBatchSaving(false)
    }
  }

  const tableData = sectionPlatforms.flatMap((platform: string) => {
    const accounts = grouped[platform] || []
    return orderedAccountsFor(platform, accounts).map((target: any, idx: number) => ({
      ...target,
      _platform: platform,
      _index: idx,
    }))
  })

  const columns: any[] = [
    {
      title: '',
      key: 'drag',
      width: 44,
      render: (_: any, record: any) => (
        <span
          draggable
          title="拖拽排序（同平台内）"
          onDragStart={(e: any) => handleAccountDragStart(e, record)}
          onDragOver={(e: any) => handleAccountDragOver(e, record)}
          onDrop={(e: any) => handleAccountDrop(e, record)}
          onDragEnd={handleAccountDragEnd}
          style={{ cursor: 'grab', color: 'var(--text-muted)', display: 'inline-flex', alignItems: 'center' }}
        >
          <HolderOutlined />
        </span>
      ),
    },
    {
      title: '平台',
      key: 'platform',
      width: 150,
      render: (_: any, record: any) => {
        const plat = platformMap[record.platform] || { label: record.platform, color: '#666' }
        return (
          <div style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
            <span style={{
              display: 'inline-flex', alignItems: 'center', gap: 6,
              padding: '3px 10px', borderRadius: 20,
              background: `${plat.color}12`, border: `1px solid ${plat.color}20`,
            }}>
              <span style={{ width: 8, height: 8, borderRadius: '50%', background: plat.color, display: 'inline-block' }} />
              <Text style={{ color: plat.color, fontSize: 12, fontWeight: 700, whiteSpace: 'nowrap' }}>{plat.label}</Text>
            </span>
          </div>
        )
      },
    },
    {
      title: '账号',
      key: 'account',
      render: (_: any, record: any) => (
        <Text strong style={{ fontSize: 14, display: 'block', minWidth: 160 }}>{record.account_name}</Text>
      ),
    },
    {
      title: '重要性',
      key: 'importance',
      width: 96,
      render: (_: any, record: any) => {
        const imp = record.importance ? importanceMap[record.importance] : null
        return imp ? (
          <span style={{
            display: 'inline-flex', alignItems: 'center',
            padding: '3px 10px', borderRadius: 10,
            background: `${imp.color}10`, border: `1px solid ${imp.color}18`,
            color: imp.color, fontSize: 12, fontWeight: 700, whiteSpace: 'nowrap',
          }}>
            {imp.label}
          </span>
        ) : <Text type="secondary">—</Text>
      },
    },
    {
      title: '链接',
      key: 'url',
      width: 220,
      render: (_: any, record: any) => record.account_url ? (
        <a
          href={record.account_url}
          target="_blank"
          rel="noopener noreferrer"
          style={{
            color: 'var(--text-secondary)', fontSize: 13, textDecoration: 'none',
            fontFamily: 'var(--font-mono)', display: 'inline-block', maxWidth: 200,
            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
          }}
        >
          {record.account_url}
        </a>
      ) : <Text type="secondary">—</Text>,
    },
    {
      title: '标签',
      key: 'tags',
      width: 260,
      render: (_: any, record: any) => {
        const targetTags: TagItem[] = record.tags || []
        const visibleTags = targetTags.slice(0, MAX_VISIBLE_TAGS)
        const hiddenCount = targetTags.length - visibleTags.length
        return (
          <div style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 4 }}>
            {visibleTags.map((tag: TagItem) => <TagPill key={tag.id} tag={tag} />)}
            {hiddenCount > 0 && (
              <Tooltip title={targetTags.slice(MAX_VISIBLE_TAGS).map((t: TagItem) => t.name).join('、')}>
                <span style={{
                  padding: '2px 8px', borderRadius: 10, fontSize: 11,
                  background: 'var(--surface-1)', border: '1px solid var(--border)',
                  color: 'var(--text-muted)', cursor: 'default',
                }}>+{hiddenCount}</span>
              </Tooltip>
            )}
            <TagSelectPopover
              tags={tags}
              selectedIds={targetTags.map((t: TagItem) => t.id)}
              onChange={(tagIds: number[]) => handleSetTargetTags(record, tagIds)}
              onCreateTag={handleCreateTag}
            >
              <span
                title="打标签"
                style={{
                  display: 'inline-flex', alignItems: 'center', gap: 4,
                  padding: '2px 8px', borderRadius: 10,
                  border: '1px dashed var(--border-strong)', color: 'var(--text-muted)',
                  fontSize: 11, cursor: 'pointer', whiteSpace: 'nowrap',
                }}
              >
                <PlusOutlined style={{ fontSize: 10 }} />
                {targetTags.length === 0 ? '标签' : ''}
              </span>
            </TagSelectPopover>
          </div>
        )
      },
    },
    {
      title: '调度',
      key: 'schedule',
      width: 170,
      render: (_: any, record: any) => {
        const scheduleDisplay = record.cron_schedule
          ? record.cron_schedule.split(';').filter(Boolean)
          : null
        return scheduleDisplay ? (
          <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
            {scheduleDisplay.map((e: string, i: number) => (
              <Tag key={i} style={{ fontFamily: 'var(--font-mono)', fontSize: 11, margin: 0 }}>
                {e}
              </Tag>
            ))}
          </div>
        ) : (
          <Text style={{ color: 'var(--accent)', fontFamily: 'var(--font-mono)', fontSize: 13, fontWeight: 600 }}>
            {String(record.monitor_hour).padStart(2, '0')}:{String(record.monitor_minute).padStart(2, '0')}
          </Text>
        )
      },
    },
    {
      title: '状态',
      key: 'status',
      width: 110,
      render: (_: any, record: any) => (
        <div style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
          <Switch size="small" checked={record.is_active} loading={togglingIds.includes(record.id)} onChange={(checked: boolean) => handleToggleActive(record, checked)} />
          <Text style={{ fontSize: 12, color: record.is_active ? 'var(--accent)' : 'var(--text-muted)', whiteSpace: 'nowrap' }}>
            {record.is_active ? '启用' : '停用'}
          </Text>
        </div>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 240,
      render: (_: any, record: any) => {
        const accounts = orderedAccountsFor(record._platform, grouped[record._platform] || [])
        return (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <Tooltip title="置顶该账号（同平台内）">
              <Button
                type="text"
                size="small"
                icon={<PushpinOutlined />}
                disabled={accounts[0]?.id === record.id}
                onClick={() => pinAccount(record)}
                style={{ color: '#0f766e' }}
              />
            </Tooltip>
            <Tooltip title="立即执行">
              <Button type="text" size="small" icon={<PlayCircleOutlined />} loading={runningId === record.id} onClick={() => openRunModal(record)} style={{ color: '#0f766e' }} />
            </Tooltip>
            {['x', 'weibo', 'facebook'].includes(record.platform) && (
              <Tooltip title="同步（拉取正文存档）">
                <Button type="text" size="small" icon={<SyncOutlined />} loading={syncingId === record.id} onClick={() => openSyncModal(record)} style={{ color: '#3370ff' }} />
              </Tooltip>
            )}
            <Tooltip title="编辑">
              <Button type="text" size="small" icon={<EditOutlined />} onClick={() => openEditModal(record)} />
            </Tooltip>
            <Tooltip title="查看详情">
              <Button type="text" size="small" icon={<SettingOutlined />} onClick={() => navigate('/detail/social_media/' + record.id)} />
            </Tooltip>
            <Popconfirm title="确定删除此账号？" onConfirm={() => handleDelete(record.id)} okButtonProps={{ danger: true }}>
              <Tooltip title="删除">
                <Button type="text" size="small" icon={<DeleteOutlined />} style={{ color: '#c75050' }} />
              </Tooltip>
            </Popconfirm>
          </div>
        )
      },
    },
  ]


  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: 28 }}>
        <div>
          <h1 className="page-title animate-fade-in-up">社交账号管理</h1>
          <div className="page-subtitle">
            SOCIAL ACCOUNTS · {targets.length} 个目标
          </div>
        </div>
        <div style={{ display: 'flex', gap: 10 }}>
          <Button
            icon={<TagsOutlined />}
            onClick={() => setTagManageOpen(true)}
          >
            标签管理
          </Button>
          <Button
            icon={<SettingOutlined />}
            onClick={() => setBatchOpen(true)}
            disabled={targets.length === 0}
          >
            批量设置
          </Button>
          <Button
            icon={<UploadOutlined />}
            onClick={() => setImportOpen(true)}
          >
            批量导入
          </Button>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => { setEditingTarget(null); form.resetFields(); setScheduleMode('simple'); setCronExpressions(['']); setModalOpen(true) }}
          >
            添加账号
          </Button>
        </div>
      </div>

        {/* 统一筛选栏：搜索 + 平台 + 标签，同一高度同一节奏 */}
        <div className="social-filter-bar">
          <Input
            className="page-search-input"
            allowClear
            prefix={<SearchOutlined style={{ color: 'var(--text-muted)' }} />}
            placeholder="搜索账号名称"
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            style={{ width: 'min(420px, 100%)', borderRadius: 10 }}
          />
          <Select
            size="large"
            allowClear
            placeholder="全部平台"
            value={filterPlatform}
            onChange={setFilterPlatform}
            style={{ width: 180, borderRadius: 10 }}
            options={platformOptions.map(p => ({ value: p.value, label: p.label }))}
            optionRender={option => {
              const p = platformOptions.find(x => x.value === option.value)
              return (
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
                  <span style={{ width: 8, height: 8, borderRadius: '50%', background: p?.color || '#94A3B8', flexShrink: 0 }} />
                  <span>{option.label}</span>
                </span>
              )
            }}
          />
          <Select
            className="tag-filter-select"
            mode="multiple"
            size="large"
            allowClear
            placeholder="标签筛选"
            value={filterTagIds.length ? filterTagIds : undefined}
            onChange={setFilterTagIds}
            maxTagCount="responsive"
            style={{ width: 280, borderRadius: 10 }}
            suffixIcon={<TagsOutlined style={{ color: 'var(--text-muted)' }} />}
            options={tags.map(t => ({ value: t.id, label: t.name }))}
            optionRender={option => {
              const t = tags.find(x => x.id === option.value)
              return (
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
                  <span style={{ width: 8, height: 8, borderRadius: '50%', background: t?.color || '#94A3B8', flexShrink: 0 }} />
                  <span>{option.label}</span>
                </span>
              )
            }}
            tagRender={props => {
              const t = tags.find(x => x.id === props.value)
              if (!t) return <span>{props.label}</span>
              return (
                <TagPill
                  tag={t}
                  closable
                  onClose={e => { e.stopPropagation(); props.onClose(e) }}
                  onClick={e => e.stopPropagation()}
                />
              )
            }}
          />
        </div>

              {/* Account table */}
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 8 }}>
          <Button size="small" type="text" icon={<VerticalAlignTopOutlined />} loading={orderSaving} onClick={resetOrder}>
            恢复默认平台排序
          </Button>
        </div>
        <Table
          rowKey="id"
          columns={columns}
          dataSource={tableData}
          loading={loading}
          size="middle"
          scroll={{ x: 1380 }}
          pagination={{ pageSize: 20, showSizeChanger: false, showTotal: (total: number) => `共计 ${total} 个账号` }}
          onRow={(record: any) => ({ style: { opacity: record.is_active ? 1 : 0.65 } })}
          locale={{ emptyText: targets.length === 0 ? '暂无社交账号，点击"添加账号"开始监控' : '未找到匹配当前筛选条件的账号' }}
        />

{/* 标签管理弹窗 */}
      <TagManageModal
        open={tagManageOpen}
        onClose={() => setTagManageOpen(false)}
        tags={tags}
        onChanged={handleTagsChanged}
      />

      {/* 批量设置弹窗：作用于当前筛选结果 */}
      <Modal
        title={`批量设置（${filtered.length} 个账号）`}
        open={batchOpen}
        onOk={handleBatchUpdate}
        okText="应用"
        confirmLoading={batchSaving}
        onCancel={() => { setBatchOpen(false); setBatchActive('keep'); setBatchPush('keep'); setBatchTagIds([]); setBatchTagMode('add') }}
        width={500}
      >
        <div style={{ marginTop: 12, display: 'flex', flexDirection: 'column', gap: 16 }}>
          <Text type="secondary" style={{ fontSize: 13 }}>
            以下设置将作用于当前{searchQuery ? `筛选结果「${searchQuery}」` : '全部账号'}（共 {filtered.length} 个）
          </Text>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <Text style={{ fontSize: 14, fontWeight: 600 }}>启用监测</Text>
            <Select
              value={batchActive}
              onChange={setBatchActive}
              style={{ width: 200 }}
              options={[
                { value: 'keep', label: '保持不变' },
                { value: 'on', label: '开启' },
                { value: 'off', label: '关闭' },
              ]}
            />
          </div>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <Text style={{ fontSize: 14, fontWeight: 600 }}>飞书推送</Text>
            <Select
              value={batchPush}
              onChange={setBatchPush}
              style={{ width: 200 }}
              options={[
                { value: 'keep', label: '保持不变' },
                { value: 'on', label: '开启' },
                { value: 'off', label: '关闭' },
              ]}
            />
          </div>
          <div style={{ borderTop: '1px solid var(--border)', paddingTop: 16 }}>
            <Text style={{ fontSize: 14, fontWeight: 600, display: 'block', marginBottom: 10 }}>
              标签
            </Text>
            <Select
              mode="multiple"
              allowClear
              placeholder="选择标签（可选）"
              value={batchTagIds.length ? batchTagIds : undefined}
              onChange={setBatchTagIds}
              maxTagCount="responsive"
              style={{ width: '100%' }}
              options={tags.map(t => ({ value: t.id, label: t.name }))}
              optionRender={option => {
                const t = tags.find(x => x.id === option.value)
                return (
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ width: 8, height: 8, borderRadius: '50%', background: t?.color || '#94A3B8', flexShrink: 0 }} />
                    <span>{option.label}</span>
                  </span>
                )
              }}
            />
            <Segmented
              block
              value={batchTagMode}
              onChange={v => setBatchTagMode(v as 'add' | 'remove')}
              style={{ marginTop: 10 }}
              options={[
                { value: 'add', label: '添加到所选账号' },
                { value: 'remove', label: '从所选账号移除' },
              ]}
            />
          </div>
        </div>
      </Modal>

      {/* Sync limit modal — 按参考图设计 */}
      <Modal
        open={syncModalOpen}
        onCancel={() => setSyncModalOpen(false)}
        width={440}
        footer={null}
        centered
      >
        <div style={{ padding: '8px 4px 0 4px' }}>
          <Text style={{ fontSize: 17, fontWeight: 700, color: 'var(--text-primary)', display: 'block', marginBottom: 22 }}>
            同步 {platformMap[syncTarget?.platform]?.label || ''}账号
          </Text>

          {/* Account */}
          <Text style={{ fontSize: 12, color: 'var(--text-muted)', display: 'block', marginBottom: 6 }}>
            账号
          </Text>
          <Text style={{ fontSize: 20, fontWeight: 700, color: 'var(--text-primary)', display: 'block', marginBottom: 22 }}>
            @{syncTarget?.account_name}
          </Text>

          {/* Count selector */}
          <Text style={{ fontSize: 12, color: 'var(--text-muted)', display: 'block', marginBottom: 10 }}>
            抓取条数
          </Text>
          <Segmented
            block
            value={syncLimit}
            onChange={v => setSyncLimit(v as number)}
            options={[
              { label: '200', value: 200 },
              { label: '1.0k', value: 1000 },
              { label: '5.0k', value: 5000 },
              { label: '全部', value: 10000 },
            ]}
            style={{ width: '100%' }}
          />

          {/* Custom count input */}
          <InputNumber
            min={1} max={10000}
            value={syncLimit}
            onChange={v => { if (v != null) setSyncLimit(v) }}
            controls={false}
            bordered={false}
            style={{
              fontSize: 30, fontWeight: 700, color: 'var(--text-primary)',
              width: '100%', margin: '14px 0 10px 0', height: 40,
            }}
            placeholder="输入抓取条数 (1-10000)"
          />
          <Text style={{ fontSize: 12, color: 'var(--text-muted)', display: 'block', lineHeight: 1.7, marginBottom: 26 }}>
            最新 N 条帖子（1-10,000）。较大的同步会分页抓取，并在请求之间短暂间隔以降低限流风险。
            {syncTarget?.platform === 'facebook' && '（Facebook 优先用 Chrome 登录态模拟人浏览抓取最新帖；Chrome 未登录 FB 或 CDP 代理不可用时降级为 Google 索引快照模式，约 10 条）'}
          </Text>

          {/* Progress */}
          {syncingId !== null && (
            <div style={{
              display: 'flex', alignItems: 'center', gap: 8,
              marginBottom: 18, padding: '10px 14px', borderRadius: 10,
              background: 'rgba(51,112,255,0.06)', border: '1px solid rgba(51,112,255,0.2)',
              color: 'var(--text-secondary)', fontSize: 13,
            }}>
              <LoadingOutlined spin style={{ color: '#3370ff' }} />
              <span>
                正在同步 @{syncTarget?.account_name}，抓取 {syncLimit} 条帖子... 已等待 {syncElapsed} 秒
              </span>
            </div>
          )}

          {/* Actions */}
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
            <Button disabled={syncingId !== null} onClick={() => setSyncModalOpen(false)}>取消</Button>
            <Button type="primary" loading={syncingId !== null} onClick={handleSync}>开始同步</Button>
          </div>
        </div>
      </Modal>

      {/* 立即执行：时间范围筛选弹窗（默认近24小时） */}
      <Modal
        title={
          batchRunPlatform
            ? '批量执行：' + (platformMap[batchRunPlatform]?.label || batchRunPlatform) + ' 平台'
            : runTarget
              ? '立即执行：' + runTarget.account_name
              : '立即执行'
        }
        open={runModalOpen}
        onOk={confirmRun}
        onCancel={() => setRunModalOpen(false)}
        okText="确认执行"
        cancelText="取消"
        confirmLoading={runningId === runTarget?.id}
        width={520}
      >
        <div style={{ marginTop: 12, display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div>
            <Text type="secondary" style={{ fontSize: 13 }}>
              选择数据时间范围，仅获取该时间段内发布的贴文（默认近24小时）
              {batchRunPlatform && ('；将对 ' + activeCountOf(batchRunPlatform) + ' 个启用账号逐个执行')}
            </Text>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 12 }}>
              {runTimePresets.map(p => (
                <Button
                  key={p.label}
                  size="small"
                  type={runPreset === p.label ? 'primary' : 'default'}
                  onClick={() => {
                    setRunPreset(p.label)
                    setRunRange([dayjs().subtract(p.hours, 'hour'), dayjs()])
                  }}
                >
                  {p.label}
                </Button>
              ))}
            </div>
          </div>
          <div>
            <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 8 }}>
              自定义范围（精确到分钟）
            </Text>
            <DatePicker.RangePicker
              showTime={{ format: 'HH:mm' }}
              format="YYYY-MM-DD HH:mm"
              value={runRange}
              onChange={v => {
                setRunRange(v as [dayjs.Dayjs, dayjs.Dayjs] | null)
                setRunPreset('')
              }}
              allowClear={false}
              style={{ width: '100%' }}
            />
          </div>
          <div style={{
            padding: '8px 12px', borderRadius: 8, fontSize: 12,
            color: 'var(--text-muted)', background: 'var(--surface-2)',
          }}>
            平台无发布时间的贴文会被过滤；确认后将按此时间范围抓取并筛选贴文，完成后自动写入最新监测结果。
          </div>
        </div>
      </Modal>

      {/* Sync result drawer — 按参考图设计 */}
      <Drawer
        open={syncDrawerOpen}
        onClose={() => setSyncDrawerOpen(false)}
        width={800}
      >
        {syncTarget && (
          <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
            {/* Header: 账号 + 条数 + 同步/浏览 */}
            <div style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              marginBottom: 14,
            }}>
              <Text style={{ fontSize: 18, fontWeight: 700, color: 'var(--text-primary)' }}>
                @{syncTarget.account_name}{' '}
                <Text type="secondary" style={{ fontSize: 14, fontWeight: 400 }}>
                  {syncPosts?.length ?? 0} 条帖子
                </Text>
              </Text>
              <div style={{ display: 'flex', gap: 8 }}>
                <Button
                  size="small" icon={<SyncOutlined />}
                  loading={syncingId === syncTarget.id}
                  onClick={() => openSyncModal(syncTarget)}
                >
                  同步
                </Button>
                <Button
                  size="small" icon={<SettingOutlined />}
                  onClick={() => navigate(`/detail/social_media/${syncTarget.id}`)}
                >
                  浏览
                </Button>
              </div>
            </div>

            {/* Info row: 最早 / 最新 / 上次同步 */}
            <div style={{
              display: 'flex', gap: 24, marginBottom: 14, flexWrap: 'wrap',
              color: 'var(--text-muted)', fontSize: 13,
            }}>
              <span>最早：{syncRange.earliest}</span>
              <span>最新：{syncRange.latest}</span>
              <span>上次同步:{(syncSyncedAt || '').replace(/-/g, '/') || '-'}</span>
            </div>

            {/* Export row */}
            <div style={{ display: 'flex', gap: 10, marginBottom: 20 }}>
              <Button icon={<DownloadOutlined />} onClick={handleExportNdjson} disabled={!syncPosts?.length}>
                导出为 NDJSON
              </Button>
              <Button icon={<DownloadOutlined />} onClick={handleExportMd} disabled={!syncPosts?.length}>
                导出为 Markdown
              </Button>
            </div>

            {/* Recent posts */}
            <Text style={{
              fontSize: 14, fontWeight: 600, color: 'var(--text-primary)',
              marginBottom: 12, display: 'block',
            }}>
              最近帖子
            </Text>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12, overflow: 'auto', flex: 1 }}>
              {!syncPosts?.length ? (
                <div style={{ textAlign: 'center', padding: '48px 0', color: 'var(--text-muted)' }}>
                  暂无内容
                </div>
              ) : syncPosts.map((p: any, i: number) => (
                <div key={i} style={{
                  background: 'var(--surface-1)', border: '1px solid var(--border)',
                  borderRadius: 12, padding: 14,
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, marginBottom: 6 }}>
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      {fmtPostTime(p.published_at)}
                    </Text>
                    {extractPostId(p) && (
                      <Tag style={{
                        fontSize: 11, margin: 0, fontFamily: 'var(--font-mono)',
                        background: 'rgba(51,112,255,0.08)', border: '1px solid rgba(51,112,255,0.2)',
                        color: '#3370ff',
                      }}>
                        {extractPostId(p)}
                      </Tag>
                    )}
                  </div>
                  <div style={{
                    color: 'var(--text-primary)', fontSize: 14, lineHeight: 1.7,
                    whiteSpace: 'pre-wrap', wordBreak: 'break-word',
                  }}>
                    {p.content}
                  </div>
                  {p.url && (
                    <a href={p.url} target="_blank" rel="noopener noreferrer"
                      style={{ fontSize: 12, display: 'block', marginTop: 8, wordBreak: 'break-all', color: '#3370ff' }}>
                      {p.url}
                    </a>
                  )}
                  <div style={{
                    display: 'flex', gap: 16, marginTop: 8,
                    color: 'var(--text-muted)', fontSize: 12,
                  }}>
                    <span>点赞 {p.likes ?? 0}</span>
                    <span>评论 {p.comments_count ?? 0}</span>
                    <span>转发 {p.shares ?? 0}</span>
                    <span>浏览 {p.views ?? 0}</span>
                  </div>
                  {Array.isArray(p.images) && p.images.length > 0 && (
                    <div style={{ display: 'flex', gap: 8, marginTop: 10, flexWrap: 'wrap' }}>
                      {p.images.map((img: string, j: number) => (
                        <img key={j} src={img} alt="" style={{
                          width: 96, height: 96, objectFit: 'cover', borderRadius: 8,
                          border: '1px solid var(--border)',
                        }} />
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
      </Drawer>

      {/* 批量立即执行进度抽屉 */}
      <Drawer
        open={batchRunDrawerOpen}
        onClose={() => setBatchRunDrawerOpen(false)}
        width={560}
        title={
          batchRunPlatform
            ? '批量执行 · ' + (platformMap[batchRunPlatform]?.label || batchRunPlatform)
            : '批量执行进度'
        }
      >
        {(() => {
          const entries = filtered.filter((t: any) => batchRunStatuses[t.id] !== undefined)
          const count = (s: string) => entries.filter((t: any) => batchRunStatuses[t.id] === s).length
          const done = count('success') + count('failed') + count('skipped')
          const running = count('running')
          const hasFailed = count('failed') > 0
          return (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
                <Tag color="default">共 {entries.length} 个</Tag>
                <Tag color="green">成功 {count('success')}</Tag>
                <Tag color="red">失败 {count('failed')}</Tag>
                <Tag color="blue">进行中 {running}</Tag>
                <Tag>跳过(停用) {count('skipped')}</Tag>
                {done === entries.length && (
                  <Button size="small" icon={<SyncOutlined />} disabled={!hasFailed} onClick={retryBatchFailed}>
                    重试失败
                  </Button>
                )}
              </div>
              {entries.map((t: any) => {
                const s = batchRunStatuses[t.id]
                const err = batchRunErrors[t.id]
                const icon = s === 'success'
                  ? <CheckCircleOutlined style={{ color: '#22C55E' }} />
                  : s === 'failed'
                    ? <CloseCircleOutlined style={{ color: '#c75050' }} />
                    : s === 'running'
                      ? <LoadingOutlined spin style={{ color: '#3370ff' }} />
                      : s === 'skipped'
                        ? <PauseCircleOutlined style={{ color: '#8c8c8c' }} />
                        : <ClockCircleOutlined style={{ color: '#8c8c8c' }} />
                const label = s === 'success' ? '成功' : s === 'failed' ? '失败' : s === 'running' ? '执行中' : s === 'skipped' ? '跳过(停用)' : '等待中'
                return (
                  <div key={t.id} style={{
                    display: 'flex', alignItems: 'center', gap: 10,
                    padding: '10px 14px', borderRadius: 10,
                    background: 'var(--surface-1)', border: '1px solid var(--border)',
                  }}>
                    {icon}
                    <Text style={{ color: 'var(--text-primary)', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {t.account_name}
                    </Text>
                    <Text style={{ fontSize: 12, color: 'var(--text-muted)' }}>{label}</Text>
                    {err && (
                      <Tooltip title={err}>
                        <Text style={{ fontSize: 12, color: '#c75050' }}>详情</Text>
                      </Tooltip>
                    )}
                  </div>
                )
              })}
            </div>
          )
        })()}
      </Drawer>

      {/* Add/Edit modal */}
      <Modal
        title={editingTarget ? '编辑账号' : '添加账号'}
        open={modalOpen}
        onOk={handleSubmit}
        onCancel={() => { setModalOpen(false); setEditingTarget(null); form.resetFields(); setScheduleMode('simple'); setCronExpressions(['']) }}
        width={560}
      >
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item name="platform" label="平台" rules={[{ required: true }]}>
            <Select options={platformOptions} placeholder="选择平台" />
          </Form.Item>
          <Form.Item name="account_name" label="账号名称" rules={[{ required: true }]}>
            <Input
              placeholder={fbPlatform ? '如: 某公众人物昵称' : '如: @elonmusk'}
              suffix={
                fbPlatform ? (
                  <Button
                    type="link"
                    size="small"
                    loading={fbSearching}
                    onClick={handleFbSearch}
                    style={{ padding: 0, height: 'auto' }}
                  >
                    搜索候选账号
                  </Button>
                ) : null
              }
            />
          </Form.Item>
          <Form.Item name="account_url" label="账号 URL" rules={[{ required: true }]}>
            <Input placeholder={fbPlatform ? '如: https://www.facebook.com/xxx （也可点上方按钮反查填充）' : '如: https://x.com/elonmusk'} />
          </Form.Item>
          <Form.Item name="avatar_url" label="头像 URL">
            <Input placeholder="可选" />
          </Form.Item>
          <Form.Item name="importance" label="重要性">
            <Select options={importanceOptions} placeholder="选择重要性" allowClear />
          </Form.Item>
          <Form.Item name="tag_ids" label="标签">
            <Select
              mode="multiple"
              allowClear
              placeholder="选择标签（可多选）"
              options={tags.map(t => ({ value: t.id, label: t.name }))}
              optionRender={option => {
                const t = tags.find(x => x.id === option.value)
                return (
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ width: 8, height: 8, borderRadius: '50%', background: t?.color || '#94A3B8', flexShrink: 0 }} />
                    <span>{option.label}</span>
                  </span>
                )
              }}
              tagRender={props => {
                const t = tags.find(x => x.id === props.value)
                if (!t) return <span>{props.label}</span>
                return (
                  <TagPill
                    tag={t}
                    closable
                    onClose={e => { e.stopPropagation(); props.onClose(e) }}
                    onClick={e => e.stopPropagation()}
                  />
                )
              }}
            />
          </Form.Item>
          <Form.Item label="调度模式">
            <Select
              value={scheduleMode}
              onChange={v => {
                setScheduleMode(v)
                if (v === 'cron' && cronExpressions.length === 0) setCronExpressions([''])
              }}
              options={[
                { value: 'simple', label: '每天定时' },
                { value: 'cron', label: '高级 Cron 表达式' },
              ]}
              style={{ width: 200 }}
            />
          </Form.Item>

          {scheduleMode === 'simple' ? (
            <div style={{ display: 'flex', gap: 16 }}>
              <Form.Item name="monitor_hour" label="监测小时" initialValue={9} style={{ flex: 1 }}>
                <InputNumber min={0} max={23} style={{ width: '100%' }} />
              </Form.Item>
              <Form.Item name="monitor_minute" label="监测分钟" initialValue={0} style={{ flex: 1 }}>
                <InputNumber min={0} max={59} style={{ width: '100%' }} />
              </Form.Item>
            </div>
          ) : (
            <Form.Item label="Cron 表达式">
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {cronExpressions.map((expr, idx) => (
                  <div key={idx} style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                    <Input
                      value={expr}
                      onChange={e => {
                        const updated = [...cronExpressions]
                        updated[idx] = e.target.value
                        setCronExpressions(updated)
                      }}
                      placeholder="分 时 日 月 周 (如: 0 9 * * *)"
                      style={{ flex: 1, fontFamily: 'var(--font-mono)' }}
                    />
                    {cronExpressions.length > 1 && (
                      <Button
                        danger
                        size="small"
                        onClick={() => setCronExpressions(cronExpressions.filter((_, i) => i !== idx))}
                      >
                        删除
                      </Button>
                    )}
                  </div>
                ))}
                <Button
                  type="dashed"
                  size="small"
                  onClick={() => setCronExpressions([...cronExpressions, ''])}
                  style={{ width: 120 }}
                >
                  + 添加定时
                </Button>
              </div>
            </Form.Item>
          )}

          <div style={{ display: 'flex', gap: 16 }}>
            <Form.Item name="post_limit" label="抓取数量" initialValue={10} style={{ flex: 1 }}>
              <InputNumber min={1} max={100} style={{ width: '100%' }} addonAfter="条" />
            </Form.Item>
            <Form.Item name="post_time_range_days" label="时间范围" initialValue={0} style={{ flex: 1 }}>
              <InputNumber min={0} max={365} style={{ width: '100%' }} addonAfter="天" />
            </Form.Item>
          </div>
          <Text style={{ color: 'var(--text-muted)', fontSize: 12, marginTop: -8, marginBottom: 16, display: 'block' }}>
            时间范围填 0 表示不限制
          </Text>

          <Form.Item name="is_active" label="启用" valuePropName="checked" initialValue={true}>
            <Switch />
          </Form.Item>
          <Form.Item name="push_enabled" label="飞书推送" valuePropName="checked" initialValue={true}
            tooltip="监测完成后向绑定的飞书账号推送摘要/告警">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>

      {/* Facebook 昵称反查候选选择 */}
      <Modal
        title="选择 Facebook 候选账号"
        open={fbSearchOpen}
        onCancel={() => setFbSearchOpen(false)}
        footer={null}
        width={560}
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <div style={{
            padding: '10px 14px',
            borderRadius: 8,
            fontSize: 13,
            color: 'var(--text-secondary)',
            background: 'rgba(24,119,242,0.12)',
            border: '1px solid rgba(24,119,242,0.35)',
          }}>
            以下为 Google 搜索到的疑似主页，点击一条即可自动填充账号名称与 URL。
          </div>
          {fbCandidates.length === 0 ? (
            <div style={{ textAlign: 'center', padding: 24, color: 'var(--text-muted)' }}>
              未找到匹配的 Facebook 主页
            </div>
          ) : (
            fbCandidates.map((c, i) => (
              <div
                key={i}
                onClick={() => handleFbPick(c)}
                style={{
                  padding: '12px 14px',
                  borderRadius: 10,
                  border: '1px solid rgba(24,119,242,0.25)',
                  background: 'var(--surface-1)',
                  cursor: 'pointer',
                  transition: 'border-color 0.2s',
                }}
                onMouseEnter={e => (e.currentTarget.style.borderColor = '#1877F2')}
                onMouseLeave={e => (e.currentTarget.style.borderColor = 'rgba(24,119,242,0.25)')}
              >
                <div style={{ fontWeight: 600, fontSize: 14, color: '#1877F2' }}>{c.nickname}</div>
                <div style={{ fontSize: 12, color: 'var(--text-muted)', wordBreak: 'break-all', marginTop: 2 }}>{c.url}</div>
                {c.snippet ? (
                  <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4, display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
                    {c.snippet}
                  </div>
                ) : null}
              </div>
            ))
          )}
        </div>
      </Modal>

      {/* Import modal */}
      <Modal
        title="批量导入社交账号"
        open={importOpen}
        onCancel={() => { setImportOpen(false); setImportResult(null) }}
        footer={null}
        width={520}
      >
        <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 16 }}>
          <Alert
            type="info"
            showIcon
            className="import-alert-info"
            message="请先下载模板，按固定列名整理后上传"
            description={
              <>
                支持 xlsx / xls / csv 格式；列名必须为：<b>平台、账号名称、账号URL</b>。<br />
                平台可选：x / youtube / xiaohongshu / douyin / weibo / toutiao / 108community / facebook（支持中文别名，如"微博"）。
                重复账号 URL 会自动跳过。
              </>
            }
          />
          <div style={{ display: 'flex', gap: 10 }}>
            <Button icon={<DownloadOutlined />} onClick={handleDownloadTemplate} style={{ flex: 1 }}>
              下载导入模板
            </Button>
          </div>
          <Upload.Dragger
            accept=".xlsx,.xls,.csv"
            showUploadList={false}
            beforeUpload={handleImportFile}
            disabled={importing}
          >
            <p className="ant-upload-drag-icon"><FileExcelOutlined /></p>
            <p className="ant-upload-text">点击或拖拽文件到此处上传</p>
            <p className="ant-upload-hint">{importing ? '正在导入...' : '上传后自动解析并批量创建'}</p>
          </Upload.Dragger>

          {importResult && (
            <div style={{
              background: 'var(--surface-1)', borderRadius: 12, padding: '14px 16px',
              border: '1px solid var(--border)',
            }}>
              <Text strong>导入结果</Text>
              <div style={{ display: 'flex', gap: 16, marginTop: 8 }}>
                <Tag color="blue">共 {importResult.total} 行</Tag>
                <Tag color="green">成功 {importResult.created}</Tag>
                <Tag color="orange">重复跳过 {importResult.skipped_dup}</Tag>
                <Tag color="red">失败 {importResult.failed}</Tag>
              </div>
              {importResult.errors?.length > 0 && (
                <div style={{ marginTop: 10, maxHeight: 160, overflowY: 'auto', fontSize: 12, color: '#c75050' }}>
                  {importResult.errors.map((e: string, i: number) => (
                    <div key={i}>{e}</div>
                  ))}
                </div>
              )}
              {importResult.created_names?.length > 0 && (
                <div style={{ marginTop: 8, fontSize: 12, color: 'var(--text-secondary)' }}>
                  已导入: {importResult.created_names.join('、')}
                </div>
              )}
            </div>
          )}
        </div>
      </Modal>
    </div>
  )
}
