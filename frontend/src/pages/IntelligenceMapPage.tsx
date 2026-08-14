import { useEffect, useState, useRef } from 'react'
import { Tag, Skeleton, Tooltip, Spin } from 'antd'
import {
  AimOutlined, GlobalOutlined, ThunderboltOutlined,
  ReloadOutlined, EnvironmentOutlined,
} from '@ant-design/icons'
import { MapContainer, TileLayer, CircleMarker, Popup, useMap } from 'react-leaflet'
import L from 'leaflet'
import { dashboardAPI } from '../services/api'
import 'leaflet/dist/leaflet.css'

// ══════════════════════════════════════════════════
// Types
// ══════════════════════════════════════════════════

interface GeoSignal {
  lat: number
  lng: number
  platform: string
  platform_label: string
  color: string
  category: string
  count: number
  title: string
  summary: string
}

interface GeoSignalsResponse {
  signals: GeoSignal[]
  total_signals: number
  platforms_covered: number
  regions_covered: number
}

// ══════════════════════════════════════════════════
// Platform icons (emoji per platform)
// ══════════════════════════════════════════════════

const PLATFORM_ICONS: Record<string, string> = {
  x: '𝕏', youtube: '▶', xiaohongshu: '红', douyin: '抖',
  weibo: '微', bilibili: 'B', reddit: 'R', toutiao: '头',
  website: 'WWW',
}

const PLATFORM_LABELS_FULL: Record<string, string> = {
  x: 'X (Twitter)', youtube: 'YouTube', xiaohongshu: '小红书',
  douyin: '抖音', weibo: '微博', bilibili: 'B站',
  reddit: 'Reddit', toutiao: '今日头条', website: '网站监测',
}

const CATEGORY_COLORS: Record<string, string> = {
  Politics: '#F59E0B', Economy: '#3B82F6', Tech: '#A78BFA',
  Security: '#EF4444', Society: '#22C55E', Culture: '#EC4899',
  General: '#6B7280',
}

// ══════════════════════════════════════════════════
// FitBoundsOnLoad — auto-zoom to fit all markers
// ══════════════════════════════════════════════════

function FitBoundsOnLoad({ signals }: { signals: GeoSignal[] }) {
  const map = useMap()
  const fitted = useRef(false)

  useEffect(() => {
    if (signals.length === 0 || fitted.current) return
    const bounds = L.latLngBounds(signals.map(s => [s.lat, s.lng] as L.LatLngTuple))
    if (bounds.isValid()) {
      map.fitBounds(bounds, { padding: [40, 40], maxZoom: 8 })
    }
    fitted.current = true
  }, [signals, map])

  return null
}

// ══════════════════════════════════════════════════
// PulseRing — outer ring for each marker
// ══════════════════════════════════════════════════

function PulseRing({ lat, lng, color, size }: {
  lat: number; lng: number; color: string; size: number
}) {
  return (
    <CircleMarker
      center={[lat, lng]}
      radius={size * 1.8}
      pathOptions={{
        color: color,
        weight: 1,
        opacity: 0.2,
        fillColor: 'transparent',
        fillOpacity: 0,
      }}
    />
  )
}

// ══════════════════════════════════════════════════
// SignalMarker — single geo intel point
// ══════════════════════════════════════════════════

