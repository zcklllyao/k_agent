import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Button, Result, Spin } from 'antd'
import MarkdownMessage from '@/components/MarkdownMessage'
import { fetchPublicReportShare, type PublicReportShare } from '@/api/research'

// 研究报告公开查看页（无需登录）：只读渲染报告 Markdown 快照。
export default function ReportSharePage() {
  const { token } = useParams<{ token: string }>()
  const navigate = useNavigate()
  const [data, setData] = useState<PublicReportShare | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!token) return
    fetchPublicReportShare(token)
      .then(({ data }) => setData(data))
      .catch((e) => setError((e as Error).message || '分享不存在或已失效'))
      .finally(() => setLoading(false))
  }, [token])

  if (loading) {
    return (
      <div className="share-loading">
        <Spin size="large" />
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="share-page">
        <Result
          status="404"
          title="分享不可用"
          subTitle={error || '该分享链接不存在、已取消或已过期'}
          extra={
            <Button type="primary" onClick={() => navigate('/')}>
              去 k-agent 看看
            </Button>
          }
        />
      </div>
    )
  }

  return (
    <div className="share-page">
      <div className="share-container fluid-narrow">
        <div className="share-header">
          <div aria-label="k-agent" className="share-logo">K</div>
          <div>
            <div className="share-title">{data.title}</div>
            <div className="share-sub">来自 k-agent 的深度研究报告</div>
          </div>
        </div>

        <div className="share-body" style={{ padding: '24px 32px' }}>
          <MarkdownMessage content={data.markdown} />
        </div>

        <div className="share-footer">
          <span>本页内容由用户分享 · 由</span>
          <a onClick={() => navigate('/')}> k-agent </a>
          <span>生成</span>
        </div>
      </div>
    </div>
  )
}
