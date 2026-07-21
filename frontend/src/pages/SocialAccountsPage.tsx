import { useEffect, useState } from 'react'
import { Button, Modal, Form, Input, Select, InputNumber, Switch, Tag, message, Popconfirm, Typography, Tooltip, Skeleton } from 'antd'
import {
  PlusOutlined, EditOutlined, DeleteOutlined, PlayCircleOutlined,
  ClockCircleOutlined, LinkOutlined, PauseCircleOutlined,
  CheckCircleOutlined, SettingOutlined,
} from '@ant-design/icons'
import { targetsAPI, scheduleAPI, resultsAPI } from '../services/api'
import { useNavigate } from 'react-router-dom'

const { Text } = Typography

const platformOptions = [
  { value: 'x', label: 'X (Twitter)', color: '#1DA1F2' },
  { value: 'youtube', label: 'YouTube', color: '#FF0000' },
  { value: 'xiaohongshu', label: '小红书', color: '#FE2C55' },
  { value: 'douyin', label: '抖音', color: '#000000' },
  { value: 'weibo', label: '微博', color: '#E6162D' },
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

function AccountCard({
  target,
  running,
  onRun,
  onEdit,
  onDelete,
  onDetail,
  idx,
}: {
  target: any
  running: boolean
  onRun: () => void
  onEdit: () => void
  onDelete: () => void
  onDetail: () => void
  idx: number
}) {
  const plat = platformMap[target.platform] || { label: target.platform, color: '#666' }
  const imp = target.importance ? importanceMap[target.importance] : null

  const scheduleDisplay = target.cron_schedule
    ? target.cron_schedule.split(';').filter(Boolean)
    : null

  return (
    <div
      className={`animate-fade-in-up delay-${Math.min(idx + 1, 6)}`}
      style={{
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
        background: `linear-gradient(180deg, ${plat.color}, ${plat.color}88)`,
        borderRadius: '4px 0 0 4px',
      }} />

      {/* Header */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '18px 22px 14px 22px',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
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
          {/* Status pill */}
          <div style={{
            display: 'inline-flex', alignItems: 'center', gap: 5,
            padding: '3px 12px', borderRadius: 12,
            background: target.is_active ? 'rgba(82,183,136,0.08)' : 'rgba(140,140,140,0.08)',
            color: target.is_active ? '#52b788' : '#8c8c8c',
            fontSize: 12, fontWeight: 600,
          }}>
            {target.is_active ? <CheckCircleOutlined /> : <PauseCircleOutlined />}
            {target.is_active ? '启用' : '停用'}
          </div>

          {/* Actions */}
          <Tooltip title="立即执行">
            <Button
              type="text"
              size="small"
              icon={<PlayCircleOutlined />}
              onClick={onRun}
              loading={running}
              style={{ color: '#2d6a4f' }}
            />
          </Tooltip>
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

      {/* Details */}
      <div style={{ padding: '0 22px 18px 22px' }}>
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
              background: 'rgba(45,106,79,0.08)',
              color: '#2d6a4f', fontSize: 12, fontWeight: 600,
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
  const [form] = Form.useForm()
  const navigate = useNavigate()
  const [scheduleMode, setScheduleMode] = useState<'simple' | 'cron'>('simple')
  const [cronExpressions, setCronExpressions] = useState<string[]>([''])

  const fetchTargets = async () => {
    setLoading(true)
    try {
      const res = await targetsAPI.list()
      setTargets(res.data)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchTargets() }, [])

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

    try {
      if (editingTarget) {
        await targetsAPI.update(editingTarget.id, values)
        message.success('更新成功')
      } else {
        await targetsAPI.create(values)
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

  const handleDelete = async (id: number) => {
    await targetsAPI.delete(id)
    message.success('删除成功')
    fetchTargets()
  }

  const handleRunNow = async (id: number) => {
    setRunningId(id)
    message.info('开始监测...')
    try {
      const res = await scheduleAPI.runNow(id, 'social_media')
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

  const openEditModal = (target: any) => {
    setEditingTarget(target)
    form.setFieldsValue(target)
    if (target.cron_schedule) {
      setScheduleMode('cron')
      setCronExpressions(target.cron_schedule.split(';').filter(Boolean))
    } else {
      setScheduleMode('simple')
      setCronExpressions([''])
    }
    setModalOpen(true)
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: 28 }}>
        <div>
          <h1 className="page-title animate-fade-in-up">社交账号管理</h1>
          <div className="page-subtitle animate-fade-in-up" style={{ animationDelay: '0.05s' }}>
            SOCIAL ACCOUNTS · {targets.length} 个目标
          </div>
        </div>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => { setEditingTarget(null); form.resetFields(); setScheduleMode('simple'); setCronExpressions(['']); setModalOpen(true) }}
          className="animate-fade-in-up"
          style={{ animationDelay: '0.1s' }}
        >
          添加账号
        </Button>
      </div>

      {/* Account cards */}
      {loading ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} style={{
              background: '#fff', borderRadius: 16, border: '1px solid var(--border)', padding: '22px',
            }}>
              <div style={{ display: 'flex', gap: 12, marginBottom: 14 }}>
                <Skeleton.Input active style={{ width: 80, height: 26, borderRadius: 12 }} />
                <Skeleton.Input active style={{ width: 50, height: 22, borderRadius: 10 }} />
                <Skeleton.Input active style={{ width: 140, height: 22, borderRadius: 4 }} />
              </div>
              <Skeleton.Input active style={{ width: '70%', height: 16, borderRadius: 4 }} />
            </div>
          ))}
        </div>
      ) : targets.length === 0 ? (
        <div style={{
          textAlign: 'center', padding: '80px 0',
          color: 'var(--text-muted)', fontSize: 14,
        }}>
          暂无社交账号，点击"添加账号"开始监控
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {targets.map((target, idx) => (
            <AccountCard
              key={target.id}
              target={target}
              running={runningId === target.id}
              onRun={() => handleRunNow(target.id)}
              onEdit={() => openEditModal(target)}
              onDelete={() => handleDelete(target.id)}
              onDetail={() => navigate(`/detail/social_media/${target.id}`)}
              idx={idx}
            />
          ))}
        </div>
      )}

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
            <Input placeholder="如: @elonmusk" />
          </Form.Item>
          <Form.Item name="account_url" label="账号 URL" rules={[{ required: true }]}>
            <Input placeholder="如: https://x.com/elonmusk" />
          </Form.Item>
          <Form.Item name="avatar_url" label="头像 URL">
            <Input placeholder="可选" />
          </Form.Item>
          <Form.Item name="importance" label="重要性">
            <Select options={importanceOptions} placeholder="选择重要性" allowClear />
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
        </Form>
      </Modal>
    </div>
  )
}
