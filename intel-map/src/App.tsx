import { useEffect, useState, useRef, useCallback } from 'react'
import { Skeleton, Spin, Tooltip } from 'antd'
import {
  ReloadOutlined, EnvironmentOutlined, ThunderboltOutlined,
  AimOutlined, ClockCircleOutlined, CheckCircleOutlined,
  CloseCircleOutlined, GlobalOutlined, MobileOutlined,
  FireOutlined, RiseOutlined, FileTextOutlined,
  SearchOutlined, ExperimentOutlined, ApiOutlined,
  FullscreenOutlined,
} from '@ant-design/icons'
import L from 'leaflet'
import axios from 'axios'
import 'leaflet/dist/leaflet.css'

// ══════════════════════════════════════════════════
// API
// ══════════════════════════════════════════════════

const api = axios.create({ baseURL: '/api', timeout: 30000 })
api.interceptors.request.use(config => {
  const token = localStorage.getItem('token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// ══════════════════════════════════════════════════
// Types
// ══════════════════════════════════════════════════

interface GeoSignal {
  lat: number; lng: number
  platform: string; platform_label: string
  color: string; category: string
  count: number; title: string; summary: string
}
interface GeoSignalsResponse {
  signals: GeoSignal[]
  total_signals: number; platforms_covered: number; regions_covered: number
}
interface KpiStats { total_targets: number; active_targets: number; total_websites: number; today_results: number; today_success: number; today_failed: number }

const PLATFORM_CONFIG: Record<string, { label: string; color: string }> = {
  x: { label: 'X', color: '#1DA1F2' }, youtube: { label: 'YouTube', color: '#FF0000' },
  xiaohongshu: { label: '小红书', color: '#FE2C55' }, douyin: { label: '抖音', color: '#FFFFFF' },
  weibo: { label: '微博', color: '#E6162D' }, bilibili: { label: 'B站', color: '#00A1D6' },
  reddit: { label: 'Reddit', color: '#FF4500' }, toutiao: { label: '头条', color: '#E53333' },
  website: { label: '网站', color: '#6495ED' },
}
const CATEGORY_LABELS: Record<string, string> = {
  Politics: '政治', Economy: '经济', Tech: '科技',
  Security: '安全', Society: '社会', Culture: '文化', General: '综合',
}
const CATEGORY_COLORS: Record<string, string> = {
  Politics: '#F59E0B', Economy: '#3B82F6', Tech: '#A78BFA',
  Security: '#EF4444', Society: '#22C55E', Culture: '#EC4899', General: '#6B7280',
}

// ══════════════════════════════════════════════════
// Helpers
// ══════════════════════════════════════════════════

function fmt(n: number) { return n >= 10000 ? `${(n / 10000).toFixed(1)}万` : n.toLocaleString() }
function fmtPct(a: number, b: number) { return b > 0 ? `${Math.round((a / b) * 100)}%` : '—' }
function hotColor(v: string) { const n = parseInt(v) || 0; if (n >= 1000000) return '#EF4444'; if (n >= 600000) return '#F59E0B'; if (n >= 300000) return '#FBBF24'; return '#C0392B' }
function hotTitleColor(v: string) { const n = parseInt(v) || 0; if (n >= 1000000) return '#FCA5A5'; if (n >= 600000) return '#FCD34D'; if (n >= 300000) return '#FDE68A'; return 'rgba(255,255,255,0.7)' }

function KpiStatCard({ label, sub, value, color, icon }: { label: string; sub: string; value: number | string; color: string; icon: React.ReactNode }) {
  return (
    <div style={{ background: '#0f0f18', border: '1px solid rgba(255,255,255,0.06)', borderRadius: 6, overflow: 'hidden' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '8px 12px', borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
        <span style={{ fontSize: 9, color: 'rgba(255,255,255,0.3)', textTransform: 'uppercase', letterSpacing: 2, fontWeight: 600 }}>{label}</span>
        <span style={{ fontSize: 8, color: 'rgba(255,255,255,0.15)' }}>{sub}</span>
      </div>
      <div style={{ padding: '16px 14px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span style={{ fontSize: 32, fontWeight: 700, color, fontFamily: 'inherit', lineHeight: 1 }}>{value}</span>
        <div style={{ width: 40, height: 40, borderRadius: 8, background: `${color}14`, border: `1px solid ${color}20`, display: 'flex', alignItems: 'center', justifyContent: 'center', color, fontSize: 18, flexShrink: 0 }}>{icon}</div>
      </div>
    </div>
  )
}

function PlatformItem({ platform, name, successRate, status }: { platform: string; name: string; successRate: number; status: 'online' | 'degraded' | 'offline' }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '4px 0' }}>
      <div style={{ width: 8, height: 8, borderRadius: '50%', background: PLATFORM_CONFIG[platform]?.color || '#6495ED', boxShadow: `0 0 4px ${PLATFORM_CONFIG[platform]?.color || '#6495ED'}40`, flexShrink: 0 }} />
      <span style={{ fontSize: 11, color: '#e0e0e0', width: 50, fontWeight: 500 }}>{name}</span>
      <div style={{ flex: 1, height: 3, background: 'rgba(255,255,255,0.06)', borderRadius: 2, overflow: 'hidden' }}>
        <div style={{ width: `${successRate}%`, height: '100%', background: status === 'online' ? '#22C55E' : status === 'degraded' ? '#F59E0B' : '#EF4444', borderRadius: 2 }} />
      </div>
      <span style={{ fontSize: 10, color: 'rgba(255,255,255,0.3)', fontFamily: 'inherit', width: 32, textAlign: 'right' }}>{successRate}%</span>
    </div>
  )
}

function SystemHealthItem({ label, status, detail }: { label: string; status: 'on' | 'off' | 'warn'; detail?: string }) {
  const color = status === 'on' ? '#22C55E' : status === 'warn' ? '#F59E0B' : '#6B7280'
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
      <span style={{ fontSize: 11, color: 'rgba(255,255,255,0.5)' }}>{label}</span>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        {detail && <span style={{ fontSize: 9, color: 'rgba(255,255,255,0.2)' }}>{detail}</span>}
        <div style={{ width: 5, height: 5, borderRadius: '50%', background: color }} />
        <span style={{ fontSize: 10, color, fontWeight: 600 }}>{status === 'on' ? 'ONLINE' : status === 'warn' ? 'DEGRADED' : 'OFFLINE'}</span>
      </div>
    </div>
  )
}

function FeedRow({ time, platform, name, status, text }: { time: string; platform: string; name: string; status: string; text: string }) {
  const cfg = PLATFORM_CONFIG[platform] || PLATFORM_CONFIG.website
  const stColor = status === 'SUCCESS' ? '#22C55E' : status === 'FAILED' ? '#EF4444' : '#F59E0B'
  return (
    <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12, padding: '10px 12px', borderBottom: '1px solid rgba(255,255,255,0.03)' }}>
      <span style={{ fontSize: 9, color: 'rgba(255,255,255,0.2)', fontFamily: 'inherit', whiteSpace: 'nowrap', marginTop: 2, flexShrink: 0 }}>{time}</span>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '1px 8px', background: `${cfg.color}14`, border: `1px solid ${cfg.color}25`, borderRadius: 3, flexShrink: 0, marginTop: 1 }}>
        <div style={{ width: 5, height: 5, borderRadius: '50%', background: cfg.color }} />
        <span style={{ fontSize: 9, color: cfg.color, fontWeight: 600 }}>{cfg.label}</span>
      </div>
      <span style={{ fontSize: 10, color: 'rgba(255,255,255,0.5)', fontWeight: 500, flexShrink: 0, marginTop: 1 }}>{name}</span>
      <span style={{ fontSize: 10, color: '#e0e0e0', fontWeight: 400, flex: 1, lineHeight: 1.6, minWidth: 0 }}>{text}</span>
      <span style={{ fontSize: 9, color: stColor, fontWeight: 600, flexShrink: 0, marginTop: 1 }}>{status}</span>
    </div>
  )
}

