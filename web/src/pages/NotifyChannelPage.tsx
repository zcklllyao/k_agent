import { useCallback, useEffect, useState } from 'react'
import {
  App,
  Button,
  Card,
  Collapse,
  Empty,
  Form,
  Input,
  Modal,
  Select,
  Switch,
  Tag,
  Typography,
} from 'antd'
import {
  BellOutlined,
  DeleteOutlined,
  PlusOutlined,
  SendOutlined,
} from '@ant-design/icons'
import { notifyApi, type ChannelType, type NotifyChannel } from '@/api/notify'

const CHANNEL_META: Record<ChannelType, { label: string; hint: string; apply?: string }> = {
  serverchan: {
    label: 'Server酱（微信推送）',
    hint: '填 SendKey。用 GitHub 登录 sc3.ft07.com（Server酱³）拿到 SendKey，按提示绑定后消息推到你微信/手机 App。',
    apply: 'https://sc3.ft07.com',
  },
  wecom: {
    label: '企业微信群机器人',
    hint: '填群机器人的 Webhook 地址（群设置 → 群机器人 → 添加）。',
  },
  dingtalk: {
    label: '钉钉群机器人',
    hint: '填群机器人的 Webhook 地址（群设置 → 智能群助手 → 添加机器人）。',
  },
  feishu: {
    label: '飞书群机器人',
    hint: '填飞书群自定义机器人的 Webhook 地址；如果安全设置启用了签名，再填写签名密钥。',
  },
  webhook: {
    label: '通用 Webhook',
    hint: '填任意接收 POST JSON 的地址，body 为 {title, content}，由你自行处理。',
  },
}

