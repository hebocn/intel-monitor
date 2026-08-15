import { useEffect, useState, useRef, useCallback, useMemo } from 'react'
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
  name: string
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

// ── 天气 / 台风 ──
interface TyphoonSummary {
  id: string; name: string; name_en: string; status: string
  track_points: number; started_at: string | null; ended_at: string | null
}
interface TyphoonCurrent {
  lat: number; lng: number
  pressure: number | null; wind_speed: number | null
  level: string; level_label: string
  move_dir: string; move_speed: number | null
  radius7: number | null; radius10: number | null
  obs_time: string
}
interface TyphoonTrackPoint {
  lat: number; lng: number
  pressure: number | null; wind_speed: number | null
  level: string; obs_time: string; is_forecast: boolean
}
interface TyphoonAffectedCity {
  name: string; lat: number; lng: number
  est_time: string; distance: number
}
interface TyphoonDetail {
  id: string; name: string; name_en: string
  current: TyphoonCurrent | null
  track: TyphoonTrackPoint[]
  affected_cities: TyphoonAffectedCity[]
  degraded: boolean
}
interface TyphoonListResponse {
  active: TyphoonSummary[]
  archived: TyphoonSummary[]
  degraded: boolean
}
interface WeatherWarning {
  id: string; type: string; level: string; level_code: string
  title: string; region: string
  lat: number | null; lng: number | null
  issued_by: string; issued_at: string
}
interface WarningsResponse { warnings: WeatherWarning[]; total: number; degraded: boolean }

const TYPHOON_LEVEL_COLORS: Record<string, string> = {
  TD: '#9CA3AF', TS: '#4ADE80', STS: '#FACC15',
  TY: '#FB923C', STY: '#F87171', SuperTY: '#C084FC',
}
const WARNING_LEVEL_COLORS: Record<string, string> = {
  blue: '#4FC3F7', yellow: '#FFD54F', orange: '#FF9800', red: '#F44336',
}
// 地图标记用淡色（浮层/弹窗仍用上面的深色保证文字可读）
const WARNING_MARKER_COLORS: Record<string, string> = {
  blue: '#81D4FA', yellow: '#FFE082', orange: '#FFCC80', red: '#FF8A80',
}
const WARNING_SEVERITY: Record<string, number> = { red: 3, orange: 2, yellow: 1, blue: 0 }
// 暴雨预警影响半径（km，预警无半径数据，按级别估算）
const WARN_RADIUS_KM: Record<string, number> = { red: 50, orange: 80, yellow: 120, blue: 150 }
// 预警类型展示顺序（筛选 chips）
const WARN_TYPE_ORDER = ['暴雨', '雷暴大风', '雷雨大风', '雷电', '大风', '冰雹', '大雾', '强对流']

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

function haversineKm(lat1: number, lng1: number, lat2: number, lng2: number): number {
  const R = 6371
  const dLat = ((lat2 - lat1) * Math.PI) / 180
  const dLng = ((lng2 - lng1) * Math.PI) / 180
  const a = Math.sin(dLat / 2) ** 2
    + Math.cos((lat1 * Math.PI) / 180) * Math.cos((lat2 * Math.PI) / 180) * Math.sin(dLng / 2) ** 2
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a))
}

// ── WGS-84 → GCJ-02（高德瓦片坐标系，仅中国大陆范围偏移，境外原样返回）──
const GCJ_A = 6378245.0
const GCJ_EE = 0.00669342162296594323

function _gcjOutOfChina(lat: number, lng: number): boolean {
  return lng < 72.004 || lng > 137.8347 || lat < 0.8293 || lat > 55.8271
}

function _gcjTransformLat(x: number, y: number): number {
  let ret = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * Math.sqrt(Math.abs(x))
  ret += (20.0 * Math.sin(6.0 * x * Math.PI) + 20.0 * Math.sin(2.0 * x * Math.PI)) * 2.0 / 3.0
  ret += (20.0 * Math.sin(y * Math.PI) + 40.0 * Math.sin(y / 3.0 * Math.PI)) * 2.0 / 3.0
  ret += (160.0 * Math.sin(y / 12.0 * Math.PI) + 320 * Math.sin(y * Math.PI / 30.0)) * 2.0 / 3.0
  return ret
}

function _gcjTransformLng(x: number, y: number): number {
  let ret = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * Math.sqrt(Math.abs(x))
  ret += (20.0 * Math.sin(6.0 * x * Math.PI) + 20.0 * Math.sin(2.0 * x * Math.PI)) * 2.0 / 3.0
  ret += (20.0 * Math.sin(x * Math.PI) + 40.0 * Math.sin(x / 3.0 * Math.PI)) * 2.0 / 3.0
  ret += (150.0 * Math.sin(x / 12.0 * Math.PI) + 300.0 * Math.sin(x / 30.0 * Math.PI)) * 2.0 / 3.0
  return ret
}

function wgs84ToGcj02(lat: number, lng: number): [number, number] {
  if (_gcjOutOfChina(lat, lng)) return [lat, lng]
  let dLat = _gcjTransformLat(lng - 105.0, lat - 35.0)
  let dLng = _gcjTransformLng(lng - 105.0, lat - 35.0)
  const radLat = lat / 180.0 * Math.PI
  let magic = Math.sin(radLat)
  magic = 1 - GCJ_EE * magic * magic
  const sqrtMagic = Math.sqrt(magic)
  dLat = (dLat * 180.0) / ((GCJ_A * (1 - GCJ_EE)) / (magic * sqrtMagic) * Math.PI)
  dLng = (dLng * 180.0) / (GCJ_A / sqrtMagic * Math.cos(radLat) * Math.PI)
  return [lat + dLat, lng + dLng]
}

