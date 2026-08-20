import { useEffect, useState } from 'react'
import { Button, Modal, Form, Input, InputNumber, Switch, Tag, message, Popconfirm, Typography, Tooltip, Skeleton, Upload, Alert, Select } from 'antd'
import {
  PlusOutlined, EditOutlined, DeleteOutlined, PlayCircleOutlined,
  ClockCircleOutlined, GlobalOutlined, CodeOutlined,
  CheckCircleOutlined, PauseCircleOutlined, LinkOutlined,
  UploadOutlined, DownloadOutlined, FileExcelOutlined,
  SearchOutlined, SettingOutlined,
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
        style={{
          background: 'transparent',
          borderRadius: 0,
          border: 'none',
          borderBottom: '1px solid var(--border)',
          overflow: 'visible',
          transition: 'background-color 0.2s ease, border-color 0.2s ease, color 0.2s ease',
          position: 'relative',
      }}
    >

      {/* Header */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '16px 0 10px 0',
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
        <div style={{ padding: '0 0 18px 0' }}>
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
  const [importOpen, setImportOpen] = useState(false)
  const [importing, setImporting] = useState(false)
  const [importResult, setImportResult] = useState<any>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [batchOpen, setBatchOpen] = useState(false)
  const [batchActive, setBatchActive] = useState<'keep' | 'on' | 'off'>('keep')
  const [batchPush, setBatchPush] = useState<'keep' | 'on' | 'off'>('keep')
  const [batchSaving, setBatchSaving] = useState(false)
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

  const handleDownloadTemplate = async () => {
    try {
      const res = await websitesAPI.importTemplate()
      const blob = new Blob([res.data], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'website_import_template.xlsx'
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
      const res = await websitesAPI.importBatch(formData)
      setImportResult(res.data)
      message.success(`导入完成：成功 ${res.data.created} 条`)
      fetch()
    } catch (err: any) {
      message.error(err.response?.data?.detail || '导入失败')
      setImportResult(null)
    } finally {
      setImporting(false)
    }
    return false // 阻止 Upload 默认上传
  }

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

  // 前端本地过滤：按网站名搜索
  const filtered = searchQuery.trim()
    ? websites.filter((w: any) => (w.name || '').toLowerCase().includes(searchQuery.trim().toLowerCase()))
    : websites

  const handleBatchUpdate = async () => {
    if (filtered.length === 0) return
    const payload: any = { website_ids: filtered.map((w: any) => w.id) }
    if (batchActive !== 'keep') payload.is_active = batchActive === 'on'
    if (batchPush !== 'keep') payload.push_enabled = batchPush === 'on'
    if (payload.is_active === undefined && payload.push_enabled === undefined) {
      message.warning('请至少选择一项要修改的开关')
      return
    }
    setBatchSaving(true)
    try {
      const res = await websitesAPI.batchUpdate(payload)
      message.success(`已批量更新 ${res.data.updated} 个网站`)
      setBatchOpen(false)
      setBatchActive('keep')
      setBatchPush('keep')
      fetch()
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '批量更新失败')
    } finally {
      setBatchSaving(false)
    }
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: 28 }}>
        <div>
          <h1 className="page-title animate-fade-in-up">网站监测管理</h1>
          <div className="page-subtitle">
            WEBSITE TARGETS · {websites.length} 个目标
          </div>
        </div>
        <div style={{ display: 'flex', gap: 10 }}>
          <Button
            icon={<SettingOutlined />}
            onClick={() => setBatchOpen(true)}
            disabled={websites.length === 0}
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
            onClick={() => { setEditing(null); form.resetFields(); setModalOpen(true) }}
          >
            添加网站
          </Button>
        </div>
      </div>

      {/* 搜索框：按网站名定位 */}
      <div style={{ marginBottom: 16, }}>          <Input
            className="page-search-input"
            allowClear
            prefix={<SearchOutlined style={{ color: 'var(--text-muted)' }} />}
            placeholder="搜索网站名称，定位到指定网站..."
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            style={{ width: 'min(420px, 100%)', borderRadius: 10 }}
          />
      </div>

      {/* Website cards */}
      {filtered.length === 0 && websites.length > 0 ? (
        <div style={{ textAlign: 'center', padding: '60px 0', color: 'var(--text-muted)', fontSize: 14 }}>
          未找到匹配「{searchQuery}」的网站
        </div>
      ) : null}
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
          {filtered.map((site, idx) => (
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

      {/* 批量设置弹窗：作用于当前筛选结果 */}
      <Modal
        title={`批量设置（${filtered.length} 个网站）`}
        open={batchOpen}
        onOk={handleBatchUpdate}
        okText="应用"
        confirmLoading={batchSaving}
        onCancel={() => { setBatchOpen(false); setBatchActive('keep'); setBatchPush('keep') }}
        width={460}
      >
        <div style={{ marginTop: 12, display: 'flex', flexDirection: 'column', gap: 16 }}>
          <Text type="secondary" style={{ fontSize: 13 }}>
            以下设置将作用于当前{searchQuery ? `筛选结果「${searchQuery}」` : '全部网站'}（共 {filtered.length} 个）
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
        </div>
      </Modal>

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
          <Form.Item name="push_enabled" label="飞书推送" valuePropName="checked" initialValue={true}
            tooltip="监测完成后向绑定的飞书账号推送摘要/告警">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>

      {/* Import modal */}
      <Modal
        title="批量导入网站"
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
            description="支持 xlsx / xls / csv 格式；列名必须为：网站名称、网站URL。重复 URL 会自动跳过。"
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
