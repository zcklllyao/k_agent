import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  Button,
  Checkbox,
  Empty,
  Input,
  Modal,
  Popconfirm,
  Progress,
  Segmented,
  Space,
  Spin,
  Tabs,
  Tag,
  Tooltip,
  Typography,
  Upload,
  message,
} from 'antd'
import {
  ArrowLeftOutlined,
  DeleteOutlined,
  ExclamationCircleFilled,
  EyeOutlined,
  InboxOutlined,
  LinkOutlined,
  LoadingOutlined,
  ReloadOutlined,
  FileTextOutlined,
} from '@ant-design/icons'
import { documentApi, type DocumentItem, type DocumentPreview, type SearchHit } from '@/api/documents'
import { imageApi, type ImageItem } from '@/api/images'
import { knowledgeBaseApi, type KnowledgeBase } from '@/api/knowledgeBases'
import { AuthenticatedImage } from '@/components/AuthenticatedImage'
import MarkdownMessage from '@/components/MarkdownMessage'
import { FileTypeIcon, StatusTag, formatSize } from './knowledge/helpers'

const { Dragger } = Upload
const { Search } = Input

export default function KnowledgeDetailPage() {
  const { kbId = '' } = useParams()
  const navigate = useNavigate()
  const [kb, setKb] = useState<KnowledgeBase | null>(null)
  const [tab, setTab] = useState<'doc' | 'image'>('doc')

  useEffect(() => {
    if (!kbId) return
    knowledgeBaseApi
      .detail(kbId)
      .then(({ data }) => setKb(data))
      .catch((e) => message.error((e as Error).message))
  }, [kbId])

  return (
    <div className="fluid-page">
      <div className="kb-detail-header">
        <button
          type="button"
          className="kb-back-btn"
          onClick={() => navigate('/knowledge')}
        >
          <ArrowLeftOutlined />
          <span>返回</span>
        </button>
        <div className="kb-detail-title">
          <span className="kb-detail-icon">{kb?.icon || '📁'}</span>
          <div>
            <Typography.Title level={3} style={{ margin: 0, lineHeight: 1.2 }}>
              {kb ? kb.name : '知识库'}
            </Typography.Title>
            {kb?.description && (
              <Typography.Text type="secondary" style={{ fontSize: 13 }}>
                {kb.description}
              </Typography.Text>
            )}
          </div>
        </div>
      </div>

      <Tabs
        activeKey={tab}
        onChange={(k) => setTab(k as 'doc' | 'image')}
        items={[
          { key: 'doc', label: '文档', children: <DocTab kbId={kbId} /> },
          { key: 'image', label: '图片', children: <ImageTab kbId={kbId} /> },
        ]}
      />
    </div>
  )
}

