import { useEffect, useState } from 'react'
import {
  Button,
  Input,
  Modal,
  Slider,
  Space,
  Upload,
  message as antdMessage,
} from 'antd'
import { CameraOutlined, CloseCircleFilled, ThunderboltOutlined } from '@ant-design/icons'
import { chatApi } from '@/api/chat'
import { agentConfigApi } from '@/api/agentConfig'
import { personaApi, type Persona, type PersonaPayload } from '@/api/personas'
import { AuthenticatedImage } from '@/components/AuthenticatedImage'
import { personaGradientCss, personaInitial } from './personaGradient'

interface Props {
  open: boolean
  persona: Persona | null // null = 新建
  onClose: () => void
  onSaved: () => void
}

export default function PersonaEditModal({ open, persona, onClose, onSaved }: Props) {
  const [name, setName] = useState('')
  const [prompt, setPrompt] = useState('')
  const [temperature, setTemperature] = useState(0.7)
  const [avatarKey, setAvatarKey] = useState<string | null>(null)
  const [avatarUrl, setAvatarUrl] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [optimizing, setOptimizing] = useState(false)

  useEffect(() => {
    if (open) {
      setName(persona?.name ?? '')
      setPrompt(persona?.system_prompt ?? '')
      setTemperature(persona?.temperature ?? 0.7)
      setAvatarKey(persona?.avatar_key ?? null)
      setAvatarUrl(persona?.avatar_url ?? null)
    }
  }, [open, persona])

  const onUpload = async (file: File) => {
    setUploading(true)
    try {
      const { data } = await chatApi.uploadImage(file)
      setAvatarKey(data.file_key)
      setAvatarUrl(data.url)
    } catch (e) {
      antdMessage.error((e as Error).message)
    } finally {
      setUploading(false)
    }
    return false
  }

  const onOptimize = async () => {
    const raw = prompt.trim()
    if (!raw) {
      antdMessage.warning('请先填写人设提示词')
      return
    }
    setOptimizing(true)
    try {
      const { data } = await agentConfigApi.optimizePrompt(raw)
      setPrompt(data.optimized)
      antdMessage.success('已优化，可继续微调')
    } catch (e) {
      antdMessage.error((e as Error).message)
    } finally {
      setOptimizing(false)
    }
  }

  const onSave = async () => {
    if (!name.trim()) {
      antdMessage.warning('请填写角色名')
      return
    }
    const payload: PersonaPayload = {
      name: name.trim(),
      avatar_key: avatarKey ?? '',
      system_prompt: prompt,
      temperature,
    }
    setSaving(true)
    try {
      if (persona) {
        await personaApi.update(persona.id, payload)
        antdMessage.success('已保存')
      } else {
        await personaApi.create(payload)
        antdMessage.success('已创建')
      }
      onSaved()
      onClose()
    } catch (e) {
      antdMessage.error((e as Error).message)
    } finally {
      setSaving(false)
    }
  }

  const grad = personaGradientCss(name || '?')

  return (
    <Modal
      open={open}
      onCancel={onClose}
      onOk={onSave}
      confirmLoading={saving}
      okText="保存"
      cancelText="取消"
      title={persona ? '编辑角色' : '打造你的角色'}
      width={680}
      className="persona-modal"
      styles={{ body: { paddingTop: 12 } }}
    >
      <div className="persona-edit-grid">
        {/* 左：头像 + 名称 */}
        <div className="persona-edit-left">
          <Upload
            accept="image/*"
            showUploadList={false}
            beforeUpload={onUpload as never}
            disabled={uploading}
          >
            <div className="persona-upload" style={{ background: grad }}>
              {avatarUrl ? (
                <AuthenticatedImage
                  src={avatarUrl}
                  alt="头像"
                  style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                />
              ) : (
                <span className="persona-upload-initial">
                  {name.trim() ? personaInitial(name) : <CameraOutlined />}
                </span>
              )}
              <div className="persona-upload-mask">
                <CameraOutlined /> {uploading ? '上传中' : '上传头像'}
              </div>
            </div>
          </Upload>
          {avatarUrl && (
            <Button
              type="text"
              size="small"
              danger
              icon={<CloseCircleFilled />}
              onClick={() => {
                setAvatarKey(null)
                setAvatarUrl(null)
              }}
            >
              移除头像
            </Button>
          )}
          <div className="persona-upload-tip">不上传则该角色不显示 AI 头像</div>
        </div>

        {/* 右：名称 + 提示词 + 温度 */}
        <div className="persona-edit-right">
          <div className="persona-field-label">角色名</div>
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="例如：周杰伦 / 严谨助理 / 特朗普"
            maxLength={64}
          />

          <div className="persona-field-label" style={{ marginTop: 14 }}>
            <Space>
              <span>人设提示词</span>
              <Button
                size="small"
                type="link"
                icon={<ThunderboltOutlined />}
                loading={optimizing}
                onClick={onOptimize}
                style={{ padding: 0 }}
              >
                优化
              </Button>
            </Space>
          </div>
          <Input.TextArea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            autoSize={{ minRows: 5, maxRows: 12 }}
            placeholder="描述这个角色的身份、说话风格、口头禅等。例如：你是周杰伦，说话随性幽默，偶尔哼几句歌词，然后点击优化即可生成完整提示词…"
            maxLength={4000}
          />

          <div className="persona-field-label" style={{ marginTop: 14 }}>
            温度（创造性）
          </div>
          <Slider
            min={0}
            max={2}
            step={0.1}
            value={temperature}
            onChange={setTemperature}
            marks={{ 0: '严谨', 1: '平衡', 2: '发散' }}
          />
        </div>
      </div>
    </Modal>
  )
}
