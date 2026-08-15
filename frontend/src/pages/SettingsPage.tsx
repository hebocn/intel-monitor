import { useState, useEffect, useCallback } from 'react'
import { Input, Button, Typography, message, Tag, Alert, Radio, Tooltip, Skeleton } from 'antd'
import {
  SaveOutlined, SyncOutlined, ClockCircleOutlined,
  CheckCircleOutlined, CloseCircleOutlined, ApiOutlined,
  KeyOutlined, StarFilled, ScheduleOutlined, MessageOutlined,
} from '@ant-design/icons'
import { scheduleAPI, settingsAPI, feishuAPI } from '../services/api'

const { Text } = Typography

const aiProviders = [
  { key: 'minimax', label: 'MiniMax', color: '#A78BFA', desc: 'MiniMax-M2.7 · 多模态' },
  { key: 'deepseek', label: 'DeepSeek', color: '#3B82F6', desc: 'deepseek-chat · 推理能力强' },
  { key: 'mimo', label: 'MiMo', color: '#e11d48', desc: 'MiMo-V2.5-Pro · 小米大模型' },
  { key: 'lmstudio', label: 'LM Studio', color: '#10b981', desc: '本地模型 · minicpm-v-4.6-thinking · 视觉多模态' },
]

// Service providers — API key only, not LLM models
const serviceProviders = [
  { key: 'firecrawl', label: 'Firecrawl', color: '#F59E0B', desc: 'Web 搜索 + 全文抓取 · 开源情报核心引擎' },
  { key: 'tavily', label: 'Tavily', color: '#0891b2', desc: 'AI 驱动 Web 搜索 · 深度内容提取' },
  { key: 'youtube', label: 'YouTube', color: '#FF0000', desc: 'YouTube Data API v3 · 关键词搜索 + 视频元数据' },
  { key: 'google_cse', label: 'Google CSE', color: '#4285F4', desc: 'Facebook 搜索 · Google 自定义搜索引擎 ID' },
]

// All providers for backward compat in status loading
const providers = [...aiProviders, ...serviceProviders]

interface ProviderState {
  hasKey: boolean
  maskedKey: string
  model: string
  modelSaving: boolean
  saving: boolean
  testing: boolean
  apiKey: string
  testResult: { success: boolean; message: string; reply?: string } | null
}