function fmtBeijing(iso: string): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (isNaN(d.getTime())) return '—'
  return d.toLocaleString('zh-CN', {
    timeZone: 'Asia/Shanghai', hour12: false,
    year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
  })
}

function typhoonPopupHTML(d: TyphoonDetail): string {
  const c = d.current
  if (!c) return `<div style="padding:2px;font-family:'JetBrains Mono','Fira Code',monospace;background:#151520;color:#e0e0e0;font-size:11px">${d.name || d.name_en || d.id}</div>`
  const color = TYPHOON_LEVEL_COLORS[c.level] || '#9CA3AF'
  const row = (k: string, v: string, vc?: string) =>
    `<div style="display:flex;justify-content:space-between;gap:16px;padding:2px 0"><span style="font-size:9px;color:rgba(255,255,255,0.35)">${k}</span><span style="font-size:10px;color:${vc || '#e0e0e0'};font-weight:600">${v}</span></div>`
  return `<div style="min-width:200px;padding:2px;font-family:'JetBrains Mono','Fira Code',monospace;background:#151520;color:#e0e0e0">
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px">
      <span style="font-size:12px;font-weight:700;color:#f0f0f0">${d.name}${d.name_en && d.name_en !== 'nameless' ? ` <span style="font-size:9px;color:rgba(255,255,255,0.4)">${d.name_en}</span>` : ''}</span>
      <span style="display:inline-flex;align-items:center;padding:1px 7px;border-radius:3px;background:${color}18;color:${color};border:1px solid ${color}30;font-size:9px;font-weight:600">${c.level_label || c.level}</span>
    </div>
    ${row('中心气压', c.pressure != null ? `${c.pressure} hPa` : '—')}
    ${row('最大风速', c.wind_speed != null ? `${c.wind_speed} m/s` : '—')}
    ${row('移动', c.move_dir ? `${c.move_dir} ${c.move_speed != null ? c.move_speed + ' km/h' : ''}` : '—')}
    ${row('7级风圈', c.radius7 != null ? `${Math.round(c.radius7)} km` : '—')}
    ${row('10级风圈', c.radius10 != null ? `${Math.round(c.radius10)} km` : '—')}
    ${row('观测时间', fmtBeijing(c.obs_time))}
  </div>`
}

function raindropSvg(color: string): string {
  return `<svg width="14" height="18" viewBox="0 0 16 18">
    <path d="M8 0.5 C 4.2 5.5 2 8.8 2 12 A 6 6 0 0 0 14 12 C 14 8.8 11.8 5.5 8 0.5 Z"
      fill="${color}" fill-opacity="0.55" stroke="${color}" stroke-width="1" stroke-opacity="0.9"/>
    <line class="rain-streak" x1="5.8" y1="1.5" x2="5" y2="5" stroke="${color}" stroke-width="1" stroke-linecap="round"/>
    <line class="rain-streak s2" x1="10.2" y1="1.5" x2="11" y2="5" stroke="${color}" stroke-width="1" stroke-linecap="round"/>
  </svg>`
}

function windSvg(c: string): string {
  return `<svg width="14" height="18" viewBox="0 0 16 18">
    <path d="M1 6.5 Q4 4.5 7 6.5 T13 6.5" fill="none" stroke="${c}" stroke-width="1.5" stroke-linecap="round"/>
    <path d="M3 10.5 Q6 8.5 9 10.5 T15 10.5" fill="none" stroke="${c}" stroke-width="1.5" stroke-linecap="round"/>
    <path d="M1 14.5 Q4 12.5 7 14.5 T13 14.5" fill="none" stroke="${c}" stroke-width="1.5" stroke-linecap="round"/>
  </svg>`
}

const WARN_TYPE_ICONS: Record<string, (color: string) => string> = {
  '暴雨': raindropSvg,
  '雷电': (c) => `<svg width="14" height="18" viewBox="0 0 16 18">
    <path d="M9.5 1 L3.5 10.5 L7 10.5 L5.5 17 L12.5 7 L9 7 Z"
      fill="${c}" fill-opacity="0.6" stroke="${c}" stroke-width="1" stroke-linejoin="round"/>
  </svg>`,
  '大风': windSvg,
  '雷暴大风': windSvg,
  '冰雹': (c) => `<svg width="14" height="18" viewBox="0 0 16 18">
    <circle cx="8" cy="9.5" r="4.2" fill="${c}" fill-opacity="0.6" stroke="${c}" stroke-width="1"/>
    <path d="M8 2.5 V4.2 M8 14.8 V16.5 M2.2 9.5 H3.9 M12.1 9.5 H13.8" stroke="${c}" stroke-width="1.2" stroke-linecap="round"/>
  </svg>`,
  '大雾': (c) => `<svg width="14" height="18" viewBox="0 0 16 18">
    <path d="M1.5 6 H14.5 M1.5 10 H14.5 M1.5 14 H14.5" stroke="${c}" stroke-width="2.2" stroke-linecap="round" opacity="0.85"/>
  </svg>`,
  '强对流': (c) => `<svg width="14" height="18" viewBox="0 0 16 18">
    <path d="M8 2.5 A 6.5 6.5 0 1 1 2.9 6.2" fill="none" stroke="${c}" stroke-width="1.5" stroke-linecap="round"/>
    <circle cx="11.2" cy="11.8" r="1.4" fill="${c}"/>
  </svg>`,
}

