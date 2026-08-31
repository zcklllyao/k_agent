import { useEffect, useMemo, useState } from 'react'
import {
  Button,
  Collapse,
  Empty,
  Form,
  Input,
  Modal,
  Popconfirm,
  Select,
  Spin,
  Switch,
  Tag,
  Tooltip,
  Typography,
  message,
} from 'antd'
import {
  ApiOutlined,
  CheckCircleFilled,
  CopyOutlined,
  DeleteOutlined,
  EditOutlined,
  GlobalOutlined,
  KeyOutlined,
  LinkOutlined,
  PlusOutlined,
  StarFilled,
  ThunderboltOutlined,
} from '@ant-design/icons'
import {
  modelApi,
  type ModelConfigItem,
  type ModelConfigPayload,
  type ModelConfigClonePayload,
  type ModelType,
} from '@/api/models'
import ModelConfigModal from './modelConfig/ModelConfigModal'
import {
  CAPABILITY_OPTIONS,
  PROVIDER_LINKS,
  PROVIDER_OPTIONS,
  TYPE_LABEL,
  TYPE_OPTIONS,
} from './modelConfig/constants'

const PROVIDER_LABEL = Object.fromEntries(
  PROVIDER_OPTIONS.map((p) => [p.value, p.label]),
)

// 每种模型类型一套配色 + 分组标题
const TYPE_META: Record<
  ModelType,
  { color: string; bg: string; gradient: string; desc: string }
> = {
  chat: {
    color: '#155EEF',
    bg: '#EEF4FF',
    gradient: 'linear-gradient(135deg, #155EEF 0%, #4E8CFF 100%)',
    desc: '负责对话问答的大语言模型',
  },
  multimodal: {
    color: '#7A5AF8',
    bg: '#F4F1FE',
    gradient: 'linear-gradient(135deg, #7A5AF8 0%, #B69CFF 100%)',
    desc: '能看图理解的多模态模型',
  },
  embedding: {
    color: '#0E9384',
    bg: '#E6F6F4',
    gradient: 'linear-gradient(135deg, #0E9384 0%, #4FD1C5 100%)',
    desc: '把文本转成向量用于检索',
  },
  rerank: {
    color: '#DD6B20',
    bg: '#FEF3E8',
    gradient: 'linear-gradient(135deg, #DD6B20 0%, #F6AD55 100%)',
    desc: '对检索结果重排，提升相关度',
  },
  websearch: {
    color: '#0BA5EC',
    bg: '#E7F6FE',
    gradient: 'linear-gradient(135deg, #0BA5EC 0%, #5CC9F5 100%)',
    desc: '联网搜索实时信息',
  },
  asr: {
    color: '#EC4899',
    bg: '#FCE7F3',
    gradient: 'linear-gradient(135deg, #EC4899 0%, #F9A8D4 100%)',
    desc: '语音识别，把语音转成文字',
  },
  verifier: {
    color: '#7A5AF8',
    bg: '#F4F1FE',
    gradient: 'linear-gradient(135deg, #7A5AF8 0%, #A78BFA 100%)',
    desc: '深度研究质量审稿的独立评判模型',
  },
}

const TYPE_ORDER: ModelType[] = [
  'chat',
  'multimodal',
  'embedding',
  'rerank',
  'websearch',
  'asr',
  'verifier',
]

const CAP_LABEL: Record<string, string> = {
  function_call: '工具调用',
  vision: '图片理解',
}

// 密钥掩码归一化：统一显示为「固定圆点 + 真实尾部」，避免长短不一撑乱卡片
function normalizeKey(masked: string): string {
  if (!masked) return '-'
  // 取末尾连续的非掩码字符作为可见尾部（后端掩码用 * 号）
  const tail = masked.replace(/\*+/g, '').slice(-4)
  return `${'•'.repeat(12)}${tail}`
}

