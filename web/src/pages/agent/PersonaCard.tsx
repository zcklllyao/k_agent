import { Button, Popconfirm, Tooltip } from 'antd'
import { CheckOutlined, DeleteOutlined, EditOutlined, ThunderboltFilled } from '@ant-design/icons'
import { AuthenticatedImage } from '@/components/AuthenticatedImage'
import type { Persona } from '@/api/personas'
import { personaGradientCss, personaInitial } from './personaGradient'

interface Props {
  persona: Persona
  index: number
  activating?: boolean
  onActivate: (p: Persona) => void
  onEdit: (p: Persona) => void
  onDelete: (p: Persona) => void
}

// 单张角色卡：玻璃拟态 + 头像光晕封面 + 当前生效流光描边
export default function PersonaCard({
  persona,
  index,
  activating,
  onActivate,
  onEdit,
  onDelete,
}: Props) {
  const active = persona.is_active
  const grad = personaGradientCss(persona.name)
  const tempLabel =
    persona.temperature <= 0.4 ? '严谨' : persona.temperature >= 1.2 ? '发散' : '平衡'

  return (
    <div
      className={`persona-card${active ? ' persona-card--active' : ''}`}
      style={{ animationDelay: `${Math.min(index, 12) * 60}ms` }}
    >
      {active && (
        <div className="persona-badge">
          <ThunderboltFilled /> 当前
        </div>
      )}

      {/* 封面：头像 + 光晕底 */}
      <div className="persona-cover" style={{ background: grad }}>
        <div className="persona-cover-glow" style={{ background: grad }} />
        <div className="persona-avatar">
          {persona.avatar_url ? (
            <AuthenticatedImage
              src={persona.avatar_url}
              alt={persona.name}
              style={{ width: '100%', height: '100%', objectFit: 'cover' }}
            />
          ) : (
            <span className="persona-avatar-initial" style={{ background: grad }}>
              {personaInitial(persona.name)}
            </span>
          )}
        </div>
      </div>

      {/* 信息 */}
      <div className="persona-body">
        <div className="persona-name">{persona.name}</div>
        <div className="persona-meta">
          🌡️ {persona.temperature.toFixed(1)} · {tempLabel}
          {!persona.avatar_url && ' · 无头像'}
        </div>
        <div className="persona-desc">
          {persona.system_prompt?.trim() || '未设置人设提示词'}
        </div>
      </div>

      {/* 操作 */}
      <div className="persona-actions">
        <Button
          type={active ? 'default' : 'primary'}
          size="small"
          icon={active ? <CheckOutlined /> : undefined}
          disabled={active}
          loading={activating}
          onClick={() => onActivate(persona)}
          className="persona-apply-btn"
          block
        >
          {active ? '使用中' : '应用'}
        </Button>
        <Tooltip title="编辑">
          <Button size="small" icon={<EditOutlined />} onClick={() => onEdit(persona)} />
        </Tooltip>
        <Popconfirm
          title="删除该角色？"
          okText="删除"
          okButtonProps={{ danger: true }}
          onConfirm={() => onDelete(persona)}
        >
          <Tooltip title="删除">
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Tooltip>
        </Popconfirm>
      </div>
    </div>
  )
}
