import { useState } from 'react'
import { Popover, Input, Button, message, Divider } from 'antd'
import { CheckOutlined, PlusOutlined } from '@ant-design/icons'
import { TAG_COLORS, TagPill, ColorDot, type TagItem } from './TagPill'

// 卡片上的「+ 标签」触发器 + 弹出选择器（勾选/取消勾选即时生效，支持就地新建自定义标签）
export function TagSelectPopover({
  tags,
  selectedIds,
  onChange,
  onCreateTag,
  children,
}: {
  tags: TagItem[]
  selectedIds: number[]
  onChange: (nextIds: number[]) => void
  onCreateTag: (name: string, color: string) => Promise<TagItem | null>
  children: React.ReactElement
}) {
  const [open, setOpen] = useState(false)
  const [newName, setNewName] = useState('')
  const [newColor, setNewColor] = useState(TAG_COLORS[0])
  const [creating, setCreating] = useState(false)

  const toggle = (id: number) => {
    onChange(selectedIds.includes(id) ? selectedIds.filter(x => x !== id) : [...selectedIds, id])
  }

  const handleCreate = async () => {
    const name = newName.trim()
    if (!name) {
      message.warning('请输入标签名称')
      return
    }
    setCreating(true)
    try {
      const tag = await onCreateTag(name, newColor)
      if (tag) {
        onChange([...selectedIds, tag.id])
        setNewName('')
      }
    } finally {
      setCreating(false)
    }
  }

  const content = (
    <div style={{ width: 248, display: 'flex', flexDirection: 'column', gap: 4 }}>
      {tags.length === 0 && (
        <div style={{ padding: '8px 4px', fontSize: 12, color: 'var(--text-muted)' }}>
          暂无标签，可在下方新建
        </div>
      )}
      {tags.map(tag => {
        const selected = selectedIds.includes(tag.id)
        return (
          <div
            key={tag.id}
            onClick={() => toggle(tag.id)}
            style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              gap: 8, padding: '7px 10px', borderRadius: 10,
              cursor: 'pointer',
              background: selected ? `${tag.color}10` : 'transparent',
              border: `1px solid ${selected ? `${tag.color}26` : 'transparent'}`,
              transition: 'all 0.15s ease',
            }}
            onMouseEnter={e => { if (!selected) e.currentTarget.style.background = 'rgba(248,250,252,0.04)' }}
            onMouseLeave={e => { if (!selected) e.currentTarget.style.background = 'transparent' }}
          >
            <TagPill tag={tag} />
            {selected && <CheckOutlined style={{ color: tag.color, fontSize: 12 }} />}
          </div>
        )
      })}

      <Divider style={{ margin: '8px 0 10px 0' }} />

      <Input
        size="small"
        maxLength={10}
        showCount
        value={newName}
        onChange={e => setNewName(e.target.value)}
        onPressEnter={handleCreate}
        placeholder="新建自定义标签"
        style={{ borderRadius: 8 }}
      />
      <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginTop: 10, flexWrap: 'wrap' }}>
        {TAG_COLORS.map(c => (
          <ColorDot key={c} color={c} active={newColor === c} onClick={() => setNewColor(c)} />
        ))}
      </div>
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 10 }}>
        <Button
          size="small" type="primary" icon={<PlusOutlined />}
          loading={creating}
          onClick={handleCreate}
          style={{ height: 30, fontSize: 12 }}
        >
          新建并打上
        </Button>
      </div>
    </div>
  )

  return (
    <Popover
      trigger="click"
      placement="bottomLeft"
      arrow={false}
      open={open}
      onOpenChange={v => { setOpen(v); if (!v) setNewName('') }}
      content={content}
      styles={{ body: { padding: '10px 10px 12px 10px' } }}
    >
      {children}
    </Popover>
  )
}
