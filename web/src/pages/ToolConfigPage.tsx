import { useEffect, useState } from 'react'
import { Card, List, Space, Switch, Tag, Typography, message } from 'antd'
import { toolsApi, type ToolItem } from '@/api/tools'
import McpServers from './tools/McpServers'

const { Text } = Typography

export default function ToolConfigPage() {
  const [tools, setTools] = useState<ToolItem[]>([])
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState<string | null>(null)

  const load = async () => {
    setLoading(true)
    try {
      const { data } = await toolsApi.list()
      setTools(data)
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const onToggle = async (item: ToolItem, enabled: boolean) => {
    setSaving(item.tool_key)
    try {
      await toolsApi.toggle(item.tool_key, enabled)
      setTools((prev) =>
        prev.map((t) => (t.tool_key === item.tool_key ? { ...t, enabled } : t)),
      )
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setSaving(null)
    }
  }

  return (
    <div className="fluid-page">
      <Space direction="vertical" size={16} style={{ width: '100%' }}>
        <Card
          title="内置工具"
          loading={loading}
          extra={<Text type="secondary">控制 AI 在对话中可调用的工具</Text>}
        >
          <List
            itemLayout="horizontal"
            dataSource={tools}
            renderItem={(item) => (
              <List.Item
                actions={[
                  <Switch
                    key="sw"
                    checked={item.enabled}
                    loading={saving === item.tool_key}
                    onChange={(v) => onToggle(item, v)}
                  />,
                ]}
              >
                <List.Item.Meta
                  avatar={<span style={{ fontSize: 24 }}>{item.icon}</span>}
                  title={
                    <span>
                      {item.name}
                      {item.needs_config && (
                        <Tag color="orange" style={{ marginInlineStart: 8 }}>
                          需配置
                        </Tag>
                      )}
                    </span>
                  }
                  description={
                    <span>
                      {item.description}
                      {item.needs_config && item.config_hint && (
                        <div>
                          <Text type="warning" style={{ fontSize: 12 }}>
                            {item.config_hint}
                          </Text>
                        </div>
                      )}
                    </span>
                  }
                />
              </List.Item>
            )}
          />
        </Card>
        <McpServers />
      </Space>
    </div>
  )
}
