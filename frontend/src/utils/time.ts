// 统一时间工具：监控贴文的 published_at 由后端存为 naive UTC（无时区后缀的 ISO 字符串）。
// 前端一律按北京时间（Asia/Shanghai）展示，避免浏览器把 naive 时间当作本地时间解析导致偏差。

/** 解析后端时间字符串为 Date。无时区后缀 → 视为 UTC；带 Z/±HH:MM → 原样解析。 */
export function toBeijingDate(iso?: string | null): Date | null {
  if (!iso) return null
  const s = String(iso)
  const hasTz = /Z$|[+-]\d{2}:?\d{2}$/.test(s)
  const d = new Date(hasTz ? s : s + 'Z')
  return Number.isNaN(d.getTime()) ? null : d
}

const FMT: Intl.DateTimeFormatOptions = {
  timeZone: 'Asia/Shanghai',
  hourCycle: 'h23',
  year: 'numeric', month: '2-digit', day: '2-digit',
  hour: '2-digit', minute: '2-digit',
}

/** 格式化为「YYYY年MM月DD日 HH:mm」（北京时间）。 */
export function formatBeijingTime(iso?: string | null): string {
  const d = toBeijingDate(iso)
  if (!d) return ''
  const parts = new Intl.DateTimeFormat('zh-CN', FMT).formatToParts(d)
  const get = (t: string) => parts.find(p => p.type === t)?.value ?? ''
  return `${get('year')}年${get('month')}月${get('day')}日 ${get('hour')}:${get('minute')}`
}

/** 格式化为「YYYY/MM/DD」（北京时间）。 */
export function formatBeijingDate(iso?: string | null): string {
  const d = toBeijingDate(iso)
  if (!d) return '-'
  const parts = new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai',
    hourCycle: 'h23',
    year: 'numeric', month: '2-digit', day: '2-digit',
  }).formatToParts(d)
  const get = (t: string) => parts.find(p => p.type === t)?.value ?? ''
  return `${get('year')}/${get('month')}/${get('day')}`
}