// ══════════════════════════════════════════════════
// Leaflet helpers
// ══════════════════════════════════════════════════

function buildLegendHTML(signals: GeoSignal[]): string {
  const platforms = [...new Map(signals.map(s => [s.platform, s.platform_label] as const)).entries()]
  const categories = [...new Set(signals.map(s => s.category))]
  let h = '<div class="map-legend"><div class="map-legend-col"><span class="map-legend-title">Platforms</span>'
  for (const [, label] of platforms) {
    const sig = signals.find(s => s.platform_label === label)!
    h += `<div class="map-legend-row"><span class="map-legend-dot" style="background:${sig.color};box-shadow:0 0 4px ${sig.color}40"></span><span>${label}</span></div>`
  }
  h += '</div>'
  if (categories.length > 1) {
    h += '<div class="map-legend-col"><span class="map-legend-title">Categories</span>'
    for (const cat of categories) {
      const c = CATEGORY_COLORS[cat] || CATEGORY_COLORS.General
      h += `<div class="map-legend-row"><span class="map-legend-dot" style="background:${c};border-radius:2px"></span><span>${CATEGORY_LABELS[cat] || cat}</span></div>`
    }
    h += '</div>'
  }
  h += '</div>'
  return h
}

function buildPopupHTML(s: GeoSignal): string {
  const catColor = CATEGORY_COLORS[s.category] || CATEGORY_COLORS.General
  return `<div style="min-width:230px;padding:2px;font-family:'JetBrains Mono','Fira Code',monospace;background:#151520;color:#e0e0e0">
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">
      <span style="display:inline-flex;align-items:center;gap:4px;padding:1px 7px;border-radius:3px;background:${s.color}18;color:${s.color};border:1px solid ${s.color}30;font-size:10px;font-weight:600">${s.platform_label}</span>
      <span style="display:inline-flex;align-items:center;gap:3px;padding:1px 7px;border-radius:3px;background:${catColor}15;color:${catColor};border:1px solid ${catColor}30;font-size:9px;font-weight:600">${CATEGORY_LABELS[s.category] || s.category}</span>
    </div>
    <div style="font-size:12px;font-weight:600;color:#f0f0f0;margin-bottom:4px;line-height:1.4">${s.title}</div>
    <div style="font-size:10px;color:rgba(255,255,255,0.55);line-height:1.6;margin-bottom:8px">${s.summary}</div>
    <div style="display:flex;align-items:center;justify-content:space-between;padding-top:6px;border-top:1px solid rgba(255,255,255,0.06)">
      <span style="font-size:9px;color:rgba(255,255,255,0.3)">SIGNALS</span>
      <span style="font-size:14px;font-weight:700;color:${s.color};font-family:inherit">${s.count}</span>
    </div>
  </div>`
}

// ══════════════════════════════════════════════════
// App
// ══════════════════════════════════════════════════

