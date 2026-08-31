import { useEffect, useState } from 'react'
import { Checkbox, Input, Modal, message } from 'antd'
import { personaApi, type Persona } from '@/api/personas'
import {
  personaGroupApi,
  type PersonaGroup,
  type PersonaGroupPayload,
} from '@/api/personaGroups'

interface Props {
  open: boolean
  group: PersonaGroup | null // null = 新建
  onClose: () => void
  onSaved: () => void
}

const ICONS = ['🎭', '📈', '🧳', '💼', '🧠', '❤️', '🎬', '🏠', '⚖️', '🎓']

export default function PersonaGroupEditModal({ open, group, onClose, onSaved }: Props) {
  const [personas, setPersonas] = useState<Persona[]>([])
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [icon, setIcon] = useState('🎭')
  const [selected, setSelected] = useState<string[]>([])
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    if (!open) return
    // 只从「单个角色」里选成员（不含仅卡组成员，保持可控）
    personaApi
      .list()
      .then((r) => setPersonas(r.data))
      .catch(() => {})
    if (group) {
      setName(group.name)
      setDescription(group.description)
      setIcon(group.icon || '🎭')
      setSelected(group.member_persona_ids)
    } else {
      setName('')
      setDescription('')
      setIcon('🎭')
      setSelected([])
    }
  }, [open, group])

  const toggle = (id: string) => {
    setSelected((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    )
  }

  const onSubmit = async () => {
    if (!name.trim()) {
      message.warning('请填写卡组名称')
      return
    }
    if (selected.length < 2 || selected.length > 5) {
      message.warning('请选择 2~5 个角色')
      return
    }
    setSubmitting(true)
    try {
      const payload: PersonaGroupPayload = {
        name: name.trim(),
        description: description.trim(),
        icon,
        member_persona_ids: selected,
      }
      if (group) {
        await personaGroupApi.update(group.id, payload)
        message.success('已保存')
      } else {
        await personaGroupApi.create(payload)
        message.success('已创建')
      }
      onSaved()
      onClose()
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal
      open={open}
      title={group ? '编辑卡组' : '新建角色卡组'}
      onCancel={onClose}
      onOk={onSubmit}
      okText={group ? '保存' : '创建'}
      cancelText="取消"
      confirmLoading={submitting}
      width={560}
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16, marginTop: 8 }}>
        <div>
          <div className="pg-field-label">卡组名称</div>
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="如：我的投研天团"
            maxLength={64}
          />
        </div>
        <div>
          <div className="pg-field-label">图标</div>
          <div className="pg-icon-row">
            {ICONS.map((ic) => (
              <button
                key={ic}
                className={`pg-icon-btn ${icon === ic ? 'pg-icon-btn--on' : ''}`}
                onClick={() => setIcon(ic)}
                type="button"
              >
                {ic}
              </button>
            ))}
          </div>
        </div>
        <div>
          <div className="pg-field-label">描述（可选）</div>
          <Input.TextArea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="一句话说明这组角色是干嘛的"
            autoSize={{ minRows: 2, maxRows: 3 }}
            maxLength={200}
          />
        </div>
        <div>
          <div className="pg-field-label">
            选择成员（2~5 个，已选 {selected.length}）
          </div>
          {personas.length === 0 ? (
            <div style={{ color: '#98a2b3', fontSize: 13 }}>
              还没有单个角色，请先到「单个角色」里创建
            </div>
          ) : (
            <div className="pg-member-grid">
              {personas.map((p) => (
                <label
                  key={p.id}
                  className={`pg-member-item ${
                    selected.includes(p.id) ? 'pg-member-item--on' : ''
                  }`}
                >
                  <Checkbox
                    checked={selected.includes(p.id)}
                    onChange={() => toggle(p.id)}
                  />
                  <span className="pg-member-name">{p.name}</span>
                </label>
              ))}
            </div>
          )}
        </div>
      </div>
    </Modal>
  )
}
