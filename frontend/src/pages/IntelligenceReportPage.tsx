import { useEffect, useState, useRef } from 'react'
import {
  Input, Button, Card, Tag, Space, Select, Layout, message, Spin, Empty,
  Typography, Row, Col, Modal, TreeSelect, Pagination, Tooltip, Divider,
  Descriptions, Steps, Alert,
} from 'antd'
import {
  FileTextOutlined, SearchOutlined, DownloadOutlined, DeleteOutlined,
  ReloadOutlined, ExportOutlined, EyeOutlined, PlusOutlined,
  SettingOutlined, ClockCircleOutlined, CheckCircleOutlined,
  SyncOutlined, CloseCircleOutlined, GlobalOutlined, MobileOutlined,
  ExperimentOutlined, FilePdfOutlined, FileWordOutlined, CopyOutlined,
} from '@ant-design/icons'
import { intelligenceAPI } from '../services/api'

const { TextArea } = Input
const { Text, Title, Paragraph } = Typography

// ── Types ──────────────────────────────────────────────────────────────────
interface CategoryNode {
  id: number; name: string; level: number; sort_order: number; children: CategoryNode[]
}
interface ReportProgress {
  id: number; status: string; title: string; topic: string
  category_id: number | null; progress_detail: string | null
  error_log: string | null; created_at: string; completed_at: string | null
}
interface ReportDetail extends ReportProgress {
  search_queries: string | null; search_platforms: string | null
  report_markdown: string | null; sources_json: string | null
}
interface ReportListItem {
  id: number; title: string; status: string; category_id: number | null
  created_at: string; completed_at: string | null
}

// ── Constants ──────────────────────────────────────────────────────────────
const STATUS_MAP: Record<string, { color: string; icon: any; text: string }> = {
  pending:   { color: '#f59e0b', icon: <ClockCircleOutlined />,    text: '排队中' },
  searching: { color: '#60A5FA', icon: <SearchOutlined />,         text: '搜索中' },
  scraping:  { color: '#A78BFA', icon: <GlobalOutlined />,         text: '抓取中' },
  analyzing: { color: '#F472B6', icon: <ExperimentOutlined />,     text: '分析中' },
  writing:   { color: '#F59E0B', icon: <SyncOutlined spin />,      text: '撰写中' },
  reviewing: { color: '#2DD4BF', icon: <SyncOutlined spin />,      text: '润色中' },
  completed: { color: '#10b981', icon: <CheckCircleOutlined />,    text: '已完成' },
  failed:    { color: '#ef4444', icon: <CloseCircleOutlined />,    text: '失败' },
}

const R = { sm: 8, md: 12, lg: 16, xl: 20 }

const fmtDt = (iso: string | null): string => {
  if (!iso) return ''
  const d = iso.endsWith('Z') || iso.includes('+') ? new Date(iso) : new Date(iso + 'Z')
  return d.toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Shanghai' })
}

// ── Styles ─────────────────────────────────────────────────────────────────
const sectionStyle: React.CSSProperties = {
  background: 'var(--surface-2)', borderRadius: R.lg, padding: 24, marginBottom: 16,
  border: '1px solid rgba(15,118,110,0.08)',
}

