import { useState, useEffect } from 'react'
import { Card, Form, Input, Button, Typography, Alert } from 'antd'
import { UserOutlined, LockOutlined, RadarChartOutlined } from '@ant-design/icons'
import { authAPI } from '../services/api'

const { Text } = Typography

type Mode = 'login' | 'register' | 'reset'

interface Props {
  onLogin: () => void
}

export default function LoginPage({ onLogin }: Props) {
  const [loading, setLoading] = useState(false)
  const [needsSetup, setNeedsSetup] = useState(false)
  const [checking, setChecking] = useState(true)
  const [mode, setMode] = useState<Mode>('login')
  const [errorMsg, setErrorMsg] = useState('')
  const [successMsg, setSuccessMsg] = useState('')
  const [form] = Form.useForm()

  useEffect(() => {
    authAPI.checkStatus().then(res => {
      setNeedsSetup(res.data.needs_setup)
    }).finally(() => setChecking(false))
  }, [])

  const handleSubmit = async (values: { username: string; password: string; newPassword?: string }) => {
    setLoading(true)
    setErrorMsg('')
    setSuccessMsg('')
    try {
      if (needsSetup) {
        const res = await authAPI.setup(values.username, values.password)
        localStorage.setItem('token', res.data.access_token)
        setSuccessMsg('系统初始化成功，正在进入...')
        setTimeout(onLogin, 600)
        return
      }

      if (mode === 'register') {
        const res = await authAPI.register(values.username, values.password)
        localStorage.setItem('token', res.data.access_token)
        setSuccessMsg('注册成功，正在进入...')
        setTimeout(onLogin, 600)
        return
      }

      if (mode === 'reset') {
        const loginRes = await authAPI.login(values.username, values.password)
        localStorage.setItem('token', loginRes.data.access_token)
        await authAPI.resetPassword(values.newPassword!)
        localStorage.removeItem('token')
        setSuccessMsg('密码已重置，请使用新密码重新登录')
        form.resetFields()
        setMode('login')
        return
      }

      // Login mode
      const res = await authAPI.login(values.username, values.password)
      localStorage.setItem('token', res.data.access_token)
      setSuccessMsg('登录成功，正在进入...')
      setTimeout(onLogin, 600)
    } catch (err: any) {
      const status = err.response?.status
      const detail = err.response?.data?.detail || ''

      if (!err.response) {
        setErrorMsg('网络连接失败，请检查服务是否运行')
      } else if (status === 401) {
        setErrorMsg('用户名或密码错误')
        form.setFields([
          { name: 'password', errors: ['密码不正确'] },
        ])
      } else if (status === 409) {
        setErrorMsg('用户名已存在，请更换')
        form.setFields([
          { name: 'username', errors: ['该用户名已被注册'] },
        ])
      } else if (status === 422) {
        setErrorMsg('请完整填写所有字段')
      } else {
        setErrorMsg(detail || '操作失败，请稍后重试')
      }
    } finally {
      setLoading(false)
    }
  }

  const switchMode = (m: Mode) => {
    setMode(m)
    setErrorMsg('')
    setSuccessMsg('')
    form.resetFields()
  }

  if (checking) return null

  const modeConfig: Record<Mode, { title: string; subtitle: string; btn: string }> = {
    login: { title: '情报监测智能体', subtitle: 'SYSTEM ACCESS', btn: '登录' },
    register: { title: '创建新账号', subtitle: 'REGISTER', btn: '注册' },
    reset: { title: '重置密码', subtitle: 'RESET PASSWORD', btn: '重置密码' },
  }

  const cfg = modeConfig[needsSetup ? 'login' : mode]
  const displayTitle = needsSetup ? '初始设置' : cfg.title
  const displaySubtitle = needsSetup ? 'INITIAL SETUP' : cfg.subtitle
  const displayBtn = needsSetup ? '初始化系统' : cfg.btn

  return (
    <div style={{
      minHeight: '100vh',
      background: 'var(--bg)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      position: 'relative',
      overflow: 'hidden',
    }}>
      {/* Ambient warm gradients */}
      <div style={{
        position: 'absolute', top: '15%', left: '45%',
        width: 700, height: 700,
        transform: 'translate(-50%, -50%)',
        background: 'radial-gradient(circle, rgba(45,106,79,0.06) 0%, transparent 70%)',
        pointerEvents: 'none',
      }} />
      <div style={{
        position: 'absolute', bottom: '5%', right: '15%',
        width: 500, height: 500,
        background: 'radial-gradient(circle, rgba(45,106,79,0.04) 0%, transparent 70%)',
        pointerEvents: 'none',
      }} />

      {/* Corner lines */}
      <div style={{ position: 'absolute', top: 48, left: 48, width: 60, height: 60, borderTop: '1px solid rgba(45,106,79,0.12)', borderLeft: '1px solid rgba(45,106,79,0.12)' }} />
      <div style={{ position: 'absolute', bottom: 48, right: 48, width: 60, height: 60, borderBottom: '1px solid rgba(45,106,79,0.12)', borderRight: '1px solid rgba(45,106,79,0.12)' }} />

      <Card className="animate-scale-in" style={{
        width: 460,
        background: '#ffffff',
        border: '1px solid var(--border)',
        borderRadius: 20,
        boxShadow: '0 24px 80px rgba(0,0,0,0.08), 0 8px 24px rgba(0,0,0,0.04)',
        position: 'relative',
        overflow: 'hidden',
      }}
        styles={{ body: { padding: '52px 44px 44px' } }}
      >
        {/* Top accent */}
        <div style={{
          position: 'absolute', top: 0, left: 0, right: 0, height: 3,
          background: 'linear-gradient(90deg, transparent 10%, #2d6a4f, transparent 90%)',
          opacity: 0.6,
        }} />

        {/* Logo */}
        <div style={{ textAlign: 'center', marginBottom: 28 }}>
          <div style={{
            width: 76, height: 76, borderRadius: 18,
            background: 'linear-gradient(135deg, rgba(45,106,79,0.12), rgba(45,106,79,0.04))',
            border: '1px solid rgba(45,106,79,0.15)',
            display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
            marginBottom: 20,
          }}>
            <RadarChartOutlined style={{ fontSize: 34, color: '#2d6a4f' }} />
          </div>
          <div style={{
            color: 'var(--text-primary)', fontWeight: 700,
            fontFamily: "var(--font-display)", letterSpacing: 2, fontSize: 26,
          }}>
            {displayTitle}
          </div>
          <Text style={{
            color: 'var(--text-muted)', fontSize: 12, letterSpacing: 4,
            fontFamily: "var(--font-mono)", display: 'block', marginTop: 8,
          }}>
            {displaySubtitle}
          </Text>
        </div>

        {/* Error alert */}
        {errorMsg && (
          <Alert
            type="error"
            message={errorMsg}
            showIcon
            closable
            onClose={() => setErrorMsg('')}
            style={{
              marginBottom: 16, borderRadius: 10, textAlign: 'center',
              background: 'rgba(199,80,80,0.06)',
              border: '1px solid rgba(199,80,80,0.15)',
            }}
          />
        )}

        {/* Success alert */}
        {successMsg && (
          <Alert
            type="success"
            message={successMsg}
            showIcon
            style={{
              marginBottom: 16, borderRadius: 10, textAlign: 'center',
              background: 'rgba(82,183,136,0.06)',
              border: '1px solid rgba(82,183,136,0.15)',
            }}
          />
        )}

        <Form form={form} layout="vertical" onFinish={handleSubmit}>
          <Form.Item name="username" rules={[{ required: true, message: '请输入用户名' }]}>
            <Input
              prefix={<UserOutlined style={{ color: 'var(--text-muted)' }} />}
              placeholder="用户名"
              size="large"
              onChange={() => { setErrorMsg(''); setSuccessMsg(''); }}
              style={{ height: 52, fontSize: 16, borderRadius: 12 }}
            />
          </Form.Item>
          <Form.Item name="password" rules={[{ required: true, message: '请输入密码' }]}>
            <Input.Password
              prefix={<LockOutlined style={{ color: 'var(--text-muted)' }} />}
              placeholder={mode === 'reset' ? '当前密码' : '密码'}
              size="large"
              onChange={() => { setErrorMsg(''); setSuccessMsg(''); }}
              style={{ height: 52, fontSize: 16, borderRadius: 12 }}
            />
          </Form.Item>

          {mode === 'reset' && (
            <Form.Item name="newPassword" rules={[{ required: true, message: '请输入新密码' }]}>
              <Input.Password
                prefix={<LockOutlined style={{ color: 'var(--text-muted)' }} />}
                placeholder="新密码（至少 4 位）"
                size="large"
                style={{ height: 52, fontSize: 16, borderRadius: 12 }}
              />
            </Form.Item>
          )}

          <Form.Item style={{ marginTop: 28 }}>
            <Button
              type="primary"
              htmlType="submit"
              block
              loading={loading}
              size="large"
              style={{ height: 54, fontSize: 16, fontWeight: 700, letterSpacing: 2, borderRadius: 12 }}
            >
              {displayBtn}
            </Button>
          </Form.Item>
        </Form>

        {/* Mode switch links (hidden during initial setup) */}
        {!needsSetup && (
          <div style={{ textAlign: 'center', marginTop: 8 }}>
            {mode === 'login' && (
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <Button type="link" size="small" onClick={() => switchMode('register')}
                  style={{ padding: 0, fontSize: 13, color: 'var(--text-muted)' }}>
                  注册新账号
                </Button>
                <Button type="link" size="small" onClick={() => switchMode('reset')}
                  style={{ padding: 0, fontSize: 13, color: 'var(--text-muted)' }}>
                  忘记密码？
                </Button>
              </div>
            )}
            {(mode === 'register' || mode === 'reset') && (
              <Button type="link" size="small" onClick={() => switchMode('login')}
                style={{ padding: 0, fontSize: 13, color: 'var(--text-muted)' }}>
                返回登录
              </Button>
            )}
          </div>
        )}

        <div style={{
          textAlign: 'center', marginTop: 24,
          paddingTop: 20,
          borderTop: '1px solid var(--border)',
        }}>
          <Text style={{
            color: 'var(--text-muted)', fontSize: 11, letterSpacing: 2,
            fontFamily: "var(--font-mono)",
          }}>
            SYS.INTEL.MONITOR v1.0
          </Text>
        </div>
      </Card>
    </div>
  )
}
