import { useState } from 'react'
import { Modal, Input, Button, message, Popconfirm, Typography, Divider, Empty } from 'antd'
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons'
import { tagsAPI } from '../services/api'
import { TAG_COLORS, TagPill, ColorDot } from './TagPill'

const { Text } = Typography

export interface ManagedTag {
  id: number
  name: string
  color: string
  is_preset: boolean
  target_count: number
}

// 标签库管理：改名（回车/失焦提交）、点色板换色、删除（连带从账号移除）、新建
export function TagManageModal({
  open,
  onClose,
  tags,
  onChanged,
}: {
  open: boolean
  onClose: () => void
  tags: ManagedTag[]
  onChanged: () => void
}) {
  const [newName, setNewName] = useState('')
  const [newColor, setNewColor] = useState(TAG_COLORS[0])
  const [creating, setCreating] = useState(false)

  const commitRename = async (tag: ManagedTag, raw: string) => {
    const name = raw.trim()
    if (!name || name === tag.name) return
    try {
      await tagsAPI.update(tag.id, { name })
      message.success(`已重命名为「${name}」`)
      onChanged()
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '重命名失败')
    }
  }

  const commitColor = async (tag: ManagedTag, color: string) => {
    if (color === tag.color) return
    try {
      await tagsAPI.update(tag.id, { color })
      onChanged()
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '颜色修改失败')
    }
  }

  const handleDelete = async (tag: ManagedTag) => {
    try {
      await tagsAPI.remove(tag.id)
      message.success(`已删除标签「${tag.name}」`)
      onChanged()
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '删除失败')
    }
  }

  const handleCreate = async () => {
    const name = newName.trim()
    if (!name) {
      message.warning('请输入标签名称')
      return
    }
    setCreating(true)
    try {
      await tagsAPI.create({ name, color: newColor })
      message.success(`已创建标签「${name}」`)
      setNewName('')
      onChanged()
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '创建失败')
    } finally {
      setCreating(false)
    }
  }

  return (
    <Modal
      title="标签管理"
      open={open}
      onCancel={onClose}
      footer={null}
      width={600}
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 4 }}>
        <Text type="secondary" style={{ fontSize: 13 }}>
          标签可用于标记账号类别（如涉T/涉Z），一个账号可打多个标签；改名/换色会同步到所有账号卡片。
        </Text>

        {tags.length === 0 ? (
          <Empty description="暂无标签" image={Empty.PRESENTED_IMAGE_SIMPLE} style={{ margin: '12px 0' }} />
        ) : (
          tags.map(tag => (
            <div key={tag.id} style={{
              display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap',
              padding: '10px 14px', borderRadius: 10,
              background: 'var(--surface-1)', border: '1px solid var(--border)',
            }}>
              <TagPill tag={tag} style={{ minWidth: 76 }} />
              <Input
                size="small"
                maxLength={10}
                defaultValue={tag.name}
                style={{ width: 132, borderRadius: 8 }}
                onPressEnter={e => (e.target as HTMLInputElement).blur()}
                onBlur={e => commitRename(tag, e.target.value)}
              />
              <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
                {TAG_COLORS.map(c => (
                  <ColorDot key={c} color={c} active={c === tag.color} onClick={() => commitColor(tag, c)} />
                ))}
              </div>
              <Text style={{ fontSize: 12, color: 'var(--text-muted)', marginLeft: 'auto', whiteSpace: 'nowrap' }}>
                {tag.target_count > 0 ? `${tag.target_count} 个账号` : '未使用'}
              </Text>
              <Popconfirm
                title={`删除标签「${tag.name}」？`}
                description={tag.target_count > 0 ? `该标签已用于 ${tag.target_count} 个账号，删除后将一并移除。` : undefined}
                okButtonProps={{ danger: true }}
                onConfirm={() => handleDelete(tag)}
              >
                <Button type="text" size="small" danger icon={<DeleteOutlined />} />
              </Popconfirm>
            </div>
          ))
        )}

        <Divider style={{ margin: '6px 0 4px 0' }} />

        <div style={{
          display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap',
          padding: '12px 14px', borderRadius: 10,
          background: 'var(--surface-1)', border: '1px dashed var(--border-strong)',
        }}>
          <Input
            size="small"
            maxLength={10}
            value={newName}
            onChange={e => setNewName(e.target.value)}
            onPressEnter={handleCreate}
            placeholder="新标签名称（最多10字）"
            style={{ width: 150, borderRadius: 8 }}
          />
          <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
            {TAG_COLORS.map(c => (
              <ColorDot key={c} color={c} active={c === newColor} onClick={() => setNewColor(c)} />
            ))}
          </div>
          <Button
            size="small" type="primary" icon={<PlusOutlined />}
            loading={creating}
            onClick={handleCreate}
            style={{ marginLeft: 'auto', height: 32 }}
          >
            新建标签
          </Button>
        </div>
      </div>
    </Modal>
  )
}
