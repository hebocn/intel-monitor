import { CloseOutlined } from '@ant-design/icons'
import type { CSSProperties, MouseEvent } from 'react'

// 标签固定色板（与后端 schemas/tag.py ALLOWED_TAG_COLORS 保持一致）
export const TAG_COLORS = [
  '#22C55E', '#3B82F6', '#06B6D4', '#A78BFA',
  '#F59E0B', '#F43F5E', '#EC4899', '#94A3B8',
]

export interface TagItem {
  id: number
  name: string
  color: string
}

export function TagPill({
  tag,
  closable = false,
  onClose,
  onClick,
  style,
}: {
  tag: Pick<TagItem, 'name' | 'color'>
  closable?: boolean
  onClose?: (e: MouseEvent<any>) => void
  onClick?: (e: MouseEvent<any>) => void
  style?: CSSProperties
}) {
  const { color } = tag
  return (
    <span
      onClick={onClick}
      style={{
        display: 'inline-flex', alignItems: 'center', gap: 5,
        padding: '3px 10px', borderRadius: 12,
        background: `${color}16`,
        border: `1px solid ${color}33`,
        color, fontSize: 11, fontWeight: 700,
        fontFamily: 'var(--font-body)',
        lineHeight: '16px',
        whiteSpace: 'nowrap',
        cursor: onClick ? 'pointer' : undefined,
        ...style,
      }}
    >
      <span style={{ width: 6, height: 6, borderRadius: '50%', background: color, flexShrink: 0 }} />
      {tag.name}
      {closable && (
        <CloseOutlined
          onClick={e => { e.stopPropagation(); onClose?.(e) }}
          style={{ fontSize: 9, marginLeft: 1, opacity: 0.65 }}
        />
      )}
    </span>
  )
}

// 色板圆点（标签管理/新建时选择颜色）
export function ColorDot({
  color,
  active,
  onClick,
}: {
  color: string
  active?: boolean
  onClick?: (e: MouseEvent<any>) => void
}) {
  return (
    <span
      onClick={onClick}
      title={color}
      style={{
        width: 16, height: 16, borderRadius: '50%',
        background: color, cursor: 'pointer', flexShrink: 0,
        boxShadow: active ? `0 0 0 2px var(--surface-1), 0 0 0 4px ${color}` : 'none',
        transition: 'box-shadow 0.15s ease, transform 0.15s ease',
        ...(active ? {} : { opacity: 0.85 }),
      }}
      onMouseEnter={e => { e.currentTarget.style.transform = 'scale(1.15)' }}
      onMouseLeave={e => { e.currentTarget.style.transform = 'scale(1)' }}
    />
  )
}