export default function NotifyChannelPage() {
  const { message, modal } = App.useApp()
  const [list, setList] = useState<NotifyChannel[]>([])
  const [loading, setLoading] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [testingId, setTestingId] = useState<string | null>(null)
  const [form] = Form.useForm()
  const channelType = Form.useWatch('channel_type', form) as ChannelType | undefined

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const { data } = await notifyApi.list()
      setList(data)
    } catch {
      /* 忽略 */
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const openCreate = () => {
    form.resetFields()
    form.setFieldsValue({ channel_type: 'serverchan', enabled: true })
    setModalOpen(true)
  }

  const submit = async () => {
    const v = await form.validateFields()
    try {
      await notifyApi.create({
        channel_type: v.channel_type,
        name: (v.name || '').trim(),
        target: v.target.trim(),
        secret: v.channel_type === 'feishu' ? (v.secret || '').trim() || undefined : undefined,
        enabled: v.enabled,
      })
      message.success('已添加')
      setModalOpen(false)
      load()
    } catch (err) {
      message.error((err as { message?: string })?.message || '添加失败')
    }
  }

  const toggle = async (ch: NotifyChannel, enabled: boolean) => {
    try {
      await notifyApi.update(ch.id, { enabled })
      load()
    } catch {
      message.error('操作失败')
    }
  }

  const test = async (ch: NotifyChannel) => {
    setTestingId(ch.id)
    try {
      await notifyApi.test(ch.id)
      message.success('已发送测试消息，请查收')
    } catch (err) {
      message.error((err as { message?: string })?.message || '推送失败')
    } finally {
      setTestingId(null)
    }
  }

  const remove = (ch: NotifyChannel) => {
    modal.confirm({
      title: '删除推送渠道',
      content: `确定删除「${CHANNEL_META[ch.channel_type].label}」吗？`,
      okType: 'danger',
      onOk: async () => {
        await notifyApi.remove(ch.id)
        message.success('已删除')
        load()
      },
    })
  }

  return (
    <div className="fluid-page">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16, flexWrap: 'wrap', gap: 8 }}>
        <div>
          <Typography.Title level={4} style={{ margin: 0 }}>
            <BellOutlined /> 消息推送
          </Typography.Title>
          <Typography.Text type="secondary" style={{ fontSize: 13 }}>
            配置后，定时任务跑完会把报告摘要主动推到你的手机/群里。每个渠道配你自己的 key，各推各的。
          </Typography.Text>
        </div>
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
          添加渠道
        </Button>
      </div>

      <Collapse
        ghost
        style={{ marginBottom: 12 }}
        items={[
          {
            key: 'help',
            label: '各渠道怎么配？',
            children: (
              <div style={{ fontSize: 13, color: '#475467', lineHeight: 1.9 }}>
                {(Object.keys(CHANNEL_META) as ChannelType[]).map((t) => (
                  <div key={t}>
                    <b>{CHANNEL_META[t].label}</b>：{CHANNEL_META[t].hint}
                    {CHANNEL_META[t].apply && (
                      <a href={CHANNEL_META[t].apply} target="_blank" rel="noreferrer">
                        {' '}前往申请 →
                      </a>
                    )}
                  </div>
                ))}
              </div>
            ),
          },
        ]}
      />

      {!loading && list.length === 0 && (
        <Empty description="还没有推送渠道，添加一个让 AI 跑完任务主动通知你" style={{ marginTop: 50 }}>
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
            添加渠道
          </Button>
        </Empty>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {list.map((ch) => (
          <Card key={ch.id} styles={{ body: { padding: 16 } }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
              <div style={{ minWidth: 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                  <span style={{ fontWeight: 600 }}>
                    {ch.name || CHANNEL_META[ch.channel_type].label}
                  </span>
                  <Tag color="blue">{CHANNEL_META[ch.channel_type].label}</Tag>
                </div>
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  密钥 {ch.target_mask}
                </Typography.Text>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <Switch size="small" checked={ch.enabled} onChange={(c) => toggle(ch, c)} />
                <Button
                  size="small"
                  icon={<SendOutlined />}
                  loading={testingId === ch.id}
                  onClick={() => test(ch)}
                >
                  测试
                </Button>
                <Button size="small" danger icon={<DeleteOutlined />} onClick={() => remove(ch)} />
              </div>
            </div>
          </Card>
        ))}
      </div>

      <Modal
        title="添加推送渠道"
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={submit}
        okText="保存"
        cancelText="取消"
        destroyOnClose
      >
        <Form form={form} layout="vertical" style={{ marginTop: 12 }}>
          <Form.Item name="channel_type" label="渠道类型" rules={[{ required: true }]}>
            <Select
              options={(Object.keys(CHANNEL_META) as ChannelType[]).map((t) => ({
                value: t,
                label: CHANNEL_META[t].label,
              }))}
            />
          </Form.Item>
          {channelType && (
            <Typography.Paragraph type="secondary" style={{ fontSize: 12, marginTop: -8 }}>
              {CHANNEL_META[channelType].hint}
              {CHANNEL_META[channelType].apply && (
                <a href={CHANNEL_META[channelType].apply} target="_blank" rel="noreferrer">
                  {' '}前往申请 →
                </a>
              )}
            </Typography.Paragraph>
          )}
          <Form.Item name="name" label="备注名（可选）">
            <Input placeholder="例如：我的微信" maxLength={64} />
          </Form.Item>
          <Form.Item
            name="target"
            label={channelType === 'serverchan' ? 'SendKey' : 'Webhook 地址'}
            rules={[{ required: true, message: '请填写' }]}
          >
            <Input.TextArea
              rows={2}
              placeholder={channelType === 'serverchan' ? 'SCT... 或 sctp...' : 'https://...'}
            />
          </Form.Item>
          {channelType === 'feishu' && (
            <Form.Item
              name="secret"
              label="签名密钥（可选）"
              extra="只有在飞书机器人安全设置选择“签名”时才需要填写。"
            >
              <Input.Password placeholder="飞书机器人 Secret" />
            </Form.Item>
          )}
          <Form.Item name="enabled" label="启用" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
