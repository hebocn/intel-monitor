import { useEffect, useState } from 'react'
import { Button, Modal, Form, Input, InputNumber, Switch, Tag, message, Popconfirm, Typography, Tooltip, Skeleton } from 'antd'
import {
  PlusOutlined, EditOutlined, DeleteOutlined, PlayCircleOutlined,
  ClockCircleOutlined, GlobalOutlined, CodeOutlined,
  CheckCircleOutlined, PauseCircleOutlined, LinkOutlined,
} from '@ant-design/icons'
import { websitesAPI, scheduleAPI, resultsAPI } from '../services/api'
import { useNavigate } from 'react-router-dom'

const { Text } = Typography

const siteColor = '#5a7a9a'

function WebsiteCard({
  site,
  running,
  onRun,
  onEdit,
  onDelete,
  onDetail,
  idx,
}: {
  site: any
  running: boolean
  onRun: () => void
  onEdit: () => void
  onDelete: () => void
  onDetail: () => void
  idx: number
}) {
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
        background: `linear-gradient(180deg, ${siteColor}, ${siteColor}88)`,
        borderRadius: '4px 0 0 4px',
      }} />

      {/* Header */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '18px 22px 14px 22px',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          {/* Website icon badge */}
          <div style={{
            display: 'inline-flex', alignItems: 'center', gap: 6,
            padding: '5px 14px 5px 10px',
            borderRadius: 20,
            background: `${siteColor}12`,
            border: `1px solid ${siteColor}20`,
          }}>
            <GlobalOutlined style={{ color: siteColor, fontSize: 12 }} />
            <Text style={{ color: siteColor, fontSize: 12, fontWeight: 700, fontFamily: 'var(--font-body)' }}>
              网站
            </Text>
          </div>

          {/* Site name */}
          <Text style={{ color: 'var(--text-primary)', fontWeight: 700, fontSize: 16 }}>
            {site.name}
          </Text>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          {/* Status pill */}
          <div style={{
            display: 'inline-flex', alignItems: 'center', gap: 5,
            padding: '3px 12px', borderRadius: 12,
            background: site.is_active ? 'rgba(34,197,94,0.08)' : 'rgba(140,140,140,0.08)',
            color: site.is_active ? '#22C55E' : '#8c8c8c',
            fontSize: 12, fontWeight: 600,
          }}>
            {site.is_active ? <CheckCircleOutlined /> : <PauseCircleOutlined />}
            {site.is_active ? '启用' : '停用'}
          </div>

          {/* Actions */}
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
          <Tooltip title="编辑">
            <Button type="text" size="small" icon={<EditOutlined />} onClick={onEdit} />
          </Tooltip>
          <Tooltip title="查看详情">
            <Button type="text" size="small" icon={<GlobalOutlined />} onClick={onDetail} />
          </Tooltip>
          <Popconfirm title="确定删除此网站？" onConfirm={onDelete} okButtonProps={{ danger: true }}>
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
              href={site.url}
              target="_blank"
              rel="noopener noreferrer"
              style={{
                color: 'var(--text-secondary)', fontSize: 13,
                textDecoration: 'none', maxWidth: 360,
                overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                fontFamily: 'var(--font-mono)',
              }}
            >
              {site.url}
            </a>
          </div>

          {/* CSS Selector */}
          {site.css_selector && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <CodeOutlined style={{ color: 'var(--text-muted)', fontSize: 12 }} />
              <Tag style={{
                fontFamily: 'var(--font-mono)', fontSize: 11,
                background: 'rgba(15,118,110,0.06)', color: '#0f766e',
                border: '1px solid rgba(15,118,110,0.12)',
                borderRadius: 8, padding: '1px 8px', margin: 0,
              }}>
                {site.css_selector}
              </Tag>
            </div>
          )}

          {/* Schedule */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <ClockCircleOutlined style={{ color: 'var(--text-muted)', fontSize: 12 }} />
            <Text style={{
              color: 'var(--accent)', fontFamily: 'var(--font-mono)', fontSize: 13, fontWeight: 600,
            }}>
              {String(site.monitor_hour).padStart(2, '0')}:{String(site.monitor_minute).padStart(2, '0')}
            </Text>
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

export default function WebsitesPage() {
  const [websites, setWebsites] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<any>(null)
  const [runningId, setRunningId] = useState<number | null>(null)
  const [form] = Form.useForm()
  const navigate = useNavigate()

  const fetch = async () => {
    setLoading(true)
    try {
      const res = await websitesAPI.list()
      setWebsites(res.data)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetch() }, [])

  const handleSubmit = async () => {
    const values = await form.validateFields()
    try {
      if (editing) {
        await websitesAPI.update(editing.id, values)
        message.success('更新成功')
      } else {
        await websitesAPI.create(values)
        message.success('添加成功')
      }
      setModalOpen(false)
      form.resetFields()
      setEditing(null)
      fetch()
    } catch (err: any) {
      message.error(err.response?.data?.detail || '操作失败')
    }
  }

  const handleDelete = async (id: number) => {
    await websitesAPI.delete(id)
    message.success('删除成功')
    fetch()
  }

  const handleRunNow = async (id: number) => {
    setRunningId(id)
    message.info('开始监测，请稍候...')
    try {
      const res = await scheduleAPI.runNow(id, 'website')
      const { result_id } = res.data

      const pollResult = async () => {
        for (let i = 0; i < 60; i++) {
          await new Promise(r => setTimeout(r, 2000))
          try {
            const detailRes = await resultsAPI.detail(result_id)
            const result = detailRes.data
            if (result.status === 'success') {
              message.success('监测完成')
              fetch()
              setRunningId(null)
              return
            } else if (result.status === 'failed') {
              message.warning(result.error_message || '监测失败')
              fetch()
              setRunningId(null)
              return
            }
          } catch {}
        }
        fetch()
        setRunningId(null)
      }
      pollResult()
    } catch (err: any) {
      message.error(err.response?.data?.detail || '监测启动失败')
      setRunningId(null)
    }
  }

  const openEditModal = (site: any) => {
    setEditing(site)
    form.setFieldsValue(site)
    setModalOpen(true)
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: 28 }}>
        <div>
          <h1 className="page-title animate-fade-in-up">网站监测管理</h1>
          <div className="page-subtitle animate-fade-in-up" style={{ animationDelay: '0.05s' }}>
            WEBSITE TARGETS · {websites.length} 个目标
          </div>
        </div>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => { setEditing(null); form.resetFields(); setModalOpen(true) }}
          className="animate-fade-in-up"
          style={{ animationDelay: '0.1s' }}
        >
          添加网站
        </Button>
      </div>

      {/* Website cards */}
      {loading ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} style={{
              background: 'var(--surface-2)', borderRadius: 16, border: '1px solid var(--border)', padding: '22px',
            }}>
              <div style={{ display: 'flex', gap: 12, marginBottom: 14 }}>
                <Skeleton.Input active style={{ width: 60, height: 26, borderRadius: 12 }} />
                <Skeleton.Input active style={{ width: 160, height: 22, borderRadius: 4 }} />
              </div>
              <Skeleton.Input active style={{ width: '80%', height: 16, borderRadius: 4 }} />
            </div>
          ))}
        </div>
      ) : websites.length === 0 ? (
        <div style={{
          textAlign: 'center', padding: '80px 0',
          color: 'var(--text-muted)', fontSize: 14,
        }}>
          暂无网站监测，点击"添加网站"开始监控
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {websites.map((site, idx) => (
            <WebsiteCard
              key={site.id}
              site={site}
              running={runningId === site.id}
              onRun={() => handleRunNow(site.id)}
              onEdit={() => openEditModal(site)}
              onDelete={() => handleDelete(site.id)}
              onDetail={() => navigate(`/detail/website/${site.id}`)}
              idx={idx}
            />
          ))}
        </div>
      )}

      {/* Add/Edit modal */}
      <Modal
        title={editing ? '编辑网站' : '添加网站'}
        open={modalOpen}
        onOk={handleSubmit}
        onCancel={() => { setModalOpen(false); setEditing(null); form.resetFields() }}
        width={560}
      >
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item name="name" label="网站名称" rules={[{ required: true }]}>
            <Input placeholder="如: 某某新闻网" />
          </Form.Item>
          <Form.Item name="url" label="网站 URL" rules={[{ required: true }]}>
            <Input placeholder="https://example.com" />
          </Form.Item>
          <Form.Item name="css_selector" label="CSS 选择器 (可选)">
            <Input placeholder="如: .article-content" />
          </Form.Item>
          <div style={{ display: 'flex', gap: 16 }}>
            <Form.Item name="monitor_hour" label="监测小时" initialValue={9} style={{ flex: 1 }}>
              <InputNumber min={0} max={23} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="monitor_minute" label="监测分钟" initialValue={0} style={{ flex: 1 }}>
              <InputNumber min={0} max={59} style={{ width: '100%' }} />
            </Form.Item>
          </div>
          <Form.Item name="is_active" label="启用" valuePropName="checked" initialValue={true}>
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