// ──────────── 文档 Tab ────────────
function DocTab({ kbId }: { kbId: string }) {
  const [list, setList] = useState<DocumentItem[]>([])
  const [loading, setLoading] = useState(false)
  const [urlModalOpen, setUrlModalOpen] = useState(false)
  const [url, setUrl] = useState('')
  const [importing, setImporting] = useState(false)
  const [searching, setSearching] = useState(false)
  const [hits, setHits] = useState<SearchHit[] | null>(null)
  const [uploading, setUploading] = useState(false)
  const pollRef = useRef<number | null>(null)
  const [preview, setPreview] = useState<DocumentPreview | null>(null)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [bulkDeleting, setBulkDeleting] = useState(false)
  const [overview, setOverview] = useState<{ content: string; status: string; error: string | null; updated_at: string | null } | null>(null)
  const [overviewLoading, setOverviewLoading] = useState(false)

  const loadOverview = useCallback(async () => {
    try {
      const { data } = await knowledgeBaseApi.overview(kbId)
      setOverview(data)
    } catch (e) {
      message.error((e as Error).message)
    }
  }, [kbId])

  useEffect(() => {
    loadOverview()
  }, [loadOverview])

  useEffect(() => {
    if (overview?.status !== 'generating') return
    const timer = window.setInterval(loadOverview, 3000)
    return () => clearInterval(timer)
  }, [overview?.status, loadOverview])

  const generateOverview = async () => {
    setOverviewLoading(true)
    try {
      const { data } = await knowledgeBaseApi.generateOverview(kbId)
      setOverview(data)
      message.success('总览生成任务已提交，完成后会自动显示')
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setOverviewLoading(false)
    }
  }

  const openPreview = async (d: DocumentItem) => {
    setPreviewLoading(true)
    setPreview({
      id: d.id,
      file_name: d.file_name,
      file_ext: d.file_ext,
      is_markdown: false,
      source_url: d.source_url,
      content: '',
      truncated: false,
    })
    try {
      const { data } = await documentApi.preview(d.id)
      setPreview(data)
    } catch (e) {
      message.error((e as Error).message)
      setPreview(null)
    } finally {
      setPreviewLoading(false)
    }
  }

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const { data } = await documentApi.list(1, 100, undefined, kbId)
      setList(data.items)
      const availableIds = new Set(data.items.map((item) => item.id))
      setSelectedIds((current) => {
        const next = new Set([...current].filter((id) => availableIds.has(id)))
        return next.size === current.size ? current : next
      })
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setLoading(false)
    }
  }, [kbId])

  useEffect(() => {
    if (hits === null) load()
  }, [load, hits])

  useEffect(() => {
    const hasPending = list.some(
      (d) => d.status === 'pending' || d.status === 'parsing',
    )
    if (hits === null && hasPending && pollRef.current === null) {
      pollRef.current = window.setInterval(load, 3000)
    } else if ((hits !== null || !hasPending) && pollRef.current !== null) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
    return () => {
      if (pollRef.current !== null) {
        clearInterval(pollRef.current)
        pollRef.current = null
      }
    }
  }, [list, load, hits])

  const onUpload = async (file: File) => {
    setUploading(true)
    const hide = message.loading(`正在上传「${file.name}」，请稍候…`, 0)
    try {
      await documentApi.upload(file, kbId)
      hide()
      message.success('上传成功，正在解析')
      setHits(null)
      load()
    } catch (e) {
      hide()
      message.error((e as Error).message)
    } finally {
      setUploading(false)
    }
    return false
  }

  const onImportUrl = async () => {
    if (!url.trim()) return
    setImporting(true)
    try {
      await documentApi.importUrl(url.trim(), kbId)
      message.success('导入成功，正在解析')
      setUrlModalOpen(false)
      setUrl('')
      setHits(null)
      load()
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setImporting(false)
    }
  }

  const onRetry = async (id: string) => {
    try {
      await documentApi.retry(id)
      message.success('已重新提交解析')
      load()
    } catch (e) {
      message.error((e as Error).message)
    }
  }

  const onDelete = async (id: string) => {
    try {
      await documentApi.remove(id)
      setSelectedIds((current) => {
        const next = new Set(current)
        next.delete(id)
        return next
      })
      message.success('删除成功')
      load()
    } catch (e) {
      message.error((e as Error).message)
    }
  }

  const toggleSelected = (id: string) => {
    setSelectedIds((current) => {
      const next = new Set(current)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const selectAll = () => setSelectedIds(new Set(list.map((item) => item.id)))

  const confirmBulkDelete = () => {
    const ids = [...selectedIds]
    if (!ids.length) return
    Modal.confirm({
      title: `批量删除 ${ids.length} 篇文档？`,
      content: '将同步删除原文件和检索索引，删除后不可恢复。',
      icon: <ExclamationCircleFilled style={{ color: '#FF5D34' }} />,
      okText: '批量删除',
      cancelText: '取消',
      okButtonProps: { danger: true },
      onOk: async () => {
        setBulkDeleting(true)
        try {
          const { data } = await documentApi.bulkRemove(ids)
          setSelectedIds(new Set())
          message.success(`已删除 ${data.deleted} 篇文档`)
          await load()
        } catch (e) {
          message.error((e as Error).message)
          throw e
        } finally {
          setBulkDeleting(false)
        }
      },
    })
  }

  const onSearch = async (q: string) => {
    if (!q.trim()) {
      setHits(null)
      return
    }
    setSearching(true)
    try {
      const { data } = await documentApi.search(q.trim(), 8)
      setHits(data)
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setSearching(false)
    }
  }

  const renderRow = (d: DocumentItem) => (
    <div key={d.id} className="kb-row">
      <Checkbox
        checked={selectedIds.has(d.id)}
        onClick={(event) => event.stopPropagation()}
        onChange={() => toggleSelected(d.id)}
        aria-label={`选择 ${d.file_name}`}
      />
      <div className="kb-row-icon">
        <FileTypeIcon ext={d.file_ext} isUrl={d.source_type === 'url'} />
      </div>
      <div
        className="kb-row-main"
        onClick={() => openPreview(d)}
        style={{ cursor: 'pointer' }}
        title="点击查看内容"
      >
        <div className="kb-row-title-line">
          <span className="kb-row-title" title={d.file_name}>
            {d.file_name}
          </span>
          {d.tags.map((t) => (
            <Tag key={t.name} color={t.color} style={{ margin: 0, borderRadius: 5 }}>
              {t.name}
            </Tag>
          ))}
        </div>
        <div className="kb-row-meta">
          <StatusTag status={d.status} />
          {d.status === 'parsing' && (
            <Progress
              percent={Math.round(d.progress * 100)}
              size="small"
              style={{ width: 90 }}
            />
          )}
          {d.status === 'done' && <span>{d.chunk_num} 块</span>}
          <span className="kb-dot">·</span>
          <span>{d.source_type === 'url' ? '网页' : formatSize(d.file_size)}</span>
        </div>
      </div>
      <div className="kb-row-actions">
        <Tooltip title="查看内容">
          <Button
            size="small"
            type="text"
            icon={<EyeOutlined />}
            onClick={() => openPreview(d)}
          />
        </Tooltip>
        {d.status === 'failed' && (
          <Tooltip title="重新解析">
            <Button
              size="small"
              type="text"
              icon={<ReloadOutlined />}
              onClick={() => onRetry(d.id)}
            />
          </Tooltip>
        )}
        <Popconfirm
          title="删除文档"
          description="删除后不可恢复，确定吗？"
          icon={<ExclamationCircleFilled style={{ color: '#FF5D34' }} />}
          okText="删除"
          cancelText="取消"
          okButtonProps={{ danger: true }}
          onConfirm={() => onDelete(d.id)}
        >
          <Button size="small" type="text" danger>
            删除
          </Button>
        </Popconfirm>
      </div>
    </div>
  )

  return (
    <div>
      <div style={{ marginBottom: 18, padding: '16px 20px', border: '1px solid #EAECF0', borderRadius: 12, background: '#FCFCFD' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
          <Space>
            <FileTextOutlined style={{ color: '#155EEF' }} />
            <Typography.Text strong>知识库 Markdown 总览</Typography.Text>
            {overview?.status === 'generating' && <Tag color="processing">生成中</Tag>}
            {overview?.status === 'done' && <Tag color="success">已更新</Tag>}
          </Space>
          <Button size="small" icon={<ReloadOutlined />} loading={overviewLoading} onClick={generateOverview}>
            {overview?.content ? '刷新总览' : '生成总览'}
          </Button>
        </div>
        {overview?.content ? (
          <div style={{ maxHeight: 360, overflowY: 'auto' }}><MarkdownMessage content={overview.content} /></div>
        ) : (
          <Typography.Text type="secondary">
            总览会压缩每篇已解析文档的主题、关键词和定位问题，帮助模型先了解知识库范围。上传文档后会自动生成。
          </Typography.Text>
        )}
        {overview?.error && <Typography.Text type="danger">{overview.error}</Typography.Text>}
        {overview?.updated_at && <Typography.Text type="secondary" style={{ display: 'block', marginTop: 8, fontSize: 12 }}>更新时间：{new Date(overview.updated_at).toLocaleString()}</Typography.Text>}
      </div>
      <Search
        placeholder="输入关键词语义检索（清空回到浏览）"
        allowClear
        enterButton="检索"
        size="large"
        loading={searching}
        onSearch={onSearch}
        style={{ marginBottom: 16 }}
      />
      {hits === null ? (
        <>
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 8 }}>
            {list.length > 0 && (
              <Space wrap style={{ marginRight: 8 }}>
                <Button
                  onClick={selectedIds.size === list.length ? () => setSelectedIds(new Set()) : selectAll}
                >
                  {selectedIds.size === list.length ? '取消全选' : '全选当前列表'}
                </Button>
                <Button
                  danger
                  icon={<DeleteOutlined />}
                  disabled={selectedIds.size === 0}
                  loading={bulkDeleting}
                  onClick={confirmBulkDelete}
                >
                  批量删除{selectedIds.size > 0 ? `（${selectedIds.size}）` : ''}
                </Button>
              </Space>
            )}
            <Button icon={<LinkOutlined />} onClick={() => setUrlModalOpen(true)}>
              网页导入
            </Button>
          </div>
          <Dragger
            accept=".pdf,.docx,.md,.markdown,.txt,.html,.htm"
            showUploadList={false}
            beforeUpload={onUpload}
            multiple
            disabled={uploading}
            className="kb-dragger"
          >
            <p className="ant-upload-drag-icon" style={{ marginBottom: 4 }}>
              {uploading ? <LoadingOutlined /> : <InboxOutlined />}
            </p>
            <p className="ant-upload-text" style={{ fontSize: 14 }}>
              {uploading ? '正在上传，请稍候…' : '点击或拖拽文件到此上传到本知识库'}
            </p>
            <p className="ant-upload-hint" style={{ fontSize: 12 }}>
              支持 PDF / Word / Markdown / TXT / HTML
            </p>
          </Dragger>

          <Spin spinning={loading}>
            {list.length === 0 ? (
              <Empty style={{ padding: '40px 0' }} description="这个知识库还没有文档" />
            ) : (
              <div className="kb-list" style={{ marginTop: 12 }}>
                {list.map(renderRow)}
              </div>
            )}
          </Spin>
        </>
      ) : (
        <div>
          <Space style={{ marginBottom: 12 }}>
            <Button onClick={() => setHits(null)}>返回浏览</Button>
            <span style={{ color: '#667085' }}>命中 {hits.length} 条相关片段</span>
          </Space>
          {hits.length ? (
            hits.map((h) => (
              <div key={h.chunk_id} className="kb-hit">
                <div className="kb-hit-head">
                  <Tag color="blue" style={{ margin: 0 }}>
                    {h.doc_name}
                  </Tag>
                  <span className="kb-hit-score">相关度 {h.score}</span>
                </div>
                <div className="kb-hit-content">{h.content}</div>
              </div>
            ))
          ) : (
            <Empty description="没有找到相关内容" />
          )}
        </div>
      )}

      <Modal
        title="从网页导入"
        open={urlModalOpen}
        onCancel={() => setUrlModalOpen(false)}
        onOk={onImportUrl}
        confirmLoading={importing}
      >
        <Input
          placeholder="https://..."
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          onPressEnter={onImportUrl}
        />
      </Modal>

      <Modal
        title={
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
            <EyeOutlined />
            <span
              style={{
                maxWidth: 520,
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}
            >
              {preview?.file_name || '文档内容'}
            </span>
          </span>
        }
        open={preview !== null}
        onCancel={() => setPreview(null)}
        width={860}
        footer={[
          preview?.source_url ? (
            <Button
              key="src"
              href={preview.source_url}
              target="_blank"
              rel="noreferrer"
              icon={<LinkOutlined />}
            >
              查看原网页
            </Button>
          ) : null,
          <Button key="close" type="primary" onClick={() => setPreview(null)}>
            关闭
          </Button>,
        ]}
      >
        <Spin spinning={previewLoading}>
          <div
            style={{
              maxHeight: '64vh',
              overflowY: 'auto',
              padding: '4px 4px 0',
              minHeight: 120,
            }}
          >
            {preview && !previewLoading && !preview.content && (
              <Empty description="该文档没有可显示的文本内容" />
            )}
            {preview?.content &&
              (preview.is_markdown ? (
                <MarkdownMessage content={preview.content} />
              ) : (
                <pre
                  style={{
                    whiteSpace: 'pre-wrap',
                    wordBreak: 'break-word',
                    fontFamily: 'inherit',
                    fontSize: 14,
                    lineHeight: 1.8,
                    margin: 0,
                  }}
                >
                  {preview.content}
                </pre>
              ))}
            {preview?.truncated && (
              <Typography.Text
                type="secondary"
                style={{ display: 'block', marginTop: 12, fontSize: 12 }}
              >
                内容较长，仅显示前一部分。完整内容请下载原文件查看。
              </Typography.Text>
            )}
          </div>
        </Spin>
      </Modal>
    </div>
  )
}

// ──────────── 图片 Tab ────────────
function ImageTab({ kbId }: { kbId: string }) {
  const [list, setList] = useState<ImageItem[]>([])
  const [loading, setLoading] = useState(false)
  const [view, setView] = useState<'网格' | '列表'>('网格')
  const [uploading, setUploading] = useState(false)
  const pollRef = useRef<number | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const { data } = await imageApi.list(1, 60, undefined, kbId)
      setList(data.items)
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setLoading(false)
    }
  }, [kbId])

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    const hasPending = list.some(
      (i) => i.status === 'pending' || i.status === 'processing',
    )
    if (hasPending && pollRef.current === null) {
      pollRef.current = window.setInterval(load, 3000)
    } else if (!hasPending && pollRef.current !== null) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
    return () => {
      if (pollRef.current !== null) {
        clearInterval(pollRef.current)
        pollRef.current = null
      }
    }
  }, [list, load])

  const onUpload = async (file: File) => {
    setUploading(true)
    const hide = message.loading(`正在上传「${file.name}」，请稍候…`, 0)
    try {
      await imageApi.upload(file, kbId)
      hide()
      message.success('上传成功，正在识别')
      load()
    } catch (e) {
      hide()
      message.error((e as Error).message)
    } finally {
      setUploading(false)
    }
    return false
  }

  const onDelete = async (id: string) => {
    try {
      await imageApi.remove(id)
      message.success('删除成功')
      load()
    } catch (e) {
      message.error((e as Error).message)
    }
  }

  return (
    <div>
      <Dragger
        accept="image/*"
        showUploadList={false}
        beforeUpload={onUpload}
        multiple
        disabled={uploading}
        className="kb-dragger"
      >
        <p className="ant-upload-drag-icon" style={{ marginBottom: 4 }}>
          {uploading ? <LoadingOutlined /> : <InboxOutlined />}
        </p>
        <p className="ant-upload-text" style={{ fontSize: 14 }}>
          {uploading ? '正在上传，请稍候…' : '点击或拖拽图片到此上传到本知识库'}
        </p>
        <p className="ant-upload-hint" style={{ fontSize: 12 }}>
          AI 自动生成描述、物体与场景，可被搜索
        </p>
      </Dragger>

      <div style={{ display: 'flex', justifyContent: 'flex-end', margin: '8px 0' }}>
        <Segmented
          options={['网格', '列表']}
          value={view}
          onChange={(v) => setView(v as '网格' | '列表')}
        />
      </div>

      <Spin spinning={loading}>
        {list.length === 0 ? (
          <Empty style={{ padding: '40px 0' }} description="这个知识库还没有图片" />
        ) : view === '网格' ? (
          <div className="kb-img-grid">
            {list.map((img) => (
              <div key={img.id} className="kb-img-card">
                <div className="kb-img-thumb">
                  <AuthenticatedImage
                    src={img.url}
                    alt={img.file_name}
                    style={{ maxWidth: '100%', maxHeight: '100%', objectFit: 'contain' }}
                  />
                </div>
                <div className="kb-img-foot">
                  <span className="kb-img-name" title={img.file_name}>
                    {img.file_name}
                  </span>
                  <Popconfirm
                    title="删除图片"
                    description="删除后不可恢复，确定吗？"
                    icon={<ExclamationCircleFilled style={{ color: '#FF5D34' }} />}
                    okText="删除"
                    cancelText="取消"
                    okButtonProps={{ danger: true }}
                    onConfirm={() => onDelete(img.id)}
                  >
                    <Button size="small" type="text" danger>
                      删除
                    </Button>
                  </Popconfirm>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="kb-list">
            {list.map((img) => (
              <div key={img.id} className="kb-row">
                <div className="kb-row-icon">🖼️</div>
                <div className="kb-row-main">
                  <div className="kb-row-title" title={img.file_name}>
                    {img.file_name}
                  </div>
                  <div className="kb-row-meta">
                    <span>{img.scene || '识别中'}</span>
                  </div>
                </div>
                <div className="kb-row-actions">
                  <Popconfirm
                    title="删除图片"
                    description="删除后不可恢复，确定吗？"
                    icon={<ExclamationCircleFilled style={{ color: '#FF5D34' }} />}
                    okText="删除"
                    cancelText="取消"
                    okButtonProps={{ danger: true }}
                    onConfirm={() => onDelete(img.id)}
                  >
                    <Button size="small" type="text" danger>
                      删除
                    </Button>
                  </Popconfirm>
                </div>
              </div>
            ))}
          </div>
        )}
      </Spin>
    </div>
  )
}