export default function ModelConfigPage() {
  const [list, setList] = useState<ModelConfigItem[]>([])
  const [loading, setLoading] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<ModelConfigItem | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [testingId, setTestingId] = useState<string | null>(null)
  const [cloneSource, setCloneSource] = useState<ModelConfigItem | null>(null)
  const [cloneSubmitting, setCloneSubmitting] = useState(false)
  const [cloneForm] = Form.useForm<ModelConfigClonePayload>()

  const load = async () => {
    setLoading(true)
    try {
      const { data } = await modelApi.list()
      setList(data)
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const openCreate = () => {
    setEditing(null)
    setModalOpen(true)
  }

  const openEdit = (item: ModelConfigItem) => {
    setEditing(item)
    setModalOpen(true)
  }

  const openClone = (item: ModelConfigItem) => {
    const targetType = TYPE_ORDER.find((type) => type !== item.type) ?? 'multimodal'
    setCloneSource(item)
    cloneForm.setFieldsValue({
      target_type: targetType,
      name: `${item.name} - ${TYPE_LABEL[targetType]}`,
      model_name: item.model_name,
      capability: item.capability,
      is_default: false,
    })
  }

  const onClone = async (values: ModelConfigClonePayload) => {
    if (!cloneSource) return
    setCloneSubmitting(true)
    try {
      await modelApi.clone(cloneSource.id, values)
      message.success(`已复制到「${TYPE_LABEL[values.target_type]}」配置`)
      setCloneSource(null)
      cloneForm.resetFields()
      load()
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setCloneSubmitting(false)
    }
  }

  const onSubmit = async (values: ModelConfigPayload) => {
    setSubmitting(true)
    try {
      if (editing) {
        const payload = { ...values }
        if (!payload.api_key) delete (payload as Partial<ModelConfigPayload>).api_key
        await modelApi.update(editing.id, payload)
        message.success('更新成功')
      } else {
        await modelApi.create(values)
        message.success('创建成功')
      }
      setModalOpen(false)
      load()
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setSubmitting(false)
    }
  }

  const onDelete = async (id: string) => {
    try {
      await modelApi.remove(id)
      message.success('删除成功')
      load()
    } catch (e) {
      message.error((e as Error).message)
    }
  }

  const onTest = async (id: string) => {
    setTestingId(id)
    try {
      const { data } = await modelApi.test(id)
      if (data.success) message.success(data.message)
      else message.error(data.message)
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setTestingId(null)
    }
  }

  const onSetDefault = async (id: string) => {
    try {
      await modelApi.setDefault(id)
      message.success('已设为默认')
      load()
    } catch (e) {
      message.error((e as Error).message)
    }
  }

  // 按类型分组,每组单独成区,支持顶部锚点跳转
  const grouped = useMemo(() => {
    const map = new Map<ModelType, ModelConfigItem[]>()
    TYPE_ORDER.forEach((t) => map.set(t, []))
    list.forEach((it) => {
      const arr = map.get(it.type)
      if (arr) arr.push(it)
    })
    // 同组内默认配置在前,其余按名称排序保持稳定
    map.forEach((arr) => {
      arr.sort((a, b) => {
        if (a.is_default && !b.is_default) return -1
        if (!a.is_default && b.is_default) return 1
        return a.name.localeCompare(b.name)
      })
    })
    return TYPE_ORDER.filter((t) => (map.get(t) || []).length > 0).map((t) => ({
      type: t,
      items: map.get(t) || [],
    }))
  }, [list])

  const renderCard = (item: ModelConfigItem) => {
    const meta = TYPE_META[item.type]
    const provider = PROVIDER_LABEL[item.provider] ?? item.provider
    return (
      <div key={item.id} className="model-card">
        <div className="model-card-glow" style={{ background: meta.gradient }} />
        <div className="model-card-head">
          <div
            className="model-card-icon"
            style={{ background: meta.gradient }}
          >
            <ApiOutlined />
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div className="model-card-title">
              <span className="model-card-name" title={item.name}>
                {item.name}
              </span>
              {item.is_default && (
                <Tooltip title="默认配置">
                  <StarFilled style={{ color: '#FAAD14', fontSize: 14 }} />
                </Tooltip>
              )}
            </div>
            <div className="model-card-provider">
              <GlobalOutlined style={{ fontSize: 12 }} /> {provider}
            </div>
          </div>
          <Tag
            style={{
              margin: 0,
              border: 'none',
              color: meta.color,
              background: meta.bg,
              fontWeight: 500,
              borderRadius: 6,
            }}
          >
            {TYPE_LABEL[item.type]}
          </Tag>
        </div>

        <div className="model-card-body">
          <div className="model-card-row">
            <ThunderboltOutlined style={{ color: '#98A2B3' }} />
            <span className="model-card-label">模型</span>
            <span className="model-card-value" title={item.model_name}>
              {item.model_name || '-'}
            </span>
          </div>
          <div className="model-card-row">
            <KeyOutlined style={{ color: '#98A2B3' }} />
            <span className="model-card-label">密钥</span>
            <span className="model-card-value model-card-key" title={item.api_key_masked}>
              {normalizeKey(item.api_key_masked)}
            </span>
          </div>
          {item.capability.length > 0 && (
            <div className="model-card-row">
              <CheckCircleFilled style={{ color: '#52C41A' }} />
              <span className="model-card-label">能力</span>
              <span style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                {item.capability.map((c) => (
                  <Tag
                    key={c}
                    color="green"
                    style={{ margin: 0, borderRadius: 6 }}
                  >
                    {CAP_LABEL[c] ?? c}
                  </Tag>
                ))}
              </span>
            </div>
          )}
        </div>

        <div className="model-card-actions">
          <Button
            size="small"
            type="text"
            loading={testingId === item.id}
            icon={<ApiOutlined />}
            onClick={() => onTest(item.id)}
          >
            测试
          </Button>
          {!item.is_default && (
            <Button
              size="small"
              type="text"
              icon={<StarFilled />}
              onClick={() => onSetDefault(item.id)}
            >
              设默认
            </Button>
          )}
          <Button
            size="small"
            type="text"
            icon={<EditOutlined />}
            onClick={() => openEdit(item)}
          >
            编辑
          </Button>
          <Button
            size="small"
            type="text"
            icon={<CopyOutlined />}
            onClick={() => openClone(item)}
          >
            复制到其他类型
          </Button>
          <Popconfirm
            title="确定删除该配置？"
            onConfirm={() => onDelete(item.id)}
          >
            <Button size="small" type="text" danger icon={<DeleteOutlined />}>
              删除
            </Button>
          </Popconfirm>
        </div>
      </div>
    )
  }

  return (
    <div className="fluid-page" style={{ maxWidth: '80rem' }}>
      <div className="model-page-header">
        <div>
          <Typography.Title level={3} style={{ margin: 0 }}>
            模型配置
          </Typography.Title>
          <Typography.Text type="secondary">
            管理对话、多模态、向量、重排与联网搜索模型，密钥加密存储
          </Typography.Text>
        </div>
        <Button
          type="primary"
          size="large"
          icon={<PlusOutlined />}
          onClick={openCreate}
        >
          新增配置
        </Button>
      </div>

      <Collapse
        defaultActiveKey={list.length === 0 ? ['guide'] : []}
        style={{ marginBottom: 20, background: '#fff', borderRadius: 12 }}
        items={[
          {
            key: 'guide',
            label: (
              <span style={{ fontWeight: 600 }}>
                📖 配置流程说明 · 去哪里申请 API Key？
              </span>
            ),
            children: (
              <div>
                <Typography.Paragraph style={{ marginBottom: 14, color: '#475467' }}>
                  k-agent 不内置任何模型，需你自己填入大模型供应商的 API Key（密钥会
                  <b>加密存储</b>，仅你可见）。按以下步骤配置：
                </Typography.Paragraph>

                <ol style={{ paddingLeft: 20, margin: '0 0 16px', color: '#475467', lineHeight: 2 }}>
                  <li>
                    选一个供应商（推荐<b>智谱</b>，注册送额度、模型类型最全），到其官网注册并创建 API Key。
                  </li>
                  <li>
                    点右上角<b>「新增配置」</b>，选择模型类型与供应商，base_url 会自动带出默认值，填入模型名与 API Key。
                  </li>
                  <li>
                    保存后点卡片上的<b>「测试」</b>验证连通，再点<b>「设默认」</b>把它设为该类型的默认模型。
                  </li>
                  <li>
                    至少配置 <b>对话(chat)</b> 与 <b>向量(embedding)</b> 两类；想看图配
                    <b>多模态</b>，想联网问答配<b>联网搜索</b>，想提升检索精度配 <b>rerank</b>，想语音输入配 <b>ASR</b>，想深度研究跨模型审稿配 <b>Verifier</b>。
                  </li>
                </ol>

                <Typography.Text strong style={{ display: 'block', marginBottom: 10 }}>
                  各模型类型有什么用 · 怎么配
                </Typography.Text>
                <div className="model-type-guide">
                  {[
                    { name: '对话 Chat', tag: '必配', desc: '负责所有问答对话的大语言模型。建议选支持 Function Call 的强模型（勾上「工具调用」能力），才能自动调用知识库/记忆/联网等工具。', provider: '智谱 glm-4 / DeepSeek deepseek-chat / 通义 qwen-max' },
                    { name: '向量 Embedding', tag: '必配', desc: '把文档和问题转成向量，知识库检索和记忆召回都依赖它。配了知识库才有意义。', provider: '智谱 embedding-3 / 通义 text-embedding-v3' },
                    { name: '多模态 Multimodal', tag: '可选', desc: '能看图理解的模型。对话中发送图片让 AI 分析时用到（勾「图片理解」能力）。', provider: '智谱 glm-4v / 通义 qwen-vl-max / 豆包 vision' },
                    { name: 'Rerank 重排', tag: '可选', desc: '对知识库检索结果重新排序，提升相关度。不配也能用，配了检索更准。', provider: '通义 gte-rerank' },
                    { name: '联网搜索 Websearch', tag: '可选', desc: '让 AI 能查实时信息（新闻/股价/天气）。配了并在对话开启联网开关才生效。', provider: '百度千帆 / Tavily' },
                    { name: '语音识别 ASR', tag: '可选', desc: '把语音转文字，对话输入框的麦克风用它（更准）。不配则用浏览器免费识别。', provider: '通义千问 paraformer-v2 / OpenAI whisper-1' },
                    { name: '审稿 Verifier', tag: '可选', desc: '深度研究 Verifier Loop 的独立审稿模型。建议与对话模型用不同供应商（跨家族），避免自评偏乐观。配好并设为默认后会自动用于跨模型审稿；不配则回退为同模型自评。', provider: '智谱 glm-4-flash / 通义 qwen-plus（与对话模型错开家族）' },
                  ].map((m) => (
                    <div key={m.name} className="model-type-item">
                      <div className="model-type-item__head">
                        <span className="model-type-item__name">{m.name}</span>
                        <span
                          className="model-type-item__tag"
                          style={{
                            color: m.tag === '必配' ? '#155EEF' : '#98A2B3',
                            background: m.tag === '必配' ? '#EEF4FF' : '#F2F4F7',
                          }}
                        >
                          {m.tag}
                        </span>
                      </div>
                      <div className="model-type-item__desc">{m.desc}</div>
                      <div className="model-type-item__provider">推荐：{m.provider}</div>
                    </div>
                  ))}
                </div>

                <Typography.Text strong style={{ display: 'block', marginBottom: 10 }}>
                  各供应商申请入口
                </Typography.Text>
                <div className="provider-link-grid">
                  {PROVIDER_LINKS.map((p) => (
                    <a
                      key={p.label}
                      className="provider-link"
                      href={p.url}
                      target="_blank"
                      rel="noreferrer"
                    >
                      <div className="provider-link__head">
                        <LinkOutlined />
                        <span className="provider-link__name">{p.label}</span>
                      </div>
                      <div className="provider-link__desc">{p.desc}</div>
                    </a>
                  ))}
                </div>
                <Typography.Text type="secondary" style={{ fontSize: 12, marginTop: 12, display: 'block' }}>
                  提示：以上为第三方平台地址，注册与计费以各平台为准；密钥请勿泄露给他人。
                </Typography.Text>
              </div>
            ),
          },
        ]}
      />

      <Spin spinning={loading}>
        {grouped.length === 0 && !loading ? (
          <Empty
            style={{ padding: '60px 0' }}
            description="还没有模型配置,点击右上角新增一个"
          />
        ) : (
          <div>
            {/* 顶部分类快捷锚点 */}
            {grouped.length > 1 && (
              <div
                style={{
                  display: 'flex',
                  flexWrap: 'wrap',
                  gap: 8,
                  padding: '10px 14px',
                  background: '#ffffff',
                  border: '1px solid #eef0f4',
                  borderRadius: 12,
                  marginBottom: 18,
                  position: 'sticky',
                  top: 8,
                  zIndex: 10,
                }}
              >
                <Typography.Text
                  type="secondary"
                  style={{ fontSize: 12.5, marginRight: 6, alignSelf: 'center' }}
                >
                  快速跳转
                </Typography.Text>
                {grouped.map((g) => {
                  const meta = TYPE_META[g.type]
                  return (
                    <a
                      key={g.type}
                      href={`#type-${g.type}`}
                      onClick={(e) => {
                        e.preventDefault()
                        document
                          .getElementById(`type-${g.type}`)
                          ?.scrollIntoView({ behavior: 'smooth', block: 'start' })
                      }}
                      style={{
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: 6,
                        padding: '3px 10px',
                        borderRadius: 999,
                        fontSize: 12.5,
                        fontWeight: 500,
                        color: meta.color,
                        background: meta.bg,
                        border: `1px solid ${meta.color}26`,
                        textDecoration: 'none',
                        transition: 'transform 0.12s, box-shadow 0.18s',
                      }}
                      onMouseEnter={(e) => {
                        e.currentTarget.style.transform = 'translateY(-1px)'
                        e.currentTarget.style.boxShadow = `0 4px 10px -6px ${meta.color}80`
                      }}
                      onMouseLeave={(e) => {
                        e.currentTarget.style.transform = ''
                        e.currentTarget.style.boxShadow = ''
                      }}
                    >
                      <span
                        style={{
                          display: 'inline-block',
                          width: 6,
                          height: 6,
                          borderRadius: '50%',
                          background: meta.color,
                        }}
                      />
                      {TYPE_LABEL[g.type]}
                      <span
                        style={{
                          marginLeft: 2,
                          padding: '0 6px',
                          fontSize: 11,
                          fontWeight: 600,
                          background: '#fff',
                          borderRadius: 999,
                          color: meta.color,
                        }}
                      >
                        {g.items.length}
                      </span>
                    </a>
                  )
                })}
              </div>
            )}

            {/* 分组列表 */}
            {grouped.map((g, gi) => {
              const meta = TYPE_META[g.type]
              return (
                <section
                  key={g.type}
                  id={`type-${g.type}`}
                  style={{
                    scrollMarginTop: 70,
                    marginTop: gi === 0 ? 0 : 28,
                  }}
                >
                  {/* 分组头 */}
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 12,
                      paddingBottom: 12,
                      marginBottom: 14,
                      borderBottom: `1px solid ${meta.color}1f`,
                    }}
                  >
                    <span
                      style={{
                        width: 4,
                        height: 18,
                        borderRadius: 2,
                        background: meta.gradient,
                      }}
                    />
                    <Typography.Text
                      strong
                      style={{ fontSize: 15.5, color: '#171719' }}
                    >
                      {TYPE_LABEL[g.type]}
                    </Typography.Text>
                    <span
                      style={{
                        padding: '1px 8px',
                        fontSize: 11.5,
                        fontWeight: 600,
                        borderRadius: 999,
                        color: meta.color,
                        background: meta.bg,
                      }}
                    >
                      {g.items.length}
                    </span>
                    <Typography.Text
                      type="secondary"
                      style={{ fontSize: 12.5, color: '#98A2B3' }}
                    >
                      {meta.desc}
                    </Typography.Text>
                  </div>
                  <div className="model-card-grid">{g.items.map(renderCard)}</div>
                </section>
              )
            })}
          </div>
        )}
      </Spin>

      <ModelConfigModal
        open={modalOpen}
        editing={editing}
        confirmLoading={submitting}
        onCancel={() => setModalOpen(false)}
        onSubmit={onSubmit}
      />

      <Modal
        title="复制模型配置"
        open={!!cloneSource}
        onCancel={() => {
          setCloneSource(null)
          cloneForm.resetFields()
        }}
        onOk={() => cloneForm.submit()}
        confirmLoading={cloneSubmitting}
        destroyOnClose
        width={520}
      >
        {cloneSource && (
          <Typography.Paragraph type="secondary" style={{ marginTop: 12 }}>
            将「{cloneSource.name}」的供应商、API Key 和 Base URL 复制到新的模型类型。API Key 不会在浏览器中回显。
          </Typography.Paragraph>
        )}
        <Form
          form={cloneForm}
          layout="vertical"
          onFinish={onClone}
          requiredMark={false}
        >
          <Form.Item
            name="target_type"
            label="目标模型类型"
            rules={[{ required: true, message: '请选择目标类型' }]}
          >
            <Select
              options={TYPE_OPTIONS.filter((option) => option.value !== cloneSource?.type)}
            />
          </Form.Item>
          <Form.Item
            name="name"
            label="配置名称"
            rules={[{ required: true, message: '请输入配置名称' }]}
          >
            <Input placeholder="如：同 API 的多模态模型" />
          </Form.Item>
          <Form.Item
            name="model_name"
            label="目标模型名称"
            rules={[{ required: true, message: '请输入模型名称' }]}
            extra="默认沿用源配置名称；如果目标类型使用不同模型，请在这里修改。"
          >
            <Input placeholder="如：glm-4v / qwen-vl-max" />
          </Form.Item>
          <Form.Item name="capability" label="模型能力">
            <Select
              mode="multiple"
              options={CAPABILITY_OPTIONS}
              placeholder="可选，标记工具调用 / 图片理解"
            />
          </Form.Item>
          <Form.Item name="is_default" label="设为目标类型默认" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