function SignalMarker({ signal: s }: { signal: GeoSignal }) {
  const size = Math.max(7, Math.min(20, Math.sqrt(s.count) * 3))
  const catColor = CATEGORY_COLORS[s.category] || CATEGORY_COLORS.General

  return (
    <>
      <CircleMarker
        center={[s.lat, s.lng]}
        radius={size}
        pathOptions={{
          fillColor: s.color,
          color: s.color,
          weight: 1.5,
          opacity: 0.55,
          fillOpacity: 0.3,
        }}
      >
        <Popup>
          <div style={{ minWidth: 230, padding: 2, fontFamily: "'JetBrains Mono', 'Fira Code', monospace" }}>
            {/* Header row */}
            <div style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              marginBottom: 8,
            }}>
              <span style={{
                display: 'inline-flex', alignItems: 'center', gap: 4,
                padding: '1px 7px', borderRadius: 3,
                background: `${s.color}18`, color: s.color,
                border: `1px solid ${s.color}30`,
                fontSize: 10, fontWeight: 600,
              }}>
                <span>{PLATFORM_ICONS[s.platform] || '?'}</span>
                {PLATFORM_LABELS_FULL[s.platform] || s.platform_label}
              </span>
              <span style={{
                display: 'inline-flex', alignItems: 'center', gap: 3,
                padding: '1px 7px', borderRadius: 3,
                background: `${catColor}15`, color: catColor,
                border: `1px solid ${catColor}30`,
                fontSize: 9, fontWeight: 600,
              }}>
                {s.category}
              </span>
            </div>

            {/* Title */}
            <div style={{
              fontSize: 12, fontWeight: 600, color: '#f0f0f0',
              marginBottom: 4, lineHeight: 1.4,
            }}>
              {s.title}
            </div>

            {/* Summary */}
            <div style={{
              fontSize: 10, color: 'rgba(255,255,255,0.55)',
              lineHeight: 1.6, marginBottom: 8,
            }}>
              {s.summary}
            </div>

            {/* Footer */}
            <div style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              paddingTop: 6, borderTop: '1px solid rgba(255,255,255,0.06)',
            }}>
              <span style={{ fontSize: 9, color: 'rgba(255,255,255,0.3)' }}>
                SIGNALS
              </span>
              <span style={{
                fontSize: 14, fontWeight: 700, color: s.color,
                fontFamily: 'inherit',
              }}>
                {s.count}
              </span>
            </div>
          </div>
        </Popup>
      </CircleMarker>
      <PulseRing lat={s.lat} lng={s.lng} color={s.color} size={size} />
    </>
  )
}

// ══════════════════════════════════════════════════
// MapLegend — color key for the map
// ══════════════════════════════════════════════════