function warningIcon(type: string, color: string): L.DivIcon {
  const build = WARN_TYPE_ICONS[type] || raindropSvg
  return L.divIcon({
    className: 'map-warn-drop-icon',
    html: build(color),
    iconSize: [14, 18],
    iconAnchor: [7, 17],   // 水滴尖端锚定坐标点
    popupAnchor: [0, -15],
  })
}

function warningPopupHTML(w: WeatherWarning): string {
  const color = WARNING_LEVEL_COLORS[w.level_code] || '#F44336'
  const row = (k: string, v: string) =>
    `<div style="display:flex;justify-content:space-between;gap:16px;padding:2px 0"><span style="font-size:9px;color:rgba(255,255,255,0.35);white-space:nowrap">${k}</span><span style="font-size:10px;color:#e0e0e0;font-weight:600;text-align:right">${v}</span></div>`
  return `<div style="min-width:200px;padding:2px;font-family:'JetBrains Mono','Fira Code',monospace;background:#151520;color:#e0e0e0">
    <div style="display:flex;align-items:center;gap:6px;margin-bottom:6px">
      <span style="display:inline-flex;align-items:center;padding:1px 7px;border-radius:3px;background:${color}18;color:${color};border:1px solid ${color}30;font-size:9px;font-weight:600">${w.type}</span>
      <span style="display:inline-flex;align-items:center;padding:1px 7px;border-radius:3px;background:${color}18;color:${color};border:1px solid ${color}30;font-size:9px;font-weight:600">${w.level}</span>
    </div>
    ${row('地区', w.region || '—')}
    ${row('发布单位', w.issued_by || '—')}
    ${row('发布时间', fmtBeijing(w.issued_at))}
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

  // ── 台风 / 预警状态 ──
  const [weatherOn, setWeatherOn] = useState(false)           // 台风图层开关
  const [warnOn, setWarnOn] = useState(false)                 // 预警图层开关
  const [typhoonList, setTyphoonList] = useState<TyphoonListResponse | null>(null)
  const [typhoonDetail, setTyphoonDetail] = useState<TyphoonDetail | null>(null)
  const [selectedTyphoonId, setSelectedTyphoonId] = useState<string | null>(null) // null = 默认活跃台风
  const [warnings, setWarnings] = useState<WarningsResponse | null>(null)
  const [weatherDegraded, setWeatherDegraded] = useState(false)
  const [histOpen, setHistOpen] = useState(false)
  const [warnPanelCollapsed, setWarnPanelCollapsed] = useState(false)
  const [activeWarning, setActiveWarning] = useState<WeatherWarning | null>(null)   // 点击浮层条目时临时显示影响圈
  const [warnTypeFilter, setWarnTypeFilter] = useState<Set<string>>(new Set(['暴雨']))  // 预警类型筛选，默认仅暴雨
  const [mapReady, setMapReady] = useState(false)

  const mapContainer = useRef<HTMLDivElement>(null)
  const mapInstance = useRef<L.Map | null>(null)
  const legendControl = useRef<L.Control | null>(null)
  const typhoonLayer = useRef<L.LayerGroup | null>(null)
  const warningLayer = useRef<L.LayerGroup | null>(null)
  const warningTempLayer = useRef<L.LayerGroup | null>(null)
  const signalMarkers = useRef<{ marker: L.CircleMarker; signal: GeoSignal; size: number }[]>([])
  const warningMarkers = useRef<Record<string, L.Marker>>({})
  const affectedKeys = useRef<Set<string>>(new Set())
  const warnAffectedKeys = useRef<Set<string>>(new Set())
  const panTyphoonNext = useRef(false)

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
    fetchWeather() // 气象数据独立刷新，不阻塞主数据
  }

  // ── 气象数据 ──
  const fetchWeather = useCallback(async () => {
    try {
      const [tRes, wRes] = await Promise.all([
        api.get('/weather/typhoons'),
        api.get('/weather/warnings'),
      ])
      setTyphoonList(tRes.data)
      setWarnings(wRes.data)
      setWeatherDegraded(!!(tRes.data.degraded || wRes.data.degraded))
    } catch {
      // 保留上次成功快照，仅提示降级
      setWeatherDegraded(true)
    }
  }, [])

  const fetchTyphoonDetail = useCallback(async (id: string) => {
    try {
      const res = await api.get(`/weather/typhoons/${id}`)
      setTyphoonDetail(res.data)
      setWeatherDegraded(d => d || !!res.data.degraded)
    } catch {
      setWeatherDegraded(true) // 保留上次快照
    }
  }, [])

  useEffect(() => { fetchAll() }, [])

  // 台风详情：开关打开时拉当前选中台风（默认活跃台风）
  const displayedTyphoonId = weatherOn
    ? (selectedTyphoonId || typhoonList?.active[0]?.id || null)
    : null
  useEffect(() => {
    if (displayedTyphoonId) fetchTyphoonDetail(displayedTyphoonId)
  }, [displayedTyphoonId, fetchTyphoonDetail])

  // 10 分钟轮询气象数据
  useEffect(() => {
    const t = setInterval(() => {
      fetchWeather()
      if (displayedTyphoonId) fetchTyphoonDetail(displayedTyphoonId)
    }, 10 * 60 * 1000)
    return () => clearInterval(t)
  }, [fetchWeather, fetchTyphoonDetail, displayedTyphoonId])

  // 历史下拉：点击外部关闭
  useEffect(() => {
    if (!histOpen) return
    const h = () => setHistOpen(false)
    document.addEventListener('click', h)
    return () => document.removeEventListener('click', h)
  }, [histOpen])

  // ── Initialise Leaflet ──
  const initMap = useCallback(() => {
    if (!mapContainer.current || mapInstance.current) return
    const m = L.map(mapContainer.current, { center: [28, 105], zoom: 2, scrollWheelZoom: true, zoomControl: false, attributionControl: true })
    // 高德中文瓦片（GCJ-02 坐标系，数据渲染时经 wgs84ToGcj02 转换；浅色瓦片由 CSS 滤镜暗化；无需 key）
    L.tileLayer('https://webrd0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=7&x={x}&y={y}&z={z}', {
      subdomains: ['1', '2', '3', '4'],
      maxZoom: 16,
      minZoom: 2,
      attribution: '©高德地图',
    }).addTo(m)
    typhoonLayer.current = L.layerGroup().addTo(m)
    warningLayer.current = L.layerGroup().addTo(m)
    warningTempLayer.current = L.layerGroup().addTo(m)
    mapInstance.current = m
    setMapReady(true)
  }, [])

  const updateMap = useCallback((signals: GeoSignal[]) => {
    const m = mapInstance.current; if (!m) return
    m.eachLayer(l => { if (l instanceof L.CircleMarker || l instanceof L.Marker) m.removeLayer(l) })
    if (legendControl.current) { m.removeControl(legendControl.current); legendControl.current = null }
    signalMarkers.current = []
    if (signals.length === 0) return
    const markers: L.CircleMarker[] = []
    for (const s of signals) {
      const key = `${s.lat.toFixed(3)},${s.lng.toFixed(3)}`
      const affected = affectedKeys.current.has(key) || warnAffectedKeys.current.has(key)
      const size = Math.max(7, Math.min(18, Math.sqrt(s.count) * 2.8))
      const [lat, lng] = wgs84ToGcj02(s.lat, s.lng)   // 高德底图为 GCJ-02，渲染时转换
      const circle = L.circleMarker([lat, lng], {
        radius: affected ? size + 5 : size,
        fillColor: affected ? '#FFFFFF' : s.color,
        color: affected ? '#FFFFFF' : s.color,
        weight: affected ? 3 : 1.5,
        opacity: 0.8,
        fillOpacity: affected ? 0.65 : 0.3,
      }).addTo(m)
      circle.bindPopup(buildPopupHTML(s), { maxWidth: 280, closeButton: true })
      circle.bindTooltip(s.platform_label + ' · ' + s.category + ' · ' + String(s.count) + ' signals', { direction: 'top', offset: [0, -8], opacity: 0.9, className: 'map-tooltip' })
      circle.on('mouseover', () => { circle.setStyle({ fillOpacity: 0.8, weight: 3, opacity: 1 }); circle.setRadius((affected ? size + 5 : size) * 1.3) })
      circle.on('mouseout', () => { circle.setStyle({ fillOpacity: affected ? 0.65 : 0.3, weight: affected ? 3 : 1.5, opacity: 0.8 }); circle.setRadius(affected ? size + 5 : size) })
      markers.push(circle)
      signalMarkers.current.push({ marker: circle, signal: s, size })
      L.circleMarker([lat, lng], { radius: size * 1.8, fillColor: 'transparent', color: s.color, weight: 1, opacity: 0.2, fillOpacity: 0, interactive: false }).addTo(m)
    }
    const Legend = L.Control.extend({ onAdd: () => { const div = L.DomUtil.create('div'); div.innerHTML = buildLegendHTML(signals); return div } })
    const legend = new Legend({ position: 'bottomleft' }); legend.addTo(m); legendControl.current = legend
    const bounds = L.latLngBounds(markers.map(c => c.getLatLng()))
    if (bounds.isValid()) m.fitBounds(bounds, { padding: [40, 40], maxZoom: 8 })
  }, [])

  useEffect(() => { if (!loading) initMap() }, [initMap, loading])
  const filteredSignals = useMemo(() =>
    (geoData?.signals || []).filter(s => {
      if (mapPlatformFilter.size > 0 && !mapPlatformFilter.has(s.platform)) return false
      if (mapCategoryFilter.size > 0 && !mapCategoryFilter.has(s.category)) return false
      return true
    }),
    [geoData, mapPlatformFilter, mapCategoryFilter]
  )
  useEffect(() => { if (filteredSignals.length > 0 && mapInstance.current) { const t = setTimeout(() => updateMap(filteredSignals), 100); return () => clearTimeout(t) } }, [filteredSignals, updateMap])

  // ── 台风影响信号（风圈内 haversine）──
  const typhoonCenter = weatherOn ? (typhoonDetail?.current || null) : null
  const affectedRadius = typhoonCenter ? Math.max(typhoonCenter.radius7 || 0, typhoonCenter.radius10 || 0) : 0
  const affectedSignals = useMemo(() =>
    (typhoonCenter && affectedRadius > 0)
      ? filteredSignals.filter(s => haversineKm(s.lat, s.lng, typhoonCenter.lat, typhoonCenter.lng) <= affectedRadius)
      : [],
    [filteredSignals, typhoonCenter, affectedRadius]
  )
  // 当前选中预警影响圈内的信号（声明在重标样式 effect 之前，保证 ref 先同步）
  const warnAffectedSignals = useMemo(() => {
    if (!warnOn || !activeWarning || activeWarning.lat == null || activeWarning.lng == null) return []
    const r = WARN_RADIUS_KM[activeWarning.level_code] || 120
    return filteredSignals.filter(s => haversineKm(s.lat, s.lng, activeWarning.lat!, activeWarning.lng!) <= r)
  }, [warnOn, activeWarning, filteredSignals])
  useEffect(() => {
    affectedKeys.current = new Set(affectedSignals.map(s => `${s.lat.toFixed(3)},${s.lng.toFixed(3)}`))
  }, [affectedSignals])
  useEffect(() => {
    warnAffectedKeys.current = new Set(warnAffectedSignals.map(s => `${s.lat.toFixed(3)},${s.lng.toFixed(3)}`))
  }, [warnAffectedSignals])

  // 台风风圈/预警影响圈变化时重标信号点样式（不重建、不 refit）
  useEffect(() => {
    for (const { marker, signal, size } of signalMarkers.current) {
      const key = `${signal.lat.toFixed(3)},${signal.lng.toFixed(3)}`
      const affected = affectedKeys.current.has(key) || warnAffectedKeys.current.has(key)
      marker.setStyle({
        radius: affected ? size + 5 : size,
        fillColor: affected ? '#FFFFFF' : signal.color,
        color: affected ? '#FFFFFF' : signal.color,
        weight: affected ? 3 : 1.5,
        opacity: 0.8,
        fillOpacity: affected ? 0.65 : 0.3,
      })
    }
  }, [affectedSignals, warnAffectedSignals])

  // 预警按类型筛选（默认仅暴雨，chips 可多选），按级别排序（红>橙>黄>蓝），同级按发布时间倒序
  const filteredWarnings = useMemo(() =>
    (warnings?.warnings || [])
      .filter(w => warnTypeFilter.has(w.type))
      .sort((a, b) =>
        ((WARNING_SEVERITY[b.level_code] || 0) - (WARNING_SEVERITY[a.level_code] || 0))
        || (b.issued_at || '').localeCompare(a.issued_at || '')
      ),
    [warnings, warnTypeFilter]
  )

  // ── 台风图层渲染 ──
  useEffect(() => {
    const m = mapInstance.current
    const group = typhoonLayer.current
    if (!m || !group || !mapReady) return
    group.clearLayers()
    if (!weatherOn || !typhoonDetail || typhoonDetail.track.length === 0) return
    const d = typhoonDetail
    const obs = d.track.filter(p => !p.is_forecast)
    const fc = d.track.filter(p => p.is_forecast)
    const color = TYPHOON_LEVEL_COLORS[d.current?.level || obs[obs.length - 1]?.level || ''] || '#9CA3AF'
    const lvlColor = (lvl: string) => TYPHOON_LEVEL_COLORS[lvl] || '#9CA3AF'
    const gcj = (p: { lat: number; lng: number }): [number, number] => wgs84ToGcj02(p.lat, p.lng)
    // 实况路径（实线）
    if (obs.length > 1) {
      L.polyline(obs.map(gcj), { color, weight: 2, opacity: 0.9 }).addTo(group)
    }
    // 预报路径（虚线，接在最后一个实况点后）
    if (fc.length > 0 && obs.length > 0) {
      L.polyline([obs[obs.length - 1], ...fc].map(gcj), { color, weight: 1.5, opacity: 0.7, dashArray: '6 6' }).addTo(group)
    }
    // 历史实况点（按强度着色）
    for (const p of obs) {
      L.circleMarker(gcj(p), { radius: 4, color: '#0f0f18', weight: 0.8, fillColor: lvlColor(p.level), fillOpacity: 0.95 }).addTo(group)
    }
    // 预报点（空心）
    for (const p of fc) {
      L.circleMarker(gcj(p), { radius: 3, color: lvlColor(p.level), weight: 1, fillColor: 'transparent', fillOpacity: 0 }).addTo(group)
    }
    // 当前点风圈 + 标记
    if (d.current) {
      const c = d.current
      const [clat, clng] = gcj(c)
      if (c.radius7) L.circle([clat, clng], { radius: c.radius7 * 1000, color: `${color}66`, weight: 1, fillColor: color, fillOpacity: 0.08, className: 'typhoon-wind-circle', interactive: false }).addTo(group)
      if (c.radius10) L.circle([clat, clng], { radius: c.radius10 * 1000, color: `${color}99`, weight: 1, fillColor: color, fillOpacity: 0.12, className: 'typhoon-wind-circle', interactive: false }).addTo(group)
      const cur = L.circleMarker([clat, clng], { radius: 7, color: '#FFFFFF', weight: 2, fillColor: lvlColor(c.level), fillOpacity: 1 }).addTo(group)
      cur.bindPopup(typhoonPopupHTML(d), { maxWidth: 280, closeButton: true })
      cur.bindTooltip(`${d.name} · ${c.level_label || c.level}`, { direction: 'top', offset: [0, -10], opacity: 0.9, className: 'map-tooltip' })
    }
    // 影响城市环标记（48h 窗口内风圈覆盖的城市，后端计算）
    for (const city of d.affected_cities || []) {
      const [clat, clng] = wgs84ToGcj02(city.lat, city.lng)
      const ring = L.circleMarker([clat, clng], {
        radius: 7, color: '#FFD54F', weight: 2,
        fillColor: '#FFD54F', fillOpacity: 0.12,
      }).addTo(group)
      ring.bindTooltip(`${city.name} · 距台风约 ${city.distance}km · 预计 ${fmtBeijing(city.est_time)}`, { direction: 'top', offset: [0, -8], opacity: 0.9, className: 'map-tooltip' })
    }
    // 用户切换台风/开开关时 pan 到台风
    if (panTyphoonNext.current) {
      panTyphoonNext.current = false
      const bounds = L.latLngBounds(d.track.map(gcj))
      if (bounds.isValid()) m.fitBounds(bounds, { padding: [60, 60], maxZoom: 7 })
    }
  }, [weatherOn, typhoonDetail, mapReady])

  // ── 预警图层渲染（按类型筛选，全部级别）──
  useEffect(() => {
    const group = warningLayer.current
    if (!group || !mapReady) return
    group.clearLayers()
    warningMarkers.current = {}
    if (!warnOn || filteredWarnings.length === 0) return
    for (const w of filteredWarnings) {
      if (w.lat == null || w.lng == null) continue
      const color = WARNING_MARKER_COLORS[w.level_code] || '#FF8A80'
      const mk = L.marker(wgs84ToGcj02(w.lat, w.lng), { icon: warningIcon(w.type, color) }).addTo(group)
      mk.bindPopup(warningPopupHTML(w), { maxWidth: 280, closeButton: true })
      // 点击图标：与浮层条目一致，切换影响圈显示（阻止冒泡避免地图点击取消逻辑误触发）
      mk.on('click', (e) => {
        L.DomEvent.stopPropagation(e)
        setActiveWarning(prev => prev?.id === w.id ? null : w)
      })
      warningMarkers.current[w.id] = mk
    }
  }, [warnOn, filteredWarnings, mapReady])

  // ── 预警×信号联动 ──

  // 每条预警影响圈内的信号计数（浮层每行显示）
  const warnSignalCounts = useMemo(() => {
    const counts: Record<string, number> = {}
    for (const w of filteredWarnings) {
      if (w.lat == null || w.lng == null) continue
      const r = WARN_RADIUS_KM[w.level_code] || 120
      let n = 0
      for (const s of filteredSignals) {
        if (haversineKm(s.lat, s.lng, w.lat, w.lng) <= r) n++
      }
      counts[w.id] = n
    }
    return counts
  }, [filteredWarnings, filteredSignals])

  // 点击预警浮层条目：临时影响圈（圈内信号高亮由 warnAffectedSignals 统一处理）
  useEffect(() => {
    const group = warningTempLayer.current
    if (!group || !mapReady) return
    group.clearLayers()
    if (!warnOn || !activeWarning) return
    const w = activeWarning
    if (w.lat == null || w.lng == null) return
    const r = WARN_RADIUS_KM[w.level_code] || 120
    const color = WARNING_LEVEL_COLORS[w.level_code] || '#F44336'
    const [clat, clng] = wgs84ToGcj02(w.lat, w.lng)
    L.circle([clat, clng], {
      radius: r * 1000, color: `${color}99`, weight: 1.5,
      fillColor: color, fillOpacity: 0.1,
      className: 'typhoon-wind-circle', interactive: false,
    }).addTo(group)
  }, [activeWarning, warnOn, mapReady])

  // 点击地图空白处取消临时影响圈
  useEffect(() => {
    const m = mapInstance.current
    if (!m || !mapReady) return
    const h = (e: L.LeafletMouseEvent) => {
      const target = e.originalEvent.target as Element
      if (target.closest?.('.map-warn-panel')) return   // 浮层内部点击不取消
      setActiveWarning(null)
    }
    m.on('click', h)
    return () => { m.off('click', h) }
  }, [mapReady])

  // 预警浮层内部点击不穿透到地图（避免触发取消逻辑）
  useEffect(() => {
    const panel = document.querySelector('.map-warn-panel')
    if (!panel) return
    L.DomEvent.disableClickPropagation(panel as HTMLElement)
  }, [warnOn, warnPanelCollapsed, mapReady])
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
              {/* Weather / Typhoon controls */}
              <button className={'map-filter-btn' + (weatherOn ? ' active' : '')}
                onClick={() => { panTyphoonNext.current = true; setWeatherOn(v => !v) }}
                title="台风路径 / 风圈图层"
              >台风</button>
              <button className={'map-filter-btn' + (warnOn ? ' active' : '')}
                onClick={() => setWarnOn(v => !v)}
                title="极端天气预警图层"
              >预警</button>
              <div style={{ position: 'relative' }} onClick={e => e.stopPropagation()}>
                <button className={'map-filter-btn' + (selectedTyphoonId ? ' active' : '')}
                  onClick={() => setHistOpen(v => !v)}
                  title="选择台风"
                >历史▾</button>
                {histOpen && (
                  <div className="typhoon-hist-menu">
                    <div className="typhoon-hist-head">当前活跃台风</div>
                    {(typhoonList?.active || []).map(t => (
                      <div key={t.id} className={'typhoon-hist-item' + (displayedTyphoonId === t.id ? ' sel' : '')}
                        onClick={() => { panTyphoonNext.current = true; setSelectedTyphoonId(t.id); setWeatherOn(true); setHistOpen(false) }}>
                        {t.name} <span style={{ opacity: 0.4 }}>{t.name_en !== 'nameless' ? t.name_en : ''}</span>
                      </div>
                    ))}
                    {(typhoonList?.active || []).length === 0 && <div className="typhoon-hist-empty">无活跃台风</div>}
                    {selectedTyphoonId && <div className={'typhoon-hist-item sel'}
                      onClick={() => { panTyphoonNext.current = true; setSelectedTyphoonId(null); setWeatherOn(true); setHistOpen(false) }}>
                      ⟲ 当前活跃台风
                    </div>}
                    <div className="typhoon-hist-head">历史台风</div>
                    {(typhoonList?.archived || []).map(t => (
                      <div key={t.id} className={'typhoon-hist-item' + (displayedTyphoonId === t.id ? ' sel' : '')}
                        onClick={() => { panTyphoonNext.current = true; setSelectedTyphoonId(t.id); setWeatherOn(true); setHistOpen(false) }}>
                        {t.name || t.name_en || t.id} <span style={{ opacity: 0.4 }}>{t.track_points} 点</span>
                      </div>
                    ))}
                    {(typhoonList?.archived || []).length === 0 && <div className="typhoon-hist-empty">暂无存档</div>}
                  </div>
                )}
              </div>
              {(weatherOn || warnOn) && weatherDegraded && (
                <span style={{ fontSize: 8, color: '#F59E0B' }} title="NMC 接口暂不可用，展示上次成功快照">气象数据不可用</span>
              )}
              <span style={{ width: 1, height: 10, background: 'rgba(255,255,255,0.1)' }} />
              <button onClick={fetchAll} style={{ background: 'none', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 4, color: 'rgba(255,255,255,0.4)', cursor: 'pointer', padding: '2px 8px', fontSize: 9, fontFamily: 'inherit' }}><ReloadOutlined style={{ marginRight: 4, fontSize: 9 }} />刷新</button>
              <span className="signal-counter" style={{ fontSize: 9, color: '#00ff88', fontFamily: '"JetBrains Mono","Fira Code",monospace', fontWeight: 600 }}>{geoData?.total_signals || 0} signals</span>
              {typhoonCenter && (
                <span style={{ fontSize: 9, color: '#FFFFFF', fontFamily: '"JetBrains Mono","Fira Code",monospace', fontWeight: 600, background: 'rgba(255,255,255,0.08)', borderRadius: 3, padding: '1px 6px' }}>受影响信号 {affectedSignals.length} 个</span>
              )}
            </div>
          </div>
          <div ref={mapContainer} style={{ height: 380, background: '#0a0a0a', position: 'relative' }}>
            {/* Hot Cities Ranking */}
            {(() => {
              const cityCount: Record<string, number> = {}
              for (const s of (geoData?.signals || [])) {
                // 后端 GEO_CITY_MAP 已匹配城市名，直接按城市聚合
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
            {/* Weather Warnings Panel (类型筛选，全部级别，可折叠) */}
            {warnOn && (
              <div className={'map-warn-panel' + (warnPanelCollapsed ? ' collapsed' : '')}>
                <div className="map-warn-panel-title" title={warnPanelCollapsed ? '展开预警列表' : '折叠预警列表'}
                  onClick={() => setWarnPanelCollapsed(v => !v)}>
                  <span>预警信号</span>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                    <span style={{ color: 'rgba(255,255,255,0.3)' }}>{filteredWarnings.length}</span>
                    <span className="map-warn-caret">{warnPanelCollapsed ? '▸' : '▾'}</span>
                  </span>
                </div>
                {!warnPanelCollapsed && (
                  <>
                    <div className="map-warn-chips">
                      {WARN_TYPE_ORDER.map(t => {
                        const cnt = (warnings?.warnings || []).filter(w => w.type === t).length
                        if (cnt === 0) return null
                        const active = warnTypeFilter.has(t)
                        return (
                          <button key={t} className={'map-warn-chip' + (active ? ' sel' : '')}
                            onClick={() => {
                              const next = new Set(warnTypeFilter)
                              if (next.has(t)) { next.delete(t) } else { next.add(t) }
                              setWarnTypeFilter(next)
                            }}>
                            {t}<span style={{ opacity: 0.55 }}> {cnt}</span>
                          </button>
                        )
                      })}
                    </div>
                    <div className="map-warn-list">
                      {filteredWarnings.slice(0, 50).map(w => {
                        const color = WARNING_LEVEL_COLORS[w.level_code] || '#F44336'
                        const count = warnSignalCounts[w.id] || 0
                        const isActive = activeWarning?.id === w.id
                        return (
                          <div key={w.id} className={'map-warn-row' + (isActive ? ' sel' : '')}
                            title={`${w.type}${w.level}预警`}
                            onClick={() => {
                              setActiveWarning(isActive ? null : w)   // 再点取消
                              const mk = warningMarkers.current[w.id]
                              const m = mapInstance.current
                              if (mk && m) {
                                m.flyTo(mk.getLatLng(), Math.max(m.getZoom(), 6), { duration: 0.6 })
                                mk.openPopup()
                              }
                            }}>
                            <span className="map-warn-bar" style={{ background: color }} />
                            <span className="map-warn-type" style={{ color }}>{w.type}</span>
                            <span className="map-warn-region">{w.region}</span>
                            <span className="map-warn-time">{fmtBeijing(w.issued_at)}</span>
                            <span className="map-warn-count" style={{ color: count > 0 ? '#00ff88' : 'rgba(255,255,255,0.15)' }}
                              title={`影响圈内信号数（${WARN_RADIUS_KM[w.level_code] || 120}km）`}>{count}</span>
                          </div>
                        )
                      })}
                      {warnTypeFilter.size === 0
                        ? <div className="typhoon-hist-empty">未选择预警类型</div>
                        : filteredWarnings.length === 0
                          ? <div className="typhoon-hist-empty">当前无该类型预警</div>
                          : null}
                    </div>
                  </>
                )}
              </div>
            )}
          </div>
          <style>{`
            /* 高德浅色瓦片暗化（暗色模式通用技巧：反相 + 色相回转） */
            .leaflet-tile-pane { filter: invert(1) hue-rotate(180deg) brightness(0.95) contrast(0.9) saturate(0.7); }
            .leaflet-control-attribution { background: rgba(15,15,24,0.75) !important; color: rgba(255,255,255,0.3) !important; font-size: 8px !important; }
            .leaflet-control-attribution a { color: rgba(255,255,255,0.4) !important; }
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

            /* 台风风圈脉冲 */
            .typhoon-wind-circle { animation: wind-pulse 2.5s ease-in-out infinite; }
            @keyframes wind-pulse { 0%,100% { fill-opacity: 0.06; stroke-opacity: 0.35; } 50% { fill-opacity: 0.18; stroke-opacity: 0.75; } }

            /* 历史台风下拉 */
            .typhoon-hist-menu { position: absolute; top: calc(100% + 6px); right: 0; z-index: 1100; min-width: 150px; max-height: 240px; overflow-y: auto; background: rgba(15,15,24,0.95); backdrop-filter: blur(10px); border: 1px solid rgba(255,255,255,0.1); border-radius: 6px; padding: 4px; box-shadow: 0 8px 28px rgba(0,0,0,0.5); }
            .typhoon-hist-head { font-size: 7px; letter-spacing: 1.5px; text-transform: uppercase; color: rgba(255,255,255,0.25); padding: 6px 8px 2px; }
            .typhoon-hist-item { font-size: 10px; color: rgba(255,255,255,0.6); padding: 4px 8px; border-radius: 3px; cursor: pointer; display: flex; align-items: center; justify-content: space-between; gap: 8px; white-space: nowrap; }
            .typhoon-hist-item:hover { background: rgba(255,255,255,0.06); color: #e0e0e0; }
            .typhoon-hist-item.sel { color: #00ff88; background: rgba(0,255,136,0.06); }
            .typhoon-hist-empty { font-size: 9px; color: rgba(255,255,255,0.2); padding: 4px 8px; }

            /* 预警浮层（地图内右上，可折叠） */
            .map-warn-panel { position: absolute; top: 10px; right: 10px; z-index: 1000; width: 230px; max-height: 300px; display: flex; flex-direction: column; background: rgba(15,15,24,0.9); backdrop-filter: blur(8px); border: 1px solid rgba(255,255,255,0.08); border-radius: 6px; padding: 8px 10px; font-size: 9px; }
            .map-warn-panel-title { display: flex; align-items: center; justify-content: space-between; color: rgba(255,255,255,0.3); font-size: 7px; letter-spacing: 1.5px; text-transform: uppercase; cursor: pointer; user-select: none; margin-bottom: 6px; }
            .map-warn-panel.collapsed .map-warn-panel-title { margin-bottom: 0; }
            .map-warn-panel-title:hover { color: rgba(255,255,255,0.55); }
            .map-warn-caret { color: rgba(255,255,255,0.4); font-size: 9px; }
            .map-warn-list { overflow-y: auto; display: flex; flex-direction: column; gap: 1px; }
            .map-warn-row { display: flex; align-items: center; gap: 6px; padding: 3px 4px; border-radius: 3px; cursor: pointer; }
            .map-warn-row:hover { background: rgba(255,255,255,0.06); }
            .map-warn-bar { width: 3px; height: 14px; border-radius: 2px; flex-shrink: 0; }
            .map-warn-type { font-size: 9px; font-weight: 600; flex-shrink: 0; }
            .map-warn-region { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: rgba(255,255,255,0.6); }
            .map-warn-time { font-size: 8px; color: rgba(255,255,255,0.25); font-family: "JetBrains Mono","Fira Code",monospace; flex-shrink: 0; }
            .map-warn-count { font-size: 8px; font-weight: 700; font-family: "JetBrains Mono","Fira Code",monospace; flex-shrink: 0; min-width: 12px; text-align: right; }
            .map-warn-row.sel { background: rgba(255,255,255,0.08); }
            .map-warn-chips { display: flex; flex-wrap: wrap; gap: 3px; margin-bottom: 6px; }
            .map-warn-chip { background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.1); border-radius: 3px; color: rgba(255,255,255,0.4); cursor: pointer; font-size: 8px; font-family: inherit; padding: 1px 5px; letter-spacing: 0.5px; transition: all 0.15s; }
            .map-warn-chip:hover { color: rgba(255,255,255,0.7); border-color: rgba(255,255,255,0.25); }
            .map-warn-chip.sel { background: rgba(0,255,136,0.08); border-color: rgba(0,255,136,0.35); color: #00ff88; }

            /* 雨滴形预警标记 + 降雨动画 */
            .map-warn-drop-icon svg { filter: drop-shadow(0 0 4px rgba(255,138,128,0.4)); }
            .map-warn-drop-icon path { animation: warn-drop-pulse 2.5s ease-in-out infinite; }
            .map-warn-drop-icon .rain-streak { animation: rain-fall 1.6s linear infinite; opacity: 0; }
            .map-warn-drop-icon .rain-streak.s2 { animation-delay: 0.8s; }
            @keyframes warn-drop-pulse { 0%,100% { opacity: 0.7; } 50% { opacity: 1; } }
            @keyframes rain-fall {
              0% { transform: translateY(0); opacity: 0; }
              20% { opacity: 0.75; }
              60% { opacity: 0.4; }
              100% { transform: translateY(11px); opacity: 0; }
            }
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