// ── Main Component ─────────────────────────────────────────────────────────
export default function IntelligenceReportPage() {
  // State
  const [categories, setCategories] = useState<CategoryNode[]>([])
  const [categoryId, setCategoryId] = useState<number | undefined>(undefined)
  const [topic, setTopic] = useState('')
  const [title, setTitle] = useState('')
  const [engines, setEngines] = useState<string[]>(['firecrawl'])
  const [crawlers, setCrawlers] = useState<string[]>([])
  const [maxResults, setMaxResults] = useState(10)
  const [maxSources, setMaxSources] = useState(30)
  const [reports, setReports] = useState<ReportListItem[]>([])
  const [totalReports, setTotalReports] = useState(0)
  const [page, setPage] = useState(1)
  const [selectedReport, setSelectedReport] = useState<ReportDetail | null>(null)
  const [loading, setLoading] = useState(false)
  const [reportLoading, setReportLoading] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const [activeReportId, setActiveReportId] = useState<number | null>(null)

  // Load categories
  useEffect(() => {
    intelligenceAPI.listCategories().then(r => setCategories(r.data)).catch(() => {})
  }, [])

  // Load reports
  const loadReports = () => {
    intelligenceAPI.listReports({ page, page_size: 20 }).then(r => {
      setReports(r.data.reports)
      setTotalReports(r.data.total)
    }).catch(() => {})
  }
  useEffect(() => { loadReports() }, [page])

  // Start report generation
  const handleGenerate = async () => {
    if (topic.length < 10) { message.warning('主题描述至少10个字符'); return }
    setLoading(true)
    try {
      const res = await intelligenceAPI.generate({
        topic, category_id: categoryId, title: title || undefined,
        search_engines: engines, crawl_platforms: crawlers,
        max_search_results: maxResults, max_sources: maxSources,
      })
      const { report_id } = res.data
      setActiveReportId(report_id)
      message.success('报告生成任务已启动')
      loadReports()
      // 自动打开详情弹窗,实时展示生成进度
      const detail = await intelligenceAPI.getReport(report_id)
      setSelectedReport(detail.data)
      setModalOpen(true)
      // Start polling
      startPolling(report_id)
    } catch (e: any) {
      message.error(e.response?.data?.detail || '创建失败')
    } finally {
      setLoading(false)
    }
  }

  // Poll for progress
  const startPolling = (reportId: number) => {
    if (pollRef.current) clearInterval(pollRef.current)
    pollRef.current = setInterval(async () => {
      try {
        const res = await intelligenceAPI.getReport(reportId)
        const r = res.data as ReportDetail
        setSelectedReport(r)
        // 同步刷新列表,让状态 Tag(排队/搜索/抓取/撰写…)实时更新
        loadReports()
        if (r.status === 'completed' || r.status === 'failed') {
          if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null }
          loadReports()
        }
      } catch {}
    }, 3000)
  }

  // View report
  const handleView = async (reportId: number) => {
    setReportLoading(true)
    try {
      const res = await intelligenceAPI.getReport(reportId)
      setSelectedReport(res.data)
      setModalOpen(true)
      // If still running, start polling
      if (res.data.status !== 'completed' && res.data.status !== 'failed') {
        setActiveReportId(reportId)
        startPolling(reportId)
      }
    } catch {
      message.error('加载报告失败')
    } finally {
      setReportLoading(false)
    }
  }

  // Regenerate
  const handleRegenerate = async (reportId: number) => {
    try {
      await intelligenceAPI.regenerate(reportId)
      message.success('重新生成已启动')
      setActiveReportId(reportId)
      startPolling(reportId)
    } catch (e: any) {
      message.error(e.response?.data?.detail || '重新生成失败')
    }
  }

  // Export
  const handleExport = async (reportId: number, format: 'docx' | 'pdf') => {
    try {
      const apiFn = format === 'docx' ? intelligenceAPI.exportDocx : intelligenceAPI.exportPdf
      const res = await apiFn(reportId)
      const blob = new Blob([res.data])
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${selectedReport?.title || 'report'}.${format}`
      a.click()
      URL.revokeObjectURL(url)
      message.success(`已导出 ${format.toUpperCase()}`)
    } catch {
      message.error('导出失败')
    }
  }

  // Delete
  const handleDelete = async (reportId: number) => {
    Modal.confirm({
      title: '确认删除', content: '删除后无法恢复',
      onOk: async () => {
        await intelligenceAPI.deleteReport(reportId)
        if (selectedReport?.id === reportId) setSelectedReport(null)
        loadReports()
        message.success('已删除')
      },
    })
  }

  // Copy markdown
  const handleCopy = () => {
    if (selectedReport?.report_markdown) {
      navigator.clipboard.writeText(selectedReport.report_markdown)
      message.success('已复制全文到剪贴板')
    }
  }

  // Cleanup poll
  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current) }, [])

  // ── Category tree → TreeSelect format ──
  const toTreeData = (nodes: CategoryNode[]): any[] =>
    nodes.map(n => ({
      title: n.name, value: n.id, key: n.id,
      children: n.children?.length ? toTreeData(n.children) : undefined,
    }))

  // ── Progress detail ──
  const progressData = selectedReport?.progress_detail
    ? (() => { try { return JSON.parse(selectedReport.progress_detail) } catch { return null } })()
    : null
  const statusInfo = STATUS_MAP[selectedReport?.status || 'pending'] || STATUS_MAP.pending

  return (
    <div style={{ maxWidth: 1400, margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <div>
          <Title level={3} style={{ margin: 0, color: 'var(--text-primary)' }}>
            <FileTextOutlined style={{ marginRight: 10, color: '#0f766e' }} />
            战略情报报告
          </Title>
          <Text type="secondary" style={{ fontSize: 13 }}>基于开源数据生成结构化情报分析报告 · 宗教领域战略情报攻坚战</Text>
        </div>
      </div>

      {/* ── Input Area ── */}
      <Card style={{ ...sectionStyle, marginBottom: 16 }}>
        <Row gutter={[24, 16]}>
          <Col span={24}>
            <Text strong style={{ fontSize: 14 }}>情报主题描述</Text>
            <TextArea
              rows={5}
              value={topic}
              onChange={e => setTopic(e.target.value)}
              placeholder={`详细描述情报研究主题，例如：\n围绕网络平台售卖涉宗教元素物品及书籍的风险隐患进行分析研判。淘宝、京东、抖音、小红书等网络平台是当前人们主要的购物渠道，普遍应用了大数据精准推送技术...`}
              style={{ marginTop: 8, fontSize: 14 }}
            />
          </Col>
          <Col xs={24} md={8}>
            <Text strong style={{ fontSize: 14 }}>报告标题（可选）</Text>
            <Input value={title} onChange={e => setTitle(e.target.value)} placeholder="留空则自动生成" style={{ marginTop: 8 }} />
          </Col>
          <Col xs={24} md={8}>
            <Text strong style={{ fontSize: 14 }}>情报分类</Text>
            <TreeSelect
              style={{ width: '100%', marginTop: 8 }}
              placeholder="选择分类（可选）"
              treeData={toTreeData(categories)}
              value={categoryId}
              onChange={(v) => setCategoryId(v)}
              allowClear
              treeDefaultExpandAll
            />
          </Col>
          <Col xs={24} md={8}>
            <Text strong style={{ fontSize: 14 }}>搜索平台</Text>
            <div style={{ marginTop: 8 }}>
              <Select mode="multiple" style={{ width: '100%' }} value={engines} onChange={setEngines}
                placeholder="搜索引擎">
                <Select.Option value="firecrawl">Firecrawl (Google/Bing)</Select.Option>
                <Select.Option value="tavily">Tavily (AI 搜索)</Select.Option>
              </Select>
              <Select mode="multiple" style={{ width: '100%', marginTop: 8 }} value={crawlers} onChange={setCrawlers}
                placeholder="平台爬虫（可选）">
                <Select.Option value="weibo">微博</Select.Option>
                <Select.Option value="douyin">抖音</Select.Option>
                <Select.Option value="xiaohongshu">小红书</Select.Option>
                <Select.Option value="toutiao">今日头条</Select.Option>
                <Select.Option value="108community">108天台社区</Select.Option>
                <Select.Option value="x">X (Twitter)</Select.Option>
              </Select>
            </div>
          </Col>
          <Col xs={12} md={6}>
            <Text strong style={{ fontSize: 14 }}>每查询最大结果数</Text>
            <Select value={maxResults} onChange={setMaxResults} style={{ width: '100%', marginTop: 8 }}>
              <Select.Option value={5}>5 (快速)</Select.Option>
              <Select.Option value={10}>10 (标准)</Select.Option>
              <Select.Option value={20}>20 (深度)</Select.Option>
            </Select>
          </Col>
          <Col xs={12} md={6}>
            <Text strong style={{ fontSize: 14 }}>引用来源上限</Text>
            <Select value={maxSources} onChange={setMaxSources} style={{ width: '100%', marginTop: 8 }}>
              <Select.Option value={15}>15 (精简)</Select.Option>
              <Select.Option value={30}>30 (标准)</Select.Option>
              <Select.Option value={50}>50 (全面)</Select.Option>
            </Select>
          </Col>
          <Col span={24}>
            <Button type="primary" size="large" icon={<FileTextOutlined />}
              loading={loading} onClick={handleGenerate}
              style={{ background: '#0f766e', borderColor: '#0f766e', height: 48, fontSize: 16, paddingInline: 32 }}>
              生成战略情报报告
            </Button>
          </Col>
        </Row>
      </Card>

      {/* ── Report List ── */}
      <div style={{ ...sectionStyle }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <Title level={5} style={{ margin: 0 }}>历史报告</Title>
          <Button icon={<ReloadOutlined />} onClick={loadReports} type="text">刷新</Button>
        </div>

        {reports.length === 0 ? (
          <Empty description="暂无报告，输入主题生成第一份战略情报报告" />
        ) : (
          <>
            {reports.map(r => {
              const si = STATUS_MAP[r.status] || STATUS_MAP.pending
              return (
                <div key={r.id} style={{
                  display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                  padding: '14px 16px', borderBottom: '1px solid rgba(15,118,110,0.06)',
                  borderRadius: R.md, transition: 'background 0.2s',
                  ...(r.id === selectedReport?.id ? { background: 'rgba(15,118,110,0.04)' } : {}),
                }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <Tag color={si.color} icon={si.icon} style={{ fontSize: 12 }}>{si.text}</Tag>
                      <Text strong style={{ fontSize: 15 }} ellipsis={{ tooltip: r.title }}>{r.title}</Text>
                    </div>
                    <Text type="secondary" style={{ fontSize: 12, marginTop: 4, display: 'block' }}>
                      创建 {fmtDt(r.created_at)}
                      {r.completed_at && ` · 完成 ${fmtDt(r.completed_at)}`}
                    </Text>
                  </div>
                  <Space style={{ flexShrink: 0, marginLeft: 16 }}>
                    <Tooltip title="查看"><Button icon={<EyeOutlined />} size="small" loading={reportLoading && selectedReport?.id === r.id} onClick={() => handleView(r.id)} /></Tooltip>
                    {r.status === 'completed' && (
                      <>
                        <Tooltip title="导出 Word"><Button icon={<FileWordOutlined />} size="small" onClick={() => { handleView(r.id); setTimeout(() => handleExport(r.id, 'docx'), 500) }} /></Tooltip>
                        <Tooltip title="导出 PDF"><Button icon={<FilePdfOutlined />} size="small" onClick={() => { handleView(r.id); setTimeout(() => handleExport(r.id, 'pdf'), 500) }} /></Tooltip>
                      </>
                    )}
                    {(r.status === 'failed' || r.status === 'completed') && (
                      <Tooltip title="重新生成"><Button icon={<ReloadOutlined />} size="small" onClick={() => handleRegenerate(r.id)} /></Tooltip>
                    )}
                    <Tooltip title="删除"><Button icon={<DeleteOutlined />} size="small" danger onClick={() => handleDelete(r.id)} /></Tooltip>
                  </Space>
                </div>
              )
            })}
            <div style={{ marginTop: 16, textAlign: 'right' }}>
              <Pagination current={page} total={totalReports} pageSize={20} onChange={setPage} size="small" />
            </div>
          </>
        )}
      </div>

      {/* ── Report Detail Modal ── */}
      <Modal
        open={modalOpen}
        onCancel={() => { setModalOpen(false); if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null } }}
        width={960}
        title={null}
        footer={null}
        styles={{ body: { padding: 0 } }}
      >
        {selectedReport && (
          <div style={{ padding: 24 }}>
            {/* Header */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 20 }}>
              <div style={{ flex: 1 }}>
                <Title level={4} style={{ margin: 0 }}>{selectedReport.title}</Title>
                <Space style={{ marginTop: 8 }}>
                  <Tag color={statusInfo.color} icon={statusInfo.icon}>{statusInfo.text}</Tag>
                  {selectedReport.status !== 'completed' && progressData && (
                    <Text type="secondary" style={{ fontSize: 13 }}>{progressData.message}</Text>
                  )}
                </Space>
              </div>
              <Space>
                {selectedReport.status === 'completed' && (
                  <>
                    <Button icon={<CopyOutlined />} onClick={handleCopy}>复制</Button>
                    <Button icon={<FileWordOutlined />} onClick={() => handleExport(selectedReport.id, 'docx')}>Word</Button>
                    <Button icon={<FilePdfOutlined />} onClick={() => handleExport(selectedReport.id, 'pdf')}>PDF</Button>
                  </>
                )}
                <Button icon={<ReloadOutlined />} onClick={() => handleRegenerate(selectedReport.id)}>重新生成</Button>
              </Space>
            </div>

            {/* Error log */}
            {selectedReport.status === 'failed' && selectedReport.error_log && (
              <Alert type="error" message="生成失败" description={(() => { try { return JSON.stringify(JSON.parse(selectedReport.error_log), null, 2) } catch { return selectedReport.error_log } })()} style={{ marginBottom: 16 }} />
            )}

            {/* Progress for non-completed */}
            {selectedReport.status !== 'completed' && selectedReport.status !== 'failed' && (
              <div style={{ textAlign: 'center', padding: 40 }}>
                <Spin size="large" />
                <Text style={{ display: 'block', marginTop: 16 }}>{progressData?.message || '处理中...'}</Text>
              </div>
            )}

            {/* Report content */}
            {selectedReport.status === 'completed' && selectedReport.report_markdown && (
              <div style={{
                background: 'var(--surface-1)', borderRadius: R.md, padding: 32,
                border: '1px solid var(--border)',
                maxHeight: '60vh', overflow: 'auto',
              }}>
                <ReportMarkdown content={selectedReport.report_markdown} />
              </div>
            )}

            {/* Sources summary */}
            {selectedReport.sources_json && (() => {
              try {
                const sources = JSON.parse(selectedReport.sources_json)
                return (
                  <div style={{ marginTop: 20 }}>
                    <Divider />
                    <Text strong>引用来源 ({sources.length} 条)</Text>
                    <div style={{ maxHeight: 200, overflow: 'auto', marginTop: 8 }}>
                      {sources.map((s: any, i: number) => (
                        <div key={i} style={{ marginBottom: 6, fontSize: 12 }}>
                          <Tag color={s.relevance === 'high' ? 'red' : s.relevance === 'medium' ? 'blue' : 'default'}
                            style={{ fontSize: 10 }}>{s.relevance === 'high' ? '高相关' : s.relevance === 'medium' ? '中相关' : '低相关'}</Tag>
                          <a href={s.url} target="_blank" rel="noopener noreferrer">{s.title || s.url}</a>
                          {s.source_engine && <Text type="secondary"> · {s.source_engine}</Text>}
                        </div>
                      ))}
                    </div>
                  </div>
                )
              } catch { return null }
            })()}
          </div>
        )}
      </Modal>
    </div>
  )
}

// ── Simple Markdown Render ─────────────────────────────────────────────────
function ReportMarkdown({ content }: { content: string }) {
  // Inline formatter: **bold**, *italic*, `code`
  const formatInline = (text: string): React.ReactNode[] => {
    const parts: React.ReactNode[] = []
    // Match **bold**, *italic*, `code`
    const regex = /(\*\*(.+?)\*\*|\*(.+?)\*|`(.+?)`)/g
    let last = 0
    let match: RegExpExecArray | null
    while ((match = regex.exec(text)) !== null) {
      if (match.index > last) {
        parts.push(<Text key={last}>{text.slice(last, match.index)}</Text>)
      }
      if (match[2]) {
        parts.push(<Text key={match.index} strong>{match[2]}</Text>)
      } else if (match[3]) {
        parts.push(<Text key={match.index} italic>{match[3]}</Text>)
      } else if (match[4]) {
        parts.push(<Text key={match.index} code>{match[4]}</Text>)
      }
      last = match.index + match[0].length
    }
    if (last < text.length) {
      parts.push(<Text key={last}>{text.slice(last)}</Text>)
    }
    return parts
  }

  // Render each line
  const lines = content.split('\n')
  const elements: React.ReactNode[] = []
  let i = 0
  while (i < lines.length) {
    const line = lines[i]
    const trimmed = line.trim()

    // blank
    if (!trimmed) {
      elements.push(<div key={i} style={{ height: 10 }} />)
      i++; continue
    }

    // h1: # xxx
    if (/^# (?!#)/.test(trimmed)) {
      elements.push(<Title key={i} level={3} style={{ color: 'var(--text-primary)', marginTop: 24 }}>{trimmed.replace(/^# /, '')}</Title>)
      i++; continue
    }
    // h2: ## xxx
    if (/^## (?!#)/.test(trimmed)) {
      elements.push(
        <div key={i} style={{ marginTop: 24, marginBottom: 12, paddingLeft: 12, borderLeft: '3px solid #0f766e' }}>
          <Text strong style={{ fontSize: 16, color: '#0f766e' }}>{trimmed.replace(/^## /, '')}</Text>
        </div>
      )
      i++; continue
    }
    // h3: ### xxx
    if (/^### (?!#)/.test(trimmed)) {
      elements.push(<Text key={i} strong style={{ fontSize: 15, display: 'block', marginTop: 16 }}>{trimmed.replace(/^### /, '')}</Text>)
      i++; continue
    }
    // hr
    if (trimmed === '---' || trimmed === '***') {
      elements.push(<Divider key={i} style={{ margin: '16px 0' }} />)
      i++; continue
    }
    // unordered list
    if (/^[-*]\s/.test(trimmed)) {
      elements.push(<div key={i} style={{ paddingLeft: 20 }}>· {formatInline(trimmed.replace(/^[-*]\s/, ''))}</div>)
      i++; continue
    }
    // ordered list
    if (/^\d+[.、]\s/.test(trimmed)) {
      elements.push(<div key={i} style={{ paddingLeft: 20 }}>{formatInline(trimmed.replace(/^\d+[.、]\s/, ''))}</div>)
      i++; continue
    }
    // blockquote
    if (/^>\s?/.test(trimmed)) {
      const bqLines: string[] = []
      while (i < lines.length && /^>\s?/.test(lines[i].trim())) {
        bqLines.push(lines[i].trim().replace(/^>\s?/, ''))
        i++
      }
      elements.push(
        <div key={i} style={{ borderLeft: '3px solid var(--border-strong)', paddingLeft: 14, margin: '8px 0', color: 'var(--text-muted)', fontStyle: 'italic' }}>
          {bqLines.map((bql, j) => <div key={j}>{formatInline(bql)}</div>)}
        </div>
      )
      continue
    }
    // table: | ... | ... |
    if (trimmed.startsWith('|') && trimmed.endsWith('|')) {
      const tableRows: string[][] = []
      while (i < lines.length && lines[i].trim().startsWith('|') && lines[i].trim().includes('|')) {
        const cells = lines[i].trim().split('|').filter(c => c.trim() !== '')
        tableRows.push(cells)
        i++
      }
      // Remove separator rows (|---|)
      const dataRows = tableRows.filter(r => !r.every(c => /^[-:]+$/.test(c.trim())))
      if (dataRows.length > 0) {
        elements.push(
          <div key={i} style={{ overflowX: 'auto', margin: '12px 0' }}>
            <table style={{ borderCollapse: 'collapse', width: '100%', fontSize: 13 }}>
              {dataRows.map((row, ri) => (
                <tr key={ri} style={{ borderBottom: '1px solid var(--border)' }}>
                  {row.map((cell, ci) => {
                    const CellTag = ri === 0 ? 'th' : 'td'
                    return (
                      <CellTag key={ci} style={{
                        padding: '8px 12px', textAlign: 'left',
                        background: ri === 0 ? 'rgba(15,118,110,0.06)' : undefined,
                        fontWeight: ri === 0 ? 600 : 400,
                      }}>
                        {formatInline(cell.trim())}
                      </CellTag>
                    )
                  })}
                </tr>
              ))}
            </table>
          </div>
        )
      }
      continue
    }

    // regular paragraph
    elements.push(
      <Paragraph key={i} style={{ marginBottom: 8, textIndent: '2em' }}>
        {formatInline(trimmed)}
      </Paragraph>
    )
    i++
  }

  return <div style={{ fontFamily: 'var(--font-body)', lineHeight: 1.9 }}>{elements}</div>
}