function MapLegend({ signals }: { signals: GeoSignal[] }) {
  // Dedupe platforms present
  const platforms = [...new Map(signals.map(s => [s.platform, { label: s.platform_label, color: s.color }])).entries()]
    .map(([key, val]) => ({ key, ...val }))

  const categories = [...new Set(signals.map(s => s.category))]

  if (platforms.length === 0) return null

  return (
    <div style={{
      position: 'absolute', bottom: 12, left: 12, zIndex: 1000,
      display: 'flex', gap: 16, flexWrap: 'wrap',
      background: 'rgba(15,15,24,0.92)', backdropFilter: 'blur(8px)',
      border: '1px solid rgba(255,255,255,0.08)', borderRadius: 6,
      padding: '8px 14px', fontSize: 10,
    }}>
      {/* Platforms */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        <span style={{ color: 'rgba(255,255,255,0.25)', fontSize: 8, letterSpacing: 1.5, textTransform: 'uppercase', marginBottom: 2 }}>Platforms</span>
        {platforms.map(p => (
          <div key={p.key} style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
            <div style={{ width: 7, height: 7, borderRadius: '50%', background: p.color, boxShadow: `0 0 4px ${p.color}40` }} />
            <span style={{ color: 'rgba(255,255,255,0.5)' }}>{p.label}</span>
          </div>
        ))}
      </div>
      {/* Categories */}
      {categories.length > 1 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          <span style={{ color: 'rgba(255,255,255,0.25)', fontSize: 8, letterSpacing: 1.5, textTransform: 'uppercase', marginBottom: 2 }}>Categories</span>
          {categories.map(cat => (
            <div key={cat} style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
              <div style={{ width: 7, height: 7, borderRadius: 2, background: CATEGORY_COLORS[cat] || CATEGORY_COLORS.General }} />
              <span style={{ color: 'rgba(255,255,255,0.5)' }}>{cat}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ══════════════════════════════════════════════════
// Main Page
// ══════════════════════════════════════════════════

export default function IntelligenceMapPage() {
  const [data, setData] = useState<GeoSignalsResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const fetchData = async () => {
    setLoading(true)
    setError('')
    try {
      const res = await dashboardAPI.geoSignals()
      setData(res.data)
    } catch (err: any) {
      setError(err.response?.data?.detail || '加载失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchData() }, [])

  return (
    <div style={{ minHeight: '100vh', background: '#0a0a0a', margin: -32 }}>
      {/* ═══ TOP BAR ═══ */}
      <div style={{
        display: 'flex', alignItems: 'center', height: 56,
        padding: '0 16px',
        background: 'rgba(15,15,24,0.85)', backdropFilter: 'blur(12px)',
        borderBottom: '1px solid rgba(255,255,255,0.06)', gap: 8,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <GlobalOutlined style={{ color: '#00ff88', fontSize: 18 }} />
          <div style={{
            display: 'flex', flexDirection: 'column',
            fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
          }}>
            <span style={{ fontWeight: 700, fontSize: 13, letterSpacing: 2, color: '#f0f0f0' }}>
              INTEL<span style={{ color: '#00ff88', margin: '0 2px' }}>·</span>MAP
            </span>
            <span style={{ fontSize: 9, color: 'rgba(255,255,255,0.3)', letterSpacing: 2 }}>
              GEOGRAPHIC INTELLIGENCE
            </span>
          </div>
        </div>
      </div>

      {/* ═══ CONTENT ═══ */}
      <div style={{ padding: 12, display: 'flex', flexDirection: 'column', gap: 10 }}>

        {/* ── KPI Row ── */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5,1fr)', gap: 10 }}>
          {/* KPI 1 */}
          <div style={{
            background: '#0f0f18', border: '1px solid rgba(255,255,255,0.06)',
            borderRadius: 6, overflow: 'hidden',
          }}>
            <div style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              padding: '8px 12px', borderBottom: '1px solid rgba(255,255,255,0.04)',
            }}>
              <span style={{ fontSize: 9, color: 'rgba(255,255,255,0.3)', textTransform: 'uppercase', letterSpacing: 2, fontWeight: 600 }}>情报信号</span>
              <span style={{ fontSize: 8, color: 'rgba(255,255,255,0.15)' }}>SIGNALS</span>
            </div>
            <div style={{ padding: '14px' }}>
              {loading ? (
                <Skeleton.Input active size="small" style={{ width: 50, height: 36 }} />
              ) : (
                <span style={{ fontSize: 32, fontWeight: 700, color: '#00ff88', fontFamily: "'JetBrains Mono', monospace", lineHeight: 1 }}>
                  {data?.total_signals ?? '—'}
                </span>
              )}
            </div>
          </div>
          {/* KPI 2 */}
          <div style={{
            background: '#0f0f18', border: '1px solid rgba(255,255,255,0.06)',
            borderRadius: 6, overflow: 'hidden',
          }}>
            <div style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              padding: '8px 12px', borderBottom: '1px solid rgba(255,255,255,0.04)',
            }}>
              <span style={{ fontSize: 9, color: 'rgba(255,255,255,0.3)', textTransform: 'uppercase', letterSpacing: 2, fontWeight: 600 }}>覆盖平台</span>
              <span style={{ fontSize: 8, color: 'rgba(255,255,255,0.15)' }}>PLATFORMS</span>
            </div>
            <div style={{ padding: '14px' }}>
              {loading ? (
                <Skeleton.Input active size="small" style={{ width: 50, height: 36 }} />
              ) : (
                <span style={{ fontSize: 32, fontWeight: 700, color: '#60A5FA', fontFamily: "'JetBrains Mono', monospace", lineHeight: 1 }}>
                  {data?.platforms_covered ?? '—'}
                </span>
              )}
            </div>
          </div>
          {/* KPI 3 */}
          <div style={{
            background: '#0f0f18', border: '1px solid rgba(255,255,255,0.06)',
            borderRadius: 6, overflow: 'hidden',
          }}>
            <div style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              padding: '8px 12px', borderBottom: '1px solid rgba(255,255,255,0.04)',
            }}>
              <span style={{ fontSize: 9, color: 'rgba(255,255,255,0.3)', textTransform: 'uppercase', letterSpacing: 2, fontWeight: 600 }}>覆盖地区</span>
              <span style={{ fontSize: 8, color: 'rgba(255,255,255,0.15)' }}>REGIONS</span>
            </div>
            <div style={{ padding: '14px' }}>
              {loading ? (
                <Skeleton.Input active size="small" style={{ width: 50, height: 36 }} />
              ) : (
                <span style={{ fontSize: 32, fontWeight: 700, color: '#F59E0B', fontFamily: "'JetBrains Mono', monospace", lineHeight: 1 }}>
                  {data?.regions_covered ?? '—'}
                </span>
              )}
            </div>
          </div>
          {/* KPI 4 — 最近数据源 */}
          <div style={{
            background: '#0f0f18', border: '1px solid rgba(255,255,255,0.06)',
            borderRadius: 6, overflow: 'hidden',
          }}>
            <div style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              padding: '8px 12px', borderBottom: '1px solid rgba(255,255,255,0.04)',
            }}>
              <span style={{ fontSize: 9, color: 'rgba(255,255,255,0.3)', textTransform: 'uppercase', letterSpacing: 2, fontWeight: 600 }}>数据来源</span>
              <span style={{ fontSize: 8, color: 'rgba(255,255,255,0.15)' }}>SOURCE</span>
            </div>
            <div style={{ padding: '14px' }}>
              <span style={{ fontSize: 18, fontWeight: 700, color: 'rgba(255,255,255,0.6)', fontFamily: "'JetBrains Mono', monospace", lineHeight: 1 }}>
                监测 + 话题
              </span>
              <div style={{ fontSize: 9, color: 'rgba(255,255,255,0.2)', marginTop: 4 }}>
                近期 50条结果 + 30条热搜
              </div>
            </div>
          </div>
          {/* KPI 5 — 刷新 */}
          <div style={{
            background: '#0f0f18', border: '1px solid rgba(255,255,255,0.06)',
            borderRadius: 6, overflow: 'hidden', display: 'flex',
            alignItems: 'center', justifyContent: 'center', cursor: 'pointer',
          }} onClick={fetchData}>
            <div style={{ textAlign: 'center' }}>
              <ReloadOutlined spin={loading} style={{ fontSize: 24, color: 'rgba(255,255,255,0.4)', marginBottom: 6 }} />
              <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.35)', fontWeight: 600, letterSpacing: 1 }}>
                刷新数据
              </div>
            </div>
          </div>
        </div>

        {/* ── Map Card ── */}
        <div style={{
          background: '#0f0f18', border: '1px solid rgba(255,255,255,0.06)',
          borderRadius: 6, overflow: 'hidden', position: 'relative',
        }}>
          {/* Map Header */}
          <div style={{
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            padding: '6px 10px', borderBottom: '1px solid rgba(255,255,255,0.04)',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              <EnvironmentOutlined style={{ color: 'rgba(255,255,255,0.2)', fontSize: 12 }} />
              <span style={{ fontSize: 9, color: 'rgba(255,255,255,0.25)', textTransform: 'uppercase', letterSpacing: 1.5, fontWeight: 600 }}>
                Global Intelligence Map
              </span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              {!loading && !error && (
                <span style={{ fontSize: 8, color: 'rgba(255,255,255,0.12)' }}>
                  {data?.total_signals} signals · {data?.regions_covered} regions
                </span>
              )}
              <span style={{ fontSize: 8, color: 'rgba(255,255,255,0.12)' }}>live</span>
            </div>
          </div>

          {/* Map Container */}
          <div style={{ height: 500, position: 'relative', background: '#0a0a0a' }}>
            {loading && (
              <div style={{
                position: 'absolute', inset: 0, zIndex: 1001,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                background: 'rgba(10,10,10,0.7)',
              }}>
                <Spin size="large" />
              </div>
            )}
            {error && (
              <div style={{
                position: 'absolute', inset: 0, zIndex: 1001,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                background: 'rgba(10,10,10,0.7)', flexDirection: 'column', gap: 12,
              }}>
                <span style={{ color: '#EF4444', fontSize: 13, fontWeight: 500 }}>{error}</span>
                <button
                  onClick={fetchData}
                  style={{
                    background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.1)',
                    borderRadius: 4, padding: '6px 16px', color: '#e0e0e0',
                    cursor: 'pointer', fontSize: 12, fontFamily: 'inherit',
                  }}
                >
                  重试
                </button>
              </div>
            )}
            {!loading && !error && (
              <MapContainer
                center={[28, 105]}
                zoom={2}
                scrollWheelZoom={true}
                zoomControl={true}
                attributionControl={false}
                style={{ height: '100%', width: '100%', background: '#0a0a0a' }}
              >
                <TileLayer
                  url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
                  maxZoom={10}
                  minZoom={2}
                />
                {data?.signals.map((s, i) => (
                  <SignalMarker key={`${s.lat}-${s.lng}-${s.platform}-${i}`} signal={s} />
                ))}
                {data?.signals && data.signals.length > 0 && (
                  <FitBoundsOnLoad signals={data.signals} />
                )}
              </MapContainer>
            )}
          </div>

          {/* Map Legend */}
          {!loading && !error && data?.signals && (
            <MapLegend signals={data.signals} />
          )}
        </div>

        {/* ── Signal List (compact table) ── */}
        {!loading && !error && data && data.signals.length > 0 && (
          <div style={{
            background: '#0f0f18', border: '1px solid rgba(255,255,255,0.06)',
            borderRadius: 6, overflow: 'hidden',
          }}>
            <div style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              padding: '6px 10px', borderBottom: '1px solid rgba(255,255,255,0.04)',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                <ThunderboltOutlined style={{ color: 'rgba(255,255,255,0.2)', fontSize: 12 }} />
                <span style={{ fontSize: 9, color: 'rgba(255,255,255,0.25)', textTransform: 'uppercase', letterSpacing: 1.5, fontWeight: 600 }}>
                  Signal Intelligence Feed
                </span>
              </div>
              <span style={{ fontSize: 8, color: 'rgba(255,255,255,0.12)' }}>
                {data.signals.length} entries
              </span>
            </div>
            <div style={{ padding: '6px 0', maxHeight: 320, overflow: 'auto' }}>
              <table style={{
                width: '100%', borderCollapse: 'collapse',
                fontSize: 10, fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
              }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                    <th style={{ padding: '6px 10px', textAlign: 'left', color: 'rgba(255,255,255,0.2)', fontSize: 9, fontWeight: 500, letterSpacing: 1, width: 30 }}>#</th>
                    <th style={{ padding: '6px 10px', textAlign: 'left', color: 'rgba(255,255,255,0.2)', fontSize: 9, fontWeight: 500, letterSpacing: 1, width: 70 }}>PLATFORM</th>
                    <th style={{ padding: '6px 10px', textAlign: 'left', color: 'rgba(255,255,255,0.2)', fontSize: 9, fontWeight: 500, letterSpacing: 1, width: 60 }}>CATEGORY</th>
                    <th style={{ padding: '6px 10px', textAlign: 'left', color: 'rgba(255,255,255,0.2)', fontSize: 9, fontWeight: 500, letterSpacing: 1 }}>TITLE</th>
                    <th style={{ padding: '6px 10px', textAlign: 'left', color: 'rgba(255,255,255,0.2)', fontSize: 9, fontWeight: 500, letterSpacing: 1, width: 50 }}>REGION</th>
                    <th style={{ padding: '6px 10px', textAlign: 'right', color: 'rgba(255,255,255,0.2)', fontSize: 9, fontWeight: 500, letterSpacing: 1, width: 50 }}>COUNT</th>
                  </tr>
                </thead>
                <tbody>
                  {data.signals.map((s, i) => {
                    const catColor = CATEGORY_COLORS[s.category] || CATEGORY_COLORS.General
                    return (
                      <tr
                        key={`${s.lat}-${s.lng}-${s.platform}-${i}`}
                        style={{
                          borderBottom: '1px solid rgba(255,255,255,0.02)',
                          transition: 'background 0.15s',
                        }}
                        onMouseEnter={e => e.currentTarget.style.background = 'rgba(255,255,255,0.02)'}
                        onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                      >
                        <td style={{ padding: '8px 10px', color: 'rgba(255,255,255,0.15)', fontSize: 10 }}>{i + 1}</td>
                        <td style={{ padding: '8px 10px' }}>
                          <span style={{
                            display: 'inline-flex', alignItems: 'center', gap: 3,
                            padding: '1px 6px', borderRadius: 3,
                            background: `${s.color}14`, color: s.color,
                            border: `1px solid ${s.color}25`,
                            fontSize: 9, fontWeight: 600,
                          }}>
                            {PLATFORM_ICONS[s.platform] || '?'} {s.platform_label}
                          </span>
                        </td>
                        <td style={{ padding: '8px 10px' }}>
                          <span style={{
                            display: 'inline-flex', alignItems: 'center',
                            padding: '1px 6px', borderRadius: 3,
                            background: `${catColor}12`, color: catColor,
                            fontSize: 9, fontWeight: 500,
                          }}>
                            {s.category}
                          </span>
                        </td>
                        <td style={{ padding: '8px 10px' }}>
                          <Tooltip title={s.title}>
                            <span style={{
                              color: 'rgba(255,255,255,0.6)', fontSize: 10,
                              overflow: 'hidden', textOverflow: 'ellipsis',
                              whiteSpace: 'nowrap', display: 'block', maxWidth: 400,
                            }}>
                              {s.title}
                            </span>
                          </Tooltip>
                        </td>
                        <td style={{ padding: '8px 10px', color: 'rgba(255,255,255,0.35)', fontSize: 10 }}>
                          {s.summary.split('·')[0]?.trim().slice(0, 30) || '—'}
                        </td>
                        <td style={{
                          padding: '8px 10px', textAlign: 'right',
                          fontSize: 12, fontWeight: 700, color: s.color, fontFamily: 'inherit',
                        }}>
                          {s.count}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
