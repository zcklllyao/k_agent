import { useState } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import { useEffect } from 'react'
import {
  Card,
  Empty,
  Input,
  Spin,
  Tag,
  Typography,
  message,
} from 'antd'
import {
  CheckCircleOutlined,
  ExclamationCircleOutlined,
  FileTextOutlined,
  HddOutlined,
  PictureOutlined,
} from '@ant-design/icons'
import { searchApi, type GlobalSearchResult } from '@/api/search'

const { Text, Paragraph } = Typography

function memoryTrustTone(confidence?: number | null) {
  const value = typeof confidence === 'number' ? confidence : 0.8
  if (value >= 0.85) return 'high'
  if (value >= 0.75) return 'medium'
  return 'low'
}

function MemoryTrustTag({ confidence }: { confidence?: number | null }) {
  const tone = memoryTrustTone(confidence)
  const label = tone === 'high' ? '高置信' : tone === 'medium' ? '中置信' : '待确认'
  const color = tone === 'high' ? 'success' : tone === 'medium' ? 'processing' : 'warning'
  const value = typeof confidence === 'number' ? confidence : 0.8
  return (
    <Tag
      color={color}
      icon={tone === 'low' ? <ExclamationCircleOutlined /> : <CheckCircleOutlined />}
      style={{ marginLeft: 6 }}
    >
      {label} {Math.round(Math.max(0, Math.min(1, value)) * 100)}%
    </Tag>
  )
}

export default function SearchPage() {
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()
  const [query, setQuery] = useState(params.get('q') ?? '')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<GlobalSearchResult | null>(null)

  const doSearch = async (q: string) => {
    const text = q.trim()
    if (!text) return
    setLoading(true)
    setParams({ q: text })
    try {
      const { data } = await searchApi.global(text, 8)
      setResult(data)
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  // 带 ?q= 进来时自动搜一次
  useEffect(() => {
    const q = params.get('q')
    if (q) doSearch(q)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div className="fluid-page">
      <Input.Search
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        onSearch={doSearch}
        placeholder="搜索文档、图片、记忆…"
        size="large"
        enterButton="搜索"
        allowClear
        style={{ marginBottom: 20 }}
      />

      {loading ? (
        <div style={{ textAlign: 'center', padding: 60 }}>
          <Spin />
        </div>
      ) : !result ? (
        <Empty description="输入关键词，一次搜遍知识库、图片与记忆" />
      ) : (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(18rem, 1fr))',
            gap: 16,
            alignItems: 'start',
          }}
        >
          <ResultColumn
            title="文档"
            icon={<FileTextOutlined />}
            count={result.documents.length}
          >
            {result.documents.map((d) => (
              <Card
                key={d.chunk_id}
                size="small"
                hoverable
                styles={{ body: { padding: 12 } }}
                style={{ marginBottom: 10 }}
                onClick={() => navigate('/knowledge')}
              >
                <Text strong>{d.doc_name || '未命名文档'}</Text>
                <Tag style={{ marginLeft: 6 }}>{d.score}</Tag>
                <Paragraph type="secondary" style={{ margin: '4px 0 0', fontSize: 13 }} ellipsis={{ rows: 3 }}>
                  {d.content}
                </Paragraph>
              </Card>
            ))}
          </ResultColumn>

          <ResultColumn
            title="图片"
            icon={<PictureOutlined />}
            count={result.images.length}
          >
            {result.images.map((img) => (
              <Card
                key={img.chunk_id}
                size="small"
                hoverable
                styles={{ body: { padding: 12 } }}
                style={{ marginBottom: 10 }}
                onClick={() => navigate(img.source_id ? `/images?image=${img.source_id}` : '/images')}
              >
                <Text strong>{img.doc_name || '图片'}</Text>
                <Tag style={{ marginLeft: 6 }}>{img.score}</Tag>
                <Paragraph type="secondary" style={{ margin: '4px 0 0', fontSize: 13 }} ellipsis={{ rows: 3 }}>
                  {img.content}
                </Paragraph>
              </Card>
            ))}
          </ResultColumn>

          <ResultColumn
            title="记忆"
            icon={<HddOutlined />}
            count={result.memories.length}
          >
            {result.memories.map((m) => (
              <Card
                key={m.id}
                size="small"
                hoverable
                styles={{ body: { padding: 12 } }}
                style={{ marginBottom: 10 }}
                onClick={() => navigate('/memory')}
              >
                <Text strong>{m.name}</Text> <Tag color="blue">{m.type}</Tag>
                <MemoryTrustTag confidence={m.confidence} />
                <Tag>{m.score}</Tag>
                {m.description && (
                  <Paragraph type="secondary" style={{ margin: '4px 0 0', fontSize: 13 }} ellipsis={{ rows: 3 }}>
                    {m.description}
                  </Paragraph>
                )}
              </Card>
            ))}
          </ResultColumn>
        </div>
      )}
    </div>
  )
}

function ResultColumn({
  title,
  icon,
  count,
  children,
}: {
  title: string
  icon: React.ReactNode
  count: number
  children: React.ReactNode
}) {
  return (
    <div>
      <div style={{ marginBottom: 12, fontWeight: 600, fontSize: 15 }}>
        {icon} {title} <Text type="secondary">({count})</Text>
      </div>
      {count === 0 ? (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="无结果" />
      ) : (
        children
      )}
    </div>
  )
}