function ProviderCard({
  provider,
  state,
  active,
  onStateChange,
  onSetActive,
  onModelSave,
  hideModel = false,
  hideActive = false,
}: {
  provider: typeof providers[number]
  state: ProviderState
  active: boolean
  onStateChange: (s: Partial<ProviderState>) => void
  onSetActive: (() => void) | undefined
  onModelSave: (model: string) => Promise<void>
  hideModel?: boolean
  hideActive?: boolean
}) {
  const handleSave = async () => {
    if (!state.apiKey.trim()) {
      message.warning('请输入 API Key')
      return
    }
    onStateChange({ saving: true, testResult: null })
    try {
      const res = await settingsAPI.saveProvider(provider.key, state.apiKey.trim())
      message.success(`${provider.label} API Key 已保存`)
      onStateChange({ hasKey: true, maskedKey: res.data.masked_key, apiKey: '' })

      onStateChange({ testing: true })
      try {
        const testRes = await settingsAPI.testSaved(provider.key)
        const d = testRes.data
        onStateChange({
          testResult: { success: d.success, message: d.message, reply: d.reply },
          testing: false,
          saving: false,
        })
        if (d.success) message.success(`${provider.label} 验证通过`)
        else message.warning(d.message)
      } catch {
        onStateChange({ testResult: { success: false, message: '测试请求失败' }, testing: false, saving: false })
      }
    } catch (err: any) {
      message.error(err.response?.data?.detail || '保存失败')
      onStateChange({ saving: false })
    }
  }

  const handleTestSaved = async () => {
    onStateChange({ testing: true, testResult: null })
    try {
      const res = await settingsAPI.testSaved(provider.key)
      const d = res.data
      onStateChange({ testResult: { success: d.success, message: d.message, reply: d.reply }, testing: false })
      if (d.success) message.success(`${provider.label} 验证通过`)
      else message.error(d.message)
    } catch (err: any) {
      const detail = err.response?.data?.detail || '测试失败'
      onStateChange({ testResult: { success: false, message: detail }, testing: false })
    }
  }

  return (
    <div style={{
      background: 'var(--surface-0, #fff)',
      borderRadius: 16,
      border: active ? `2px solid ${provider.color}` : '1px solid var(--border)',
      overflow: 'hidden',
      transition: 'all 0.2s ease',
      position: 'relative',
    }}>
      {/* Left accent bar */}
      <div style={{
        position: 'absolute', left: 0, top: 0, bottom: 0, width: 4,
        background: `linear-gradient(180deg, ${provider.color}, ${provider.color}88)`,
        borderRadius: '4px 0 0 4px',
      }} />

      {/* Header */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '18px 22px 14px 22px',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{
            display: 'inline-flex', alignItems: 'center', gap: 6,
            padding: '5px 14px 5px 10px',
            borderRadius: 20,
            background: `${provider.color}12`,
            border: `1px solid ${provider.color}20`,
          }}>
            <ApiOutlined style={{ color: provider.color, fontSize: 12 }} />
            <Text style={{ color: provider.color, fontSize: 12, fontWeight: 700, fontFamily: 'var(--font-body)' }}>
              {provider.label}
            </Text>
          </div>
          <Text style={{ color: 'var(--text-muted)', fontSize: 12 }}>{provider.desc}</Text>
          {state.hasKey && (
            <div style={{
              display: 'inline-flex', alignItems: 'center', gap: 4,
              padding: '2px 10px', borderRadius: 10,
              background: 'rgba(34,197,94,0.08)',
              color: '#22C55E', fontSize: 11, fontWeight: 600,
            }}>
              <CheckCircleOutlined />
              已配置
            </div>
          )}
          {!hideActive && active && (
            <div style={{
              display: 'inline-flex', alignItems: 'center', gap: 4,
              padding: '2px 10px', borderRadius: 10,
              background: `${provider.color}10`,
              color: provider.color, fontSize: 11, fontWeight: 600,
            }}>
              <StarFilled />
              当前使用
            </div>
          )}
        </div>
        {!hideActive && !active && state.hasKey && onSetActive && (
          <Tooltip title={`切换到 ${provider.label} 作为默认 AI 提供商`}>
            <Button size="small" onClick={onSetActive} style={{ color: provider.color, borderColor: provider.color }}>
              设为默认
            </Button>
          </Tooltip>
        )}
      </div>

      {/* Body */}
      <div style={{ padding: '0 22px 20px 22px' }}>
        {state.hasKey && (
          <div style={{
            padding: '12px 16px',
            background: 'var(--surface-1)',
            borderRadius: 12,
            border: '1px solid var(--border)',
            marginBottom: 12,
            display: 'flex', alignItems: 'center', gap: 10,
          }}>
            <KeyOutlined style={{ color: 'var(--text-muted)' }} />
            <Text style={{ color: 'var(--text-secondary)', fontSize: 13, fontFamily: 'var(--font-mono)' }}>
              当前密钥: {state.maskedKey}
            </Text>
          </div>
        )}

        {!hideModel && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 10,
          marginBottom: 14,
          padding: '8px 14px',
          background: 'var(--surface-1)',
          borderRadius: 10,
          border: '1px solid var(--border)',
        }}>
          <Text style={{
            color: 'var(--text-muted)', fontSize: 12, whiteSpace: 'nowrap',
            fontFamily: 'var(--font-body)',
          }}>
            模型名称
          </Text>
          <Input
            value={state.model}
            onChange={e => onStateChange({ model: e.target.value })}
            size="small"
            style={{ flex: 1, fontSize: 13 }}
            placeholder={provider.desc.split('·')[0].trim()}
          />
          <Button
            size="small"
            type="primary"
            loading={state.modelSaving}
            onClick={async () => {
              if (!state.model.trim()) return
              onStateChange({ modelSaving: true })
              try {
                await onModelSave(state.model.trim())
                message.success(`${provider.label} 模型名已保存`)
              } catch {
                message.error('保存失败')
              } finally {
                onStateChange({ modelSaving: false })
              }
            }}
            style={{ minWidth: 60, background: provider.color, borderColor: provider.color }}
          >
            保存
          </Button>
        </div>
        )}

        <div style={{ display: 'flex', gap: 12, marginBottom: 18 }}>
          <Input.Password
            value={state.apiKey}
            onChange={e => onStateChange({ apiKey: e.target.value })}
            placeholder={state.hasKey ? '输入新的 API Key 以替换' : `输入 ${provider.label} API Key`}
            prefix={<KeyOutlined style={{ color: 'var(--text-muted)' }} />}
            style={{ flex: 1 }}
            onPressEnter={handleSave}
          />
          <Button
            type="primary"
            icon={<SaveOutlined />}
            onClick={handleSave}
            loading={state.saving}
            style={{ minWidth: 120, background: provider.color, borderColor: provider.color }}
          >
            保存并测试
          </Button>
          {state.hasKey && (
            <Button
              icon={<ApiOutlined />}
              onClick={handleTestSaved}
              loading={state.testing}
              style={{ minWidth: 100 }}
            >
              测试连接
            </Button>
          )}
        </div>

        {state.testResult && (
          <Alert
            type={state.testResult.success ? 'success' : 'error'}
            showIcon
            icon={state.testResult.success ? <CheckCircleOutlined /> : <CloseCircleOutlined />}
            message={
              <span style={{ fontWeight: 600 }}>
                {state.testResult.success ? '验证成功' : '验证失败'}
              </span>
            }
            description={
              <div>
                <Text style={{ color: state.testResult.success ? '#22C55E' : '#c75050', fontSize: 14 }}>
                  {state.testResult.message}
                </Text>
                {state.testResult.reply && (
                  <div style={{ marginTop: 10 }}>
                    <Text style={{ color: 'var(--text-muted)', fontSize: 13 }}>模型回复: </Text>
                    <Text style={{ color: 'var(--text-primary)', fontFamily: 'var(--font-mono)', fontSize: 13 }}>
                      "{state.testResult.reply}"
                    </Text>
                  </div>
                )}
              </div>
            }
            style={{
              background: state.testResult.success ? 'rgba(34,197,94,0.04)' : 'rgba(199,80,80,0.04)',
              border: `1px solid ${state.testResult.success ? 'rgba(34,197,94,0.12)' : 'rgba(199,80,80,0.12)'}`,
              borderRadius: 12,
            }}
          />
        )}

        {!state.hasKey && !state.testResult && (
          <Text style={{ color: 'var(--text-muted)', fontSize: 13 }}>
            配置后将自动验证 API Key 是否可用。
          </Text>
        )}
      </div>
    </div>
  )
}