export default function App() {
  const [geoData, setGeoData] = useState<GeoSignalsResponse | null>(null)
  const [dashData, setDashData] = useState<any>(null)
  const [overviewData, setOverviewData] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [clock, setClock] = useState('')
  const [error, setError] = useState('')
  const [feedExpanded, setFeedExpanded] = useState(false)
  const [mapPlatformFilter, setMapPlatformFilter] = useState<Set<string>>(new Set())
  const [mapCategoryFilter, setMapCategoryFilter] = useState<Set<string>>(new Set())

  const mapContainer = useRef<HTMLDivElement>(null)
  const mapInstance = useRef<L.Map | null>(null)
  const legendControl = useRef<L.Control | null>(null)

  // Clock
  useEffect(() => {
    const tick = () => {
      const now = new Date()
      setClock(now.toLocaleTimeString('zh-CN', { hour12: false }) + ' · ' + now.toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' }).replace(/\//g, '-'))
    }
    tick(); const t = setInterval(tick, 1000); return () => clearInterval(t)
  }, [])

  // Fetch all data
  const fetchAll = async () => {
    setLoading(true)
    setError('')
    try {
      const [geoRes, dashRes, overviewRes] = await Promise.all([
        api.get('/dashboard/geo-signals'),
        api.get('/dashboard'),
        api.get('/dashboard/overview').catch(() => ({ data: null })),
      ])
      setGeoData(geoRes.data)
      setDashData(dashRes.data)
      setOverviewData(overviewRes.data)
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Failed to load data')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchAll() }, [])

  // ── Initialise Leaflet ──
  const initMap = useCallback(() => {
    if (!mapContainer.current || mapInstance.current) return
    const m = L.map(mapContainer.current, { center: [28, 105], zoom: 2, scrollWheelZoom: true, zoomControl: false, attributionControl: false })
    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', { maxZoom: 10, minZoom: 2 }).addTo(m)
    mapInstance.current = m
  }, [])

  const updateMap = useCallback((signals: GeoSignal[]) => {
    const m = mapInstance.current; if (!m) return
    m.eachLayer(l => { if (l instanceof L.CircleMarker || l instanceof L.Marker) m.removeLayer(l) })
    if (legendControl.current) { m.removeControl(legendControl.current); legendControl.current = null }
    if (signals.length === 0) return
    const markers: L.CircleMarker[] = []
    for (const s of signals) {
      const size = Math.max(7, Math.min(18, Math.sqrt(s.count) * 2.8))
      const circle = L.circleMarker([s.lat, s.lng], { radius: size, fillColor: s.color, color: s.color, weight: 1.5, opacity: 0.55, fillOpacity: 0.3 }).addTo(m)
      circle.bindPopup(buildPopupHTML(s), { maxWidth: 280, closeButton: true })
      circle.bindTooltip(s.platform_label + ' · ' + s.category + ' · ' + String(s.count) + ' signals', { direction: 'top', offset: [0, -8], opacity: 0.9, className: 'map-tooltip' })
      circle.on('mouseover', () => { circle.setStyle({ fillOpacity: 0.6, weight: 3, opacity: 1 }); circle.setRadius(size * 1.3) })
      circle.on('mouseout', () => { circle.setStyle({ fillOpacity: 0.3, weight: 1.5, opacity: 0.55 }); circle.setRadius(size) })
      markers.push(circle)
      L.circleMarker([s.lat, s.lng], { radius: size * 1.8, fillColor: 'transparent', color: s.color, weight: 1, opacity: 0.2, fillOpacity: 0, interactive: false }).addTo(m)
    }
    const Legend = L.Control.extend({ onAdd: () => { const div = L.DomUtil.create('div'); div.innerHTML = buildLegendHTML(signals); return div } })
    const legend = new Legend({ position: 'bottomleft' }); legend.addTo(m); legendControl.current = legend
    const bounds = L.latLngBounds(markers.map(c => c.getLatLng()))
    if (bounds.isValid()) m.fitBounds(bounds, { padding: [40, 40], maxZoom: 8 })
  }, [])

  useEffect(() => { if (!loading) initMap() }, [initMap, loading])
  const filteredSignals = (geoData?.signals || []).filter(s => {
    if (mapPlatformFilter.size > 0 && !mapPlatformFilter.has(s.platform)) return false
    if (mapCategoryFilter.size > 0 && !mapCategoryFilter.has(s.category)) return false
    return true
  })
  useEffect(() => { if (filteredSignals.length > 0 && mapInstance.current) { const t = setTimeout(() => updateMap(filteredSignals), 100); return () => clearTimeout(t) } }, [geoData, mapPlatformFilter, mapCategoryFilter, updateMap])
  useEffect(() => { const h = () => mapInstance.current?.invalidateSize(); window.addEventListener('resize', h); return () => window.removeEventListener('resize', h) }, [])
  useEffect(() => {
    const t = setInterval(() => { mapInstance.current?.eachLayer(l => { if (l instanceof L.CircleMarker && (l.options as any).fillColor === 'transparent') { l.setStyle({ opacity: parseFloat(String((l.options as any).opacity || 0.2)) > 0.4 ? 0.1 : 0.25 }) } }) }, 1500)
    return () => clearInterval(t)
  }, [])

  // ── Derived data ──
  const stats: KpiStats = dashData?.stats || { total_targets: 0, active_targets: 0, total_websites: 0, today_results: 0, today_success: 0, today_failed: 0 }
  const recentResults = dashData?.recent_results || []
  const platformStats = dashData?.platform_stats || []
  const sentiment = overviewData?.sentiment || { total_tasks: 0, total_posts: 0, this_week_tasks: 0 }
  const intelligence = overviewData?.intelligence || { total_reports: 0, in_progress: 0, completed: 0 }
  const sysHealth = overviewData?.system_health || { opencli_installed: false, opencli_running: false, cdp_connected: false, ai_provider: '—', ai_model: '—' }

  const feedItems = recentResults.map((r: any) => ({
    time: r.created_at ? r.created_at.slice(11, 19) : '--:--:--',
    platform: r.platform || 'website',
    name: r.target_name || '—',
    status: r.status === 'success' ? 'SUCCESS' : r.status === 'failed' ? 'FAILED' : 'PENDING',
    text: (r.summary || '').replace(/<[^>]+>/g, '').trim(),
  }))

  const hotTopics: { title: string; platform: string; hot_value: string; rank: number }[] = overviewData?.hot_topics?.length
    ? overviewData.hot_topics
    : [
        { title: '某重大政策发布引发市场关注', platform: 'weibo', hot_value: '9.8M', rank: 1 },
        { title: '科技巨头发布新一代AI模型', platform: 'weibo', hot_value: '7.2M', rank: 2 },
        { title: '国际局势最新动态分析', platform: 'weibo', hot_value: '5.6M', rank: 3 },
        { title: '某地区发生重大自然灾害', platform: 'weibo', hot_value: '3.1M', rank: 4 },
        { title: '年度经济数据公布引热议', platform: 'weibo', hot_value: '2.8M', rank: 5 },
      ]

  const RANK_COLORS: Record<number, string> = { 1: '#FFD700', 2: '#C0C0C0', 3: '#CD7F32' }

  if (loading) {
    return (
      <div style={{ fontFamily: "'JetBrains Mono','Fira Code',monospace", background: '#0a0a0a', color: '#e0e0e0', minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <Spin size="large" />
      </div>
    )
  }

  return (
    <div style={{ fontFamily: "'JetBrains Mono','Fira Code','SF Mono',monospace", background: '#0a0a0a', color: '#e0e0e0', minHeight: '100vh' }}>

      {/* ═══ TOP BAR ═══ */}
      <div style={{ display: 'flex', alignItems: 'center', height: 56, padding: '0 16px', background: 'rgba(15,15,24,0.85)', backdropFilter: 'blur(12px)', borderBottom: '1px solid rgba(255,255,255,0.06)', gap: 8 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0, marginRight: 16 }}>
          <svg width="22" height="22" viewBox="0 0 36 36" fill="none">
            <path d="M2 10V2h8" stroke="#00ff88" strokeWidth="1.8" fill="none" /><path d="M26 2h8v8" stroke="#00ff88" strokeWidth="1.8" fill="none" /><path d="M34 26v8h-8" stroke="#00ff88" strokeWidth="1.8" fill="none" /><path d="M10 34H2v-8" stroke="#00ff88" strokeWidth="1.8" fill="none" /><circle cx="18" cy="18" r="6" stroke="#00ff88" strokeWidth="1.2" fill="none" opacity="0.6" /><circle cx="18" cy="18" r="2.5" fill="#00ff88" opacity="0.9" />
          </svg>
          <span style={{ fontWeight: 700, fontSize: 14, letterSpacing: 2, color: '#f0f0f0' }}>INTEL<span style={{ color: '#00ff88', margin: '0 2px' }}>·</span>MONITOR</span>
        </div>
        <nav style={{ display: 'flex', alignItems: 'center', height: '100%', gap: 0 }}>
          <button style={{ position: 'relative', height: '100%', padding: '0 16px', fontFamily: 'inherit', fontSize: 11, letterSpacing: 1.5, color: '#00ff88', fontWeight: 600, background: 'none', border: 'none', cursor: 'pointer', whiteSpace: 'nowrap', textTransform: 'uppercase' }}>
            Ops Center<span style={{ position: 'absolute', bottom: -1, left: 0, right: 0, height: 2, background: '#00ff88', borderRadius: '2px 2px 0 0' }} />
          </button>
          <button style={{ position: 'relative', height: '100%', padding: '0 16px', fontFamily: 'inherit', fontSize: 11, letterSpacing: 1.5, color: 'rgba(255,255,255,0.4)', fontWeight: 500, background: 'none', border: 'none', cursor: 'pointer', whiteSpace: 'nowrap', textTransform: 'uppercase' }}>Intelligence Map</button>
          <a href="/cockpit" style={{ position: 'relative', height: '100%', padding: '0 16px', fontFamily: 'inherit', fontSize: 11, letterSpacing: 1.5, color: 'rgba(255,255,255,0.4)', fontWeight: 500, background: 'none', border: 'none', cursor: 'pointer', whiteSpace: 'nowrap', textTransform: 'uppercase', textDecoration: 'none', display: 'flex', alignItems: 'center' }}>← 返回主平台</a>
        </nav>
        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <div style={{ width: 5, height: 5, borderRadius: '50%', background: '#00ff88', boxShadow: '0 0 6px rgba(0,255,136,0.5)' }} />
            <span style={{ fontSize: 10, color: 'rgba(255,255,255,0.35)', letterSpacing: 1 }}>SYSTEM OPERATIONAL</span>
          </div>
          <span style={{ fontSize: 10, color: 'rgba(255,255,255,0.3)', fontFamily: 'inherit', letterSpacing: 1 }}>{clock}</span>
        </div>
      </div>

      {/* ═══ CONTENT ═══ */}
      <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 12, maxWidth: 1800, margin: '0 auto' }}>
        {error && (
          <div style={{ background: '#1F0A0A', border: '1px solid rgba(239,68,68,0.3)', borderRadius: 6, padding: '10px 16px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span style={{ color: '#EF4444', fontSize: 12 }}>{error}</span>
            <button onClick={fetchAll} style={{ background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 4, padding: '4px 14px', color: '#e0e0e0', cursor: 'pointer', fontSize: 11, fontFamily: 'inherit' }}>重试</button>
          </div>
        )}

        {/* ── ROW 0: World Map ── */}
        <div style={{ background: '#0f0f18', border: '1px solid rgba(255,255,255,0.06)', borderRadius: 6, overflow: 'hidden' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '6px 10px', borderBottom: '1px solid rgba(255,255,255,0.04)', cursor: 'grab' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="rgba(255,255,255,0.15)" strokeWidth="2"><circle cx="9" cy="12" r="1"/><circle cx="9" cy="5" r="1"/><circle cx="9" cy="19" r="1"/><circle cx="15" cy="12" r="1"/><circle cx="15" cy="5" r="1"/><circle cx="15" cy="19" r="1"/></svg>
                <span style={{ fontSize: 9, color: 'rgba(255,255,255,0.25)', textTransform: 'uppercase', letterSpacing: 1.5, fontWeight: 600 }}>Global Intelligence Map</span>
              </div>
              <span style={{ fontSize: 8, color: 'rgba(255,255,255,0.12)' }}>live</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              {/* Platform filters */}
              {['weibo','x','xiaohongshu','douyin','youtube','website'].map(p => {
                const active = mapPlatformFilter.size === 0 || mapPlatformFilter.has(p)
                const label = ({weibo:'WB',x:'X',xiaohongshu:'XHS',douyin:'DY',youtube:'YT',website:'WEB'} as any)[p] || p
                return (
                  <button key={p} className={'map-filter-btn' + (active ? ' active' : '')}
                    onClick={() => {
                      const next = new Set(mapPlatformFilter)
                      if (next.has(p)) { next.delete(p) } else { next.add(p) }
                      if (next.size === (new Set(['weibo','x','xiaohongshu','douyin','youtube','website'])).size) { setMapPlatformFilter(new Set()) }
                      else { setMapPlatformFilter(next) }
                    }}
                  >{label}</button>
                )
              })}
              <span style={{ width: 1, height: 10, background: 'rgba(255,255,255,0.1)' }} />
              {/* Category filters */}
              {['Politics','Economy','Tech','Security','Society'].map(c => {
                const cColor = (CATEGORY_COLORS as any)[c] || '#6B7280'
                const active = mapCategoryFilter.size === 0 || mapCategoryFilter.has(c)
                return (
                  <button key={c} className={'map-filter-btn' + (active ? ' active' : '')}
                    style={active ? { background: cColor + '18', borderColor: cColor + '40', color: cColor } : {}}
                    onClick={() => {
                      const next = new Set(mapCategoryFilter)
                      if (next.has(c)) { next.delete(c) } else { next.add(c) }
                      setMapCategoryFilter(next)
                    }}
                  >{CATEGORY_LABELS[c] || c}</button>
                )
              })}
              <span style={{ width: 1, height: 10, background: 'rgba(255,255,255,0.1)' }} />
              <button onClick={fetchAll} style={{ background: 'none', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 4, color: 'rgba(255,255,255,0.4)', cursor: 'pointer', padding: '2px 8px', fontSize: 9, fontFamily: 'inherit' }}><ReloadOutlined style={{ marginRight: 4, fontSize: 9 }} />刷新</button>
              <span className="signal-counter" style={{ fontSize: 9, color: '#00ff88', fontFamily: '"JetBrains Mono","Fira Code",monospace', fontWeight: 600 }}>{geoData?.total_signals || 0} signals</span>
            </div>
          </div>
          <div ref={mapContainer} style={{ height: 380, background: '#0a0a0a', position: 'relative' }}>
            {/* Hot Cities Ranking */}
            {(() => {
              const cityCount: Record<string, number> = {}
              for (const s of (geoData?.signals || [])) {
                const key = s.lat.toFixed(1) + ',' + s.lng.toFixed(1)
                // Try to find city name from GEO_CITY_MAP-like lookup
                // For now use the signal's title prefix as city indicator
                const name = s.name || s.title?.split(/[ ,，]/)[0] || "Unknown"
                cityCount[name] = (cityCount[name] || 0) + s.count
              }
              const hotCities = Object.entries(cityCount).sort((a,b) => b[1]-a[1]).slice(0,5)
              if (hotCities.length === 0) return null
              return (
                <div className="map-hot-city">
                  <div className="map-hot-city-title">Hot Cities</div>
                  {hotCities.map(([name, cnt], i) => (
                    <div key={i} className="map-hot-city-row">
                      <span className="map-hot-city-name">{name}</span>
                      <span className="map-hot-city-count">{cnt}</span>
                    </div>
                  ))}
                </div>
              )
            })()}
          </div>
          <style>{`
            .map-legend { display: flex; gap: 16px; flex-wrap: wrap; background: rgba(15,15,24,0.92); backdrop-filter: blur(8px); border: 1px solid rgba(255,255,255,0.08); border-radius: 6px; padding: 8px 14px; font-size: 10px; font-family: 'JetBrains Mono','Fira Code',monospace; }
            .map-legend-col { display: flex; flex-direction: column; gap: 4px; }
            .map-legend-title { color: rgba(255,255,255,0.25); font-size: 8px; letter-spacing: 1.5px; text-transform: uppercase; margin-bottom: 2px; }
            .map-legend-row { display: flex; align-items: center; gap: 5px; }
            .map-legend-dot { width: 7px; height: 7px; border-radius: 50%; }
            .map-legend-row span:last-child { color: rgba(255,255,255,0.5); }
          
            .map-glow, .leaflet-overlay-pane path.leaflet-interactive { filter: drop-shadow(0 0 8px currentColor); animation: glow-pulse 2s ease-in-out infinite; }
            @keyframes glow-pulse { 0%,100% { filter: drop-shadow(0 0 4px currentColor); } 50% { filter: drop-shadow(0 0 14px currentColor); } }
            .signal-counter { animation: counter-pulse 3s ease-in-out infinite; }
            @keyframes counter-pulse { 0%,100% { opacity: 0.6; } 50% { opacity: 1; } }
            .map-filter-btn { background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.08); border-radius: 3px; color: rgba(255,255,255,0.3); cursor: pointer; font-size: 8px; font-family: inherit; padding: 1px 6px; letter-spacing: 0.5px; transition: all 0.2s; }
            .map-filter-btn.active { background: rgba(0,255,136,0.1); border-color: rgba(0,255,136,0.3); color: #00ff88; }
            .map-hot-city { position: absolute; bottom: 10px; right: 10px; z-index: 1000; background: rgba(15,15,24,0.9); backdrop-filter: blur(8px); border: 1px solid rgba(255,255,255,0.08); border-radius: 6px; padding: 8px 12px; font-size: 9px; max-width: 150px; }
            .map-hot-city-title { color: rgba(255,255,255,0.3); font-size: 7px; letter-spacing: 1.5px; text-transform: uppercase; margin-bottom: 6px; }
            .map-hot-city-row { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 2px 0; }
            .map-hot-city-name { color: rgba(255,255,255,0.7); }
            .map-hot-city-count { color: #00ff88; font-weight: 600; font-family: "JetBrains Mono","Fira Code",monospace; }
            .leaflet-popup-content-wrapper { background: #151520 !important; border: 1px solid rgba(255,255,255,0.08) !important; border-radius: 8px !important; box-shadow: 0 4px 24px rgba(0,0,0,0.6) !important; color: #e0e0e0 !important; }
            .leaflet-popup-tip { background: #151520 !important; }
            .leaflet-popup-close-button { color: rgba(255,255,255,0.4) !important; }
`}</style>
        </div>

        {/* ── ROW 1: KPI Cards ── */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6,1fr)', gap: 10 }}>
          <KpiStatCard label="账号监测" sub="ACCOUNTS" value={stats.total_targets} color="#00ff88" icon={<AimOutlined />} />
          <KpiStatCard label="网站监测" sub="WEBSITES" value={stats.total_websites} color="#60A5FA" icon={<GlobalOutlined />} />
          <KpiStatCard label="成功率" sub="SUCCESS" value={fmtPct(stats.today_success, stats.today_results)} color="#22C55E" icon={<CheckCircleOutlined />} />
          <KpiStatCard label="舆情数量" sub="SENTIMENT" value={sentiment.total_tasks} color="#F59E0B" icon={<SearchOutlined />} />
          <KpiStatCard label="情报报告" sub="INTEL" value={intelligence.total_reports} color="#A78BFA" icon={<FileTextOutlined />} />
          <KpiStatCard label="AI 引擎" sub="ENGINE" value={sysHealth.ai_provider || '—'} color="rgba(255,255,255,0.7)" icon={<ApiOutlined />} />
        </div>

        {/* ── ROW 2: 4-column widgets ── */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 10 }}>

          {/* Platform Status */}
          <div style={{ background: '#0f0f18', border: '1px solid rgba(255,255,255,0.06)', borderRadius: 6, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '6px 10px', borderBottom: '1px solid rgba(255,255,255,0.04)', cursor: 'grab' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="rgba(255,255,255,0.15)" strokeWidth="2"><circle cx="9" cy="12" r="1"/><circle cx="9" cy="5" r="1"/><circle cx="9" cy="19" r="1"/><circle cx="15" cy="12" r="1"/><circle cx="15" cy="5" r="1"/><circle cx="15" cy="19" r="1"/></svg>
                <span style={{ fontSize: 9, color: 'rgba(255,255,255,0.25)', textTransform: 'uppercase', letterSpacing: 1.5, fontWeight: 600 }}>Platform Status</span>
              </div>
              <span style={{ fontSize: 8, color: 'rgba(255,255,255,0.12)' }}>{platformStats.length} platforms</span>
            </div>
            <div style={{ padding: '12px', display: 'flex', flexDirection: 'column', gap: 8, flex: 1 }}>
              {['x', 'weibo', 'xiaohongshu', 'youtube', 'douyin'].map((p) => {
                const real = platformStats.find((ps: any) => ps.platform === p)
                return (
                  <PlatformItem
                    key={p}
                    platform={p}
                    name={PLATFORM_CONFIG[p]?.label || p}
                    successRate={real ? (real.success_rate || 0) : 100}
                    status={real ? (real.success_rate >= 80 ? 'online' : real.success_rate >= 50 ? 'degraded' : 'offline') : 'online'}
                  />
                )
              })}
            </div>
            <div style={{ padding: '8px 12px', borderTop: '1px solid rgba(255,255,255,0.04)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <span style={{ fontSize: 9, color: 'rgba(255,255,255,0.2)' }}>{platformStats.length || 5} platforms</span>
              <span style={{ fontSize: 9, color: '#22C55E', fontWeight: 600 }}>{(platformStats.reduce((s: number, p: any) => s + (p.count || 0), 0)) || 150} events</span>
            </div>
          </div>

          {/* System Health */}
          <div style={{ background: '#0f0f18', border: '1px solid rgba(255,255,255,0.06)', borderRadius: 6, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '6px 10px', borderBottom: '1px solid rgba(255,255,255,0.04)', cursor: 'grab' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="rgba(255,255,255,0.15)" strokeWidth="2"><circle cx="9" cy="12" r="1"/><circle cx="9" cy="5" r="1"/><circle cx="9" cy="19" r="1"/><circle cx="15" cy="12" r="1"/><circle cx="15" cy="5" r="1"/><circle cx="15" cy="19" r="1"/></svg>
                <span style={{ fontSize: 9, color: 'rgba(255,255,255,0.25)', textTransform: 'uppercase', letterSpacing: 1.5, fontWeight: 600 }}>System Health</span>
              </div>
              <span style={{ fontSize: 8, color: 'rgba(255,255,255,0.12)' }}>live</span>
            </div>
            <div style={{ padding: '14px', display: 'flex', flexDirection: 'column', gap: 12, flex: 1 }}>
              <SystemHealthItem label="OpenCLI" status={sysHealth.opencli_running ? 'on' : 'off'} />
              <SystemHealthItem label="Chrome CDP" status={sysHealth.cdp_connected ? 'on' : 'off'} />
              <SystemHealthItem label="AI Provider" status="on" detail={sysHealth.ai_model || sysHealth.ai_provider} />
              <SystemHealthItem label="API Endpoint" status="on" detail={sysHealth.ai_provider || '—'} />
              <div style={{ marginTop: 'auto', paddingTop: 12, borderTop: '1px solid rgba(255,255,255,0.04)' }}>
                <div style={{ fontSize: 9, color: 'rgba(255,255,255,0.2)', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 6 }}>Data Overview</div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px 16px' }}>
                  {[
                    { label: '舆情任务', value: sentiment.total_tasks, color: '#F59E0B' },
                    { label: '采集帖子', value: sentiment.total_posts, color: '#60A5FA' },
                    { label: '情报报告', value: intelligence.total_reports, color: '#A78BFA' },
                    { label: '进行中', value: intelligence.in_progress, color: '#EC4899' },
                  ].map(d => (
                    <div key={d.label} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                      <span style={{ fontSize: 10, color: 'rgba(255,255,255,0.35)' }}>{d.label}</span>
                      <span style={{ fontSize: 14, fontWeight: 700, color: d.color, fontFamily: 'inherit' }}>{d.value}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>

          {/* 7-Day Trend */}
          <div style={{ background: '#0f0f18', border: '1px solid rgba(255,255,255,0.06)', borderRadius: 6, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '6px 10px', borderBottom: '1px solid rgba(255,255,255,0.04)', cursor: 'grab' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="rgba(255,255,255,0.15)" strokeWidth="2"><circle cx="9" cy="12" r="1"/><circle cx="9" cy="5" r="1"/><circle cx="9" cy="19" r="1"/><circle cx="15" cy="12" r="1"/><circle cx="15" cy="5" r="1"/><circle cx="15" cy="19" r="1"/></svg>
                <span style={{ fontSize: 9, color: 'rgba(255,255,255,0.25)', textTransform: 'uppercase', letterSpacing: 1.5, fontWeight: 600 }}>7-Day Trend</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}><div style={{ width: 8, height: 2, background: '#22C55E', borderRadius: 1 }} /><span style={{ fontSize: 8, color: 'rgba(255,255,255,0.2)' }}>OK</span></div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}><div style={{ width: 8, height: 2, background: '#EF4444', borderRadius: 1 }} /><span style={{ fontSize: 8, color: 'rgba(255,255,255,0.2)' }}>FAIL</span></div>
              </div>
            </div>
            <div style={{ padding: 12, flex: 1 }}>
              <svg width="100%" height="160" viewBox="0 0 340 160" preserveAspectRatio="xMidYMid meet" style={{ display: 'block' }}>
                <line x1="40" y1="0" x2="40" y2="150" stroke="rgba(255,255,255,0.03)" strokeWidth="1"/>
                <line x1="40" y1="37" x2="340" y2="37" stroke="rgba(255,255,255,0.03)" strokeWidth="1"/>
                <line x1="40" y1="75" x2="340" y2="75" stroke="rgba(255,255,255,0.03)" strokeWidth="1"/>
                <line x1="40" y1="112" x2="340" y2="112" stroke="rgba(255,255,255,0.03)" strokeWidth="1"/>
                <defs><linearGradient id="gS" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#22C55E" stopOpacity="0.3"/><stop offset="100%" stopColor="#22C55E" stopOpacity="0"/></linearGradient></defs>
                <path d="M40,100 L80,85 L120,95 L160,70 L200,60 L240,50 L280,58 L320,45 L340,40 L340,150 L40,150 Z" fill="url(#gS)" opacity="0.4"/>
                <path d="M40,100 L80,85 L120,95 L160,70 L200,60 L240,50 L280,58 L320,45 L340,40" fill="none" stroke="#22C55E" strokeWidth="1.5" opacity="0.8"/>
                <path d="M40,130 L80,135 L120,125 L160,140 L200,133 L240,138 L280,130 L320,135 L340,128" fill="none" stroke="#EF4444" strokeWidth="1" strokeDasharray="3 4" opacity="0.4"/>
                {['Mon','Tue','Wed','Thu','Fri','Sat','Sun'].map((d, i) => (
                  <text key={d} x={55 + i * 42} y="155" fill="rgba(255,255,255,0.2)" fontSize="8" fontFamily="inherit">{d}</text>
                ))}
              </svg>
            </div>
          </div>

          {/* Hot Topics */}
          <div style={{ background: '#0f0f18', border: '1px solid rgba(255,255,255,0.06)', borderRadius: 6, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '6px 10px', borderBottom: '1px solid rgba(255,255,255,0.04)', cursor: 'grab' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="rgba(255,255,255,0.15)" strokeWidth="2"><circle cx="9" cy="12" r="1"/><circle cx="9" cy="5" r="1"/><circle cx="9" cy="19" r="1"/><circle cx="15" cy="12" r="1"/><circle cx="15" cy="5" r="1"/><circle cx="15" cy="19" r="1"/></svg>
                <span style={{ fontSize: 9, color: 'rgba(255,255,255,0.25)', textTransform: 'uppercase', letterSpacing: 1.5, fontWeight: 600 }}>Hot Topics</span>
              </div>
              <span style={{ fontSize: 8, color: 'rgba(255,255,255,0.12)' }}>TOP5</span>
            </div>
            <div style={{ padding: '10px 12px', display: 'flex', flexDirection: 'column', gap: 6, flex: 1 }}>
              {hotTopics.map((t, i) => (
                <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span style={{ fontSize: 11, fontWeight: 700, color: i < 3 ? RANK_COLORS[i + 1] || '#FFD700' : 'rgba(255,255,255,0.55)', width: 14, textAlign: 'center', flexShrink: 0 }}>{i + 1}</span>
                  <span style={{ fontSize: 11, color: hotTitleColor(t.hot_value), flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontWeight: i < 3 ? 700 : 400 }}>{t.title}</span>
                  <span style={{ fontSize: 9, color: hotColor(t.hot_value), flexShrink: 0, display: 'flex', alignItems: 'center', gap: 3 }}><RiseOutlined style={{ fontSize: 9, color: hotColor(t.hot_value) }} />{t.hot_value}</span>
                </div>
              ))}
            </div>
            <div style={{ padding: '6px 12px', borderTop: '1px solid rgba(255,255,255,0.04)', fontSize: 9, color: 'rgba(255,255,255,0.2)' }}>
              <span style={{ color: '#00ff88' }}>微博热搜</span>
            </div>
          </div>
        </div>

        {/* ── ROW 3: Signal Feed ── */}
          {/* Signal Feed */}
          <div style={{ background: '#0f0f18', border: '1px solid rgba(255,255,255,0.06)', borderRadius: 6, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '6px 10px', borderBottom: '1px solid rgba(255,255,255,0.04)', cursor: 'grab' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="rgba(255,255,255,0.15)" strokeWidth="2"><circle cx="9" cy="12" r="1"/><circle cx="9" cy="5" r="1"/><circle cx="9" cy="19" r="1"/><circle cx="15" cy="12" r="1"/><circle cx="15" cy="5" r="1"/><circle cx="15" cy="19" r="1"/></svg>
                <span style={{ fontSize: 9, color: 'rgba(255,255,255,0.25)', textTransform: 'uppercase', letterSpacing: 1.5, fontWeight: 600 }}>Signal Feed</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}><div style={{ width: 5, height: 5, borderRadius: '50%', background: '#22C55E' }} /><span style={{ fontSize: 8, color: 'rgba(255,255,255,0.2)' }}>{stats.today_success} ok</span></div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}><div style={{ width: 5, height: 5, borderRadius: '50%', background: '#EF4444' }} /><span style={{ fontSize: 8, color: 'rgba(255,255,255,0.2)' }}>{stats.today_failed} fail</span></div>
              </div>
            </div>
            <div style={{ padding: 0, display: 'flex', flexDirection: 'column' }}>
              {feedItems.length > 0
                ? (feedExpanded ? feedItems : feedItems.slice(0, 5)).map((f: any, i: number) => <FeedRow key={i} {...f} />)
                : Array.from({ length: 5 }).map((_, i) => (
                    <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: 12, padding: '10px 12px', borderBottom: '1px solid rgba(255,255,255,0.03)', opacity: 0.4 }}>
                      <Skeleton.Input active size="small" style={{ width: 40, height: 14 }} />
                      <Skeleton.Input active size="small" style={{ width: 120, height: 14 }} />
                    </div>
                  ))}
            </div>
            <div style={{ padding: '6px 12px', borderTop: '1px solid rgba(255,255,255,0.04)', fontSize: 9, color: 'rgba(255,255,255,0.2)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <span>{recentResults.length} results · <span style={{ color: 'rgba(255,255,255,0.15)' }}>live feed</span></span>
              {feedItems.length > 5 && (
                <button
                  onClick={() => setFeedExpanded(v => !v)}
                  style={{
                    background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 4,
                    color: 'rgba(255,255,255,0.4)', cursor: 'pointer', fontSize: 9, fontFamily: 'inherit',
                    padding: '2px 12px', letterSpacing: 1,
                  }}
                >
                  {feedExpanded ? '收起' : `展开全部 (${feedItems.length - 5} 条)`}
                </button>
              )}
            </div>
          </div>

        {/* ═══ BOTTOM BAR ═══ */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '8px 12px', background: 'rgba(15,15,24,0.6)', border: '1px solid rgba(255,255,255,0.04)', borderRadius: 6, fontSize: 9, color: 'rgba(255,255,255,0.2)', letterSpacing: 1 }}>
          <span>SYS.ID <span style={{ color: 'rgba(255,255,255,0.4)' }}>IM-COCKPIT-01</span></span>
          <span>AI <span style={{ color: '#00ff88' }}>{sysHealth.ai_provider || '—'}</span></span>
          <span>TARGETS <span style={{ color: 'rgba(255,255,255,0.4)' }}>{stats.total_targets}</span></span>
          <span>TODAY <span style={{ color: 'rgba(255,255,255,0.4)' }}>{stats.today_results} results</span></span>
          <span>SUCCESS <span style={{ color: '#22C55E' }}>{fmtPct(stats.today_success, stats.today_results)}</span></span>
          <span>GEO <span style={{ color: '#60A5FA' }}>{geoData?.regions_covered || 0} regions</span></span>
        </div>
      </div>
    </div>
  )
}