export default function SettingsPage() {
  const [jobs, setJobs] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [activeProvider, setActiveProvider] = useState('minimax')
  const [prompts, setPrompts] = useState({
    summarize_posts: '', summarize_website: '',
    summarize_posts_default: '', summarize_website_default: '',
    intelligence_report: '', intelligence_report_default: '',
  })
  const [promptSaving, setPromptSaving] = useState(false)
  const [feishuStatus, setFeishuStatus] = useState<{
    configured: boolean; bound: boolean; push_enabled: boolean;
    app_secret_set: boolean; app_id: string;
  } | null>(null)
  const [bindCode, setBindCode] = useState<string | null>(null)
  const [bindCodeLoading, setBindCodeLoading] = useState(false)
  const [feishuSecret, setFeishuSecret] = useState('')
  const [feishuAppId, setFeishuAppId] = useState('')
  const [secretSaving, setSecretSaving] = useState(false)

  const defaultState: ProviderState = {
    hasKey: false, maskedKey: '', model: '', modelSaving: false,
    saving: false, testing: false, apiKey: '', testResult: null,
  }
  const [providerStates, setProviderStates] = useState<Record<string, ProviderState>>({
    minimax: { ...defaultState },
    deepseek: { ...defaultState },
    mimo: { ...defaultState },
    lmstudio: { ...defaultState },
    firecrawl: { ...defaultState },
    tavily: { ...defaultState },
    youtube: { ...defaultState },
    google_cse: { ...defaultState },
  })

  const updateProvider = useCallback((key: string, patch: Partial<ProviderState>) => {
    setProviderStates(prev => ({ ...prev, [key]: { ...prev[key], ...patch } }))
  }, [])

  const fetchJobs = async () => {
    try {
      const res = await scheduleAPI.status()
      setJobs(res.data.jobs)
    } catch {}
  }

  const fetchAllProviderStatus = async () => {
    for (const p of providers) {
      try {
        const res = await settingsAPI.getProvider(p.key)
        const d = res.data
        updateProvider(p.key, { hasKey: d.has_key, maskedKey: d.masked_key, model: d.model || '' })
      } catch {}
    }
  }

  const fetchActiveProvider = async () => {
    try {
      const res = await settingsAPI.getActiveProvider()
      setActiveProvider(res.data.provider)
    } catch {}
  }

  const fetchPrompts = async () => {
    try {
      const res = await settingsAPI.getPrompts()
      setPrompts(res.data)
    } catch {}
  }

  const fetchFeishuStatus = async () => {
    try {
      const res = await feishuAPI.status()
      setFeishuStatus(res.data)
    } catch {}
  }

  useEffect(() => {
    fetchJobs()
    fetchAllProviderStatus()
    fetchActiveProvider()
    fetchPrompts()
    fetchFeishuStatus()
  }, [])

  const handleSaveSecret = async () => {
    if (!feishuSecret.trim()) {
      message.warning('请输入 App Secret')
      return
    }
    setSecretSaving(true)
    try {
      const res = await feishuAPI.saveConfig({
        app_secret: feishuSecret.trim(),
        app_id: feishuAppId.trim() || undefined,
      })
      setFeishuSecret('')
      setFeishuAppId('')
      setFeishuStatus(prev => prev ? {
        ...prev,
        configured: res.data.configured,
        app_secret_set: true,
        app_id: feishuAppId.trim() || prev.app_id,
      } : prev)
      if (res.data.reloading) {
        message.info('配置已保存，后端将自动重启生效（约 5 秒），期间页面可能短暂无响应')
      } else {
        message.success('配置已保存')
      }
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '保存失败')
    } finally {
      setSecretSaving(false)
    }
  }

  const handleGenerateBindCode = async () => {
    setBindCodeLoading(true)
    try {
      const res = await feishuAPI.bindCode()
      setBindCode(res.data.code)
      message.success('绑定码已生成，15 分钟内有效')
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '生成绑定码失败')
    } finally {
      setBindCodeLoading(false)
    }
  }

  const handleUnbind = async () => {
    try {
      await feishuAPI.unbind()
      setBindCode(null)
      setFeishuStatus(prev => prev ? { ...prev, bound: false } : prev)
      message.success('已解绑飞书')
    } catch {
      message.error('解绑失败')
    }
  }

  const handleModelSave = async (provider: string, model: string) => {
    await settingsAPI.setProviderModel(provider, model)
  }

  const handleSavePrompts = async () => {
    setPromptSaving(true)
    try {
      await settingsAPI.setPrompts({
        summarize_posts: prompts.summarize_posts,
        summarize_website: prompts.summarize_website,
        intelligence_report: prompts.intelligence_report,
      })
      message.success('提示词已保存')
    } catch {
      message.error('保存失败')
    } finally {
      setPromptSaving(false)
    }
  }

  const handleRefresh = async () => {
    setLoading(true)
    try {
      await scheduleAPI.refresh()
      message.success('调度已刷新')
      fetchJobs()
    } catch {
      message.error('刷新失败')
    } finally {
      setLoading(false)
    }
  }

  const handleSetActive = async (provider: string) => {
    try {
      const res = await settingsAPI.setActiveProvider(provider)
      setActiveProvider(provider)
      message.success(res.data.message)
      window.dispatchEvent(new Event('ai-provider-changed'))
    } catch (err: any) {
      message.error(err.response?.data?.detail || '切换失败')
    }
  }

  // Group scheduler jobs
  const grouped: Record<string, any[]> = {}
  for (const job of jobs) {
    const match = job.id.match(/^(target|website)_(\d+)/)
    const key = match ? `${match[1]}_${match[2]}` : job.id
    if (!grouped[key]) grouped[key] = []
    grouped[key].push(job)
  }
  const jobEntries = Object.entries(grouped)

  return (
    <div>
      <div style={{ marginBottom: 28 }}>
        <h1 className="page-title animate-fade-in-up">系统设置</h1>
        <div className="page-subtitle animate-fade-in-up" style={{ animationDelay: '0.05s' }}>SETTINGS · AI 模型与调度配置</div>
      </div>

      {/* Active provider selector */}
      <div className="animate-fade-in-up" style={{ marginBottom: 24, animationDelay: '0.1s' }}>
        <div style={{
          background: 'var(--surface-0, #fff)',
          borderRadius: 16,
          border: '1px solid var(--border)',
          overflow: 'hidden',
          position: 'relative',
        }}>
          <div style={{
            position: 'absolute', left: 0, top: 0, bottom: 0, width: 4,
            background: 'linear-gradient(180deg, #0f766e, #0f766e88)',
            borderRadius: '4px 0 0 4px',
          }} />
          <div style={{
            display: 'flex', alignItems: 'center', gap: 8,
            padding: '18px 22px 14px 22px',
          }}>
            <div style={{
              display: 'inline-flex', alignItems: 'center', gap: 6,
              padding: '5px 14px 5px 10px',
              borderRadius: 20,
              background: 'rgba(15,118,110,0.08)',
              border: '1px solid rgba(15,118,110,0.15)',
            }}>
              <StarFilled style={{ color: '#0f766e', fontSize: 12 }} />
              <Text style={{ color: '#0f766e', fontSize: 12, fontWeight: 700, fontFamily: 'var(--font-body)' }}>
                默认 AI 模型
              </Text>
            </div>
            <Text style={{ color: 'var(--text-muted)', fontSize: 13 }}>
              选择用于内容总结的 AI 提供商
            </Text>
          </div>
          <div style={{ padding: '0 22px 20px 22px' }}>
            <Radio.Group
              value={activeProvider}
              onChange={e => handleSetActive(e.target.value)}
              style={{ display: 'flex', gap: 12 }}
            >
              {aiProviders.map(p => (
                <Radio.Button
                  key={p.key}
                  value={p.key}
                  style={{
                    minWidth: 140,
                    textAlign: 'center',
                    borderColor: activeProvider === p.key ? p.color : undefined,
                    color: activeProvider === p.key ? p.color : undefined,
                    borderRadius: 10,
                  }}
                >
                  {p.label}
                </Radio.Button>
              ))}
            </Radio.Group>
          </div>
        </div>
      </div>

      {/* AI Provider config cards */}
      {aiProviders.map((p, i) => (
        <div key={p.key} className={`animate-fade-in-up delay-${i + 1}`} style={{ marginBottom: 16 }}>
          <ProviderCard
            provider={p}
            state={providerStates[p.key]}
            active={activeProvider === p.key}
            onStateChange={patch => updateProvider(p.key, patch)}
            onSetActive={() => handleSetActive(p.key)}
            onModelSave={async (model) => handleModelSave(p.key, model)}
          />
        </div>
      ))}

      {/* Service Provider cards (Firecrawl etc.) — API key only, no model/active */}
      {serviceProviders.map((p, i) => (
        <div key={p.key} className={`animate-fade-in-up delay-${i + 1}`} style={{ marginBottom: 16 }}>
          <ProviderCard
            provider={p}
            state={providerStates[p.key]}
            active={false}
            onStateChange={patch => updateProvider(p.key, patch)}
            onSetActive={undefined}
            onModelSave={async () => {}}
            hideModel={true}
            hideActive={true}
          />
        </div>
      ))}

      {/* AI 分析提示词 */}
      <div className="animate-fade-in-up" style={{ marginBottom: 16, animationDelay: '0.25s' }}>
        <div style={{
          background: 'var(--surface-0, #fff)',
          borderRadius: 16,
          border: '1px solid var(--border)',
          overflow: 'hidden',
          position: 'relative',
        }}>
          <div style={{
            position: 'absolute', left: 0, top: 0, bottom: 0, width: 4,
            background: 'linear-gradient(180deg, #0f766e, #0f766e88)',
            borderRadius: '4px 0 0 4px',
          }} />
          <div style={{
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            padding: '18px 22px 14px 22px',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <div style={{
                display: 'inline-flex', alignItems: 'center', gap: 6,
                padding: '5px 14px 5px 10px',
                borderRadius: 20,
                background: 'rgba(15,118,110,0.08)',
                border: '1px solid rgba(15,118,110,0.15)',
              }}>
                <span style={{ fontSize: 13 }}>📝</span>
                <Text style={{ color: '#0f766e', fontSize: 12, fontWeight: 700, fontFamily: 'var(--font-body)' }}>
                  AI 分析提示词
                </Text>
              </div>
              <Text style={{ color: 'var(--text-muted)', fontSize: 13 }}>
                自定义 AI 摘要的系统提示词，为空则使用默认
              </Text>
            </div>
            <Button
              type="primary"
              loading={promptSaving}
              onClick={handleSavePrompts}
              size="small"
              style={{ borderRadius: 8 }}
            >
              保存提示词
            </Button>
          </div>
          <div style={{ padding: '0 22px 20px 22px', display: 'flex', flexDirection: 'column', gap: 16 }}>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                <Text style={{ color: 'var(--text-primary)', fontSize: 13, fontWeight: 600 }}>贴文分析</Text>
                <Tag style={{ fontSize: 10, lineHeight: '16px' }}>POSTS</Tag>
                <Button
                  type="link"
                  size="small"
                  style={{ padding: 0, fontSize: 11, height: 'auto' }}
                  onClick={() => {
                    const newVal = prompts.summarize_posts === prompts.summarize_posts_default
                      ? '' : prompts.summarize_posts_default
                    setPrompts(prev => ({ ...prev, summarize_posts: newVal }))
                  }}
                >
                  {prompts.summarize_posts === prompts.summarize_posts_default ? '清空（使用默认）' : '恢复默认'}
                </Button>
              </div>
              <Input.TextArea
                value={prompts.summarize_posts}
                onChange={e => setPrompts(prev => ({ ...prev, summarize_posts: e.target.value }))}
                placeholder={prompts.summarize_posts_default}
                rows={4}
                style={{ fontSize: 13, fontFamily: 'var(--font-body)' }}
              />
            </div>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                <Text style={{ color: 'var(--text-primary)', fontSize: 13, fontWeight: 600 }}>网站分析</Text>
                <Tag style={{ fontSize: 10, lineHeight: '16px' }}>WEBSITES</Tag>
                <Button
                  type="link"
                  size="small"
                  style={{ padding: 0, fontSize: 11, height: 'auto' }}
                  onClick={() => {
                    const newVal = prompts.summarize_website === prompts.summarize_website_default
                      ? '' : prompts.summarize_website_default
                    setPrompts(prev => ({ ...prev, summarize_website: newVal }))
                  }}
                >
                  {prompts.summarize_website === prompts.summarize_website_default ? '清空（使用默认）' : '恢复默认'}
                </Button>
              </div>
              <Input.TextArea
                value={prompts.summarize_website}
                onChange={e => setPrompts(prev => ({ ...prev, summarize_website: e.target.value }))}
                placeholder={prompts.summarize_website_default}
                rows={3}
                style={{ fontSize: 13, fontFamily: 'var(--font-body)' }}
              />
            </div>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                <Text style={{ color: 'var(--text-primary)', fontSize: 13, fontWeight: 600 }}>情报报告</Text>
                <Tag color="#d97706" style={{ fontSize: 10, lineHeight: '16px' }}>INTELLIGENCE</Tag>
                <Button
                  type="link"
                  size="small"
                  style={{ padding: 0, fontSize: 11, height: 'auto' }}
                  onClick={() => {
                    const newVal = prompts.intelligence_report === prompts.intelligence_report_default
                      ? '' : prompts.intelligence_report_default
                    setPrompts(prev => ({ ...prev, intelligence_report: newVal }))
                  }}
                >
                  {prompts.intelligence_report === prompts.intelligence_report_default ? '清空（使用默认）' : '恢复默认'}
                </Button>
              </div>
              <Input.TextArea
                value={prompts.intelligence_report}
                onChange={e => setPrompts(prev => ({ ...prev, intelligence_report: e.target.value }))}
                placeholder={prompts.intelligence_report_default}
                rows={6}
                style={{ fontSize: 13, fontFamily: 'var(--font-body)' }}
              />
            </div>
          </div>
        </div>
      </div>

      {/* Feishu push */}
      <div className="animate-fade-in-up" style={{ animationDelay: '0.3s' }}>
        <div style={{
          background: 'var(--surface-0, #fff)',
          borderRadius: 16,
          border: '1px solid var(--border)',
          overflow: 'hidden',
          position: 'relative',
        }}>
          <div style={{
            position: 'absolute', left: 0, top: 0, bottom: 0, width: 4,
            background: 'linear-gradient(180deg, #3370ff, #3370ff88)',
            borderRadius: '4px 0 0 4px',
          }} />
          <div style={{
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            padding: '18px 22px 14px 22px',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <div style={{
                display: 'inline-flex', alignItems: 'center', gap: 6,
                padding: '5px 14px 5px 10px',
                borderRadius: 20,
                background: 'rgba(51,112,255,0.08)',
                border: '1px solid rgba(51,112,255,0.15)',
              }}>
                <MessageOutlined style={{ color: '#3370ff', fontSize: 12 }} />
                <Text style={{ color: '#3370ff', fontSize: 12, fontWeight: 700, fontFamily: 'var(--font-body)' }}>
                  飞书推送
                </Text>
              </div>
              <Text style={{ color: 'var(--text-muted)', fontSize: 13 }}>
                移动端监测 · 机器人推送 + 指令查询
              </Text>
            </div>
            <Tag color={feishuStatus?.configured ? 'green' : 'default'} style={{ marginRight: 0 }}>
              {feishuStatus?.configured ? '已配置' : '未配置'}
            </Tag>
          </div>
          <div style={{ padding: '0 22px 20px 22px', display: 'flex', flexDirection: 'column', gap: 14 }}>
            {/* App ID 配置 */}
            <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
              <Input
                placeholder={feishuStatus?.app_id ? `App ID: ${feishuStatus.app_id}（输入新值可修改）` : '输入飞书 App ID（如 cli_xxx）'}
                value={feishuAppId}
                onChange={e => setFeishuAppId(e.target.value)}
                style={{ flex: 1 }}
              />
            </div>
            {/* App Secret 配置 */}
            <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
              <Input.Password
                placeholder={feishuStatus?.app_secret_set ? '已设置 App Secret（输入新值可修改）' : '输入飞书 App Secret'}
                value={feishuSecret}
                onChange={e => setFeishuSecret(e.target.value)}
                style={{ flex: 1 }}
              />
              <Button type="primary" loading={secretSaving} onClick={handleSaveSecret}>保存</Button>
            </div>
            {!feishuStatus?.configured ? (
              <Alert
                type="warning"
                showIcon
                message="飞书机器人未配置"
                description="请在上方输入 App Secret 并保存；保存后后端会自动重启生效。"
                className="feishu-alert-warning"
                />
            ) : feishuStatus.bound ? (
              <>
                <Alert
                  type="success"
                  showIcon
                  message={`已绑定飞书账号，推送${feishuStatus.push_enabled ? '已开启' : '已暂停'}`}
                  description="在飞书中向机器人发送 /帮助 查看指令；/暂停 与 /恢复 控制全局推送开关。"
                  className="feishu-alert-success"
                />
                <div style={{ display: 'flex', gap: 10 }}>
                  <Button icon={<MessageOutlined />} onClick={handleGenerateBindCode} loading={bindCodeLoading}>
                    重新生成绑定码
                  </Button>
                  <Button danger onClick={handleUnbind}>解绑</Button>
                </div>
              </>
            ) : (
              <>
                <Alert
                  type="info"
                  showIcon
                  message="尚未绑定飞书"
                  description="点击下方按钮生成绑定码，然后在飞书中向机器人发送 /绑定 <验证码> 完成关联。"
                  className="feishu-alert-info"
                />
                <div>
                  <Button type="primary" icon={<MessageOutlined />} onClick={handleGenerateBindCode} loading={bindCodeLoading}>
                    生成绑定码
                  </Button>
                </div>
              </>
            )}
            {bindCode && (
              <div style={{
                background: 'var(--surface-1)',
                padding: '14px 18px', borderRadius: 12,
                border: '1px solid var(--border)',
              }}>
                <Text style={{ color: 'var(--text-muted)', fontSize: 12 }}>绑定码（15 分钟内有效）</Text>
                <div style={{ marginTop: 4, marginBottom: 4 }}>
                  <Text copyable style={{ fontFamily: 'var(--font-mono)', fontSize: 22, fontWeight: 700, color: '#3370ff', letterSpacing: 2 }}>
                    {bindCode}
                  </Text>
                </div>
                <Text style={{ color: 'var(--text-muted)', fontSize: 12 }}>在飞书中向机器人发送：/绑定 {bindCode}</Text>
              </div>
            )}
          </div>
        </div>


      {/* Scheduler */}
      <div className="animate-fade-in-up" style={{ animationDelay: '0.35s' }}>
        <div style={{
          background: 'var(--surface-0, #fff)',
          borderRadius: 16,
          border: '1px solid var(--border)',
          overflow: 'hidden',
          position: 'relative',
        }}>
          <div style={{
            position: 'absolute', left: 0, top: 0, bottom: 0, width: 4,
            background: 'linear-gradient(180deg, #0f766e, #0f766e88)',
            borderRadius: '4px 0 0 4px',
          }} />

          {/* Scheduler header */}
          <div style={{
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            padding: '18px 22px 14px 22px',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <div style={{
                display: 'inline-flex', alignItems: 'center', gap: 6,
                padding: '5px 14px 5px 10px',
                borderRadius: 20,
                background: 'rgba(15,118,110,0.08)',
                border: '1px solid rgba(15,118,110,0.15)',
              }}>
                <ScheduleOutlined style={{ color: '#0f766e', fontSize: 12 }} />
                <Text style={{ color: '#0f766e', fontSize: 12, fontWeight: 700, fontFamily: 'var(--font-body)' }}>
                  调度任务
                </Text>
              </div>
              <div style={{
                display: 'inline-flex', alignItems: 'center', gap: 4,
                padding: '2px 10px', borderRadius: 10,
                background: 'var(--surface-1)',
                color: 'var(--text-muted)', fontSize: 11, fontWeight: 600,
                border: '1px solid var(--border)',
              }}>
                {jobs.length} 个任务
              </div>
            </div>
            <Button
              type="primary"
              icon={<SyncOutlined />}
              onClick={handleRefresh}
              loading={loading}
              size="small"
              style={{ borderRadius: 8 }}
            >
              刷新调度
            </Button>
          </div>

          {/* Scheduler body */}
          <div style={{ padding: '0 22px 20px 22px' }}>
            {jobEntries.length === 0 ? (
              <div style={{
                textAlign: 'center', padding: '40px 0',
                color: 'var(--text-muted)', fontSize: 14,
              }}>
                暂无调度任务
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                {jobEntries.map(([groupKey, groupJobs]) => (
                  <div key={groupKey} style={{
                    background: 'var(--surface-1)',
                    padding: '16px 20px',
                    borderRadius: 12,
                    border: '1px solid var(--border)',
                  }}>
                    <Text style={{
                      color: 'var(--text-primary)', fontWeight: 700, fontSize: 14,
                      marginBottom: 10, display: 'block',
                    }}>
                      {groupJobs[0]?.target_name || groupKey}
                    </Text>
                    {groupJobs.map((job: any, idx: number) => (
                      <div key={idx} style={{
                        display: 'flex', alignItems: 'center', gap: 16,
                        marginBottom: idx < groupJobs.length - 1 ? 8 : 0,
                      }}>
                        <div style={{
                          display: 'inline-flex', alignItems: 'center', gap: 6,
                          padding: '2px 10px', borderRadius: 8,
                          background: 'rgba(15,118,110,0.06)',
                          border: '1px solid rgba(15,118,110,0.1)',
                        }}>
                          <ClockCircleOutlined style={{ color: '#0f766e', fontSize: 11 }} />
                          <Text style={{ color: '#0f766e', fontFamily: 'var(--font-mono)', fontSize: 12, fontWeight: 600 }}>
                            {job.trigger}
                          </Text>
                        </div>
                        <Text style={{ color: 'var(--text-secondary)', fontSize: 13 }}>
                          下次: <span style={{ color: 'var(--accent)', fontFamily: 'var(--font-mono)', fontWeight: 600 }}>
                            {job.next_run || '未安排'}
                          </span>
                        </Text>
                      </div>
                    ))}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      </div>
    </div>
  )
}
