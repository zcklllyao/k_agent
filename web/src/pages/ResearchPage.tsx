import { useCallback, useEffect, useRef, useState } from 'react'
import {
  App,
  Button,
  Card,
  Drawer,
  Dropdown,
  Empty,
  Input,
  Modal,
  Space,
  Spin,
  Tag,
  Tooltip,
  Typography,
} from 'antd'
import {
  CheckCircleFilled,
  DeleteOutlined,
  DownloadOutlined,
  DownOutlined,
  FileSearchOutlined,
  FileWordOutlined,
  GlobalOutlined,
  HighlightOutlined,
  HistoryOutlined,
  PlusOutlined,
  PrinterOutlined,
  SaveOutlined,
  SendOutlined,
  ShareAltOutlined,
  UnorderedListOutlined,
} from '@ant-design/icons'
import { useLocation, useNavigate } from 'react-router-dom'
import MarkdownMessage from '@/components/MarkdownMessage'
import {
  researchApi,
  streamResearch,
  subscribeResearchEvents,
  type ReportBrief,
  type ReportDetail,
  type ResearchPlan,
  type ResearchSource,
  type ResearchStep,
  type ResearchStreamHandlers,
  type LoopDetail,
} from '@/api/research'

import QualityCard from '@/components/research/QualityCard'

const { TextArea } = Input

const EXAMPLES = [
  '调研 AI Agent / 大模型开发岗秋招：在招公司、岗位要求与投递链接',
  '梳理大模型应用开发岗面试高频考点与准备路径',
  '对比主流向量数据库的选型要点与适用场景',
]

// 后端研究流程的中间阶段也没有最终正文，打开历史任务时需要继续订阅 SSE。
const RUNNING_STATUSES = [
  'pending',
  'planning',
  'searching',
  'distilling',
  'reflecting',
  'curating',
  'writing',
  'summarizing',
]

const PHASE_LABEL: Record<string, string> = {
  planning: '规划中',
  searching: '检索中',
  searching_done: '检索中',
  distilling: '提炼中',
  reflecting: '反思补搜',
  curating: '整理大纲',
  writing: '撰写中',
  summarizing: '汇总中',
}

const SOURCE_META: Record<string, { label: string; color: string }> = {
  web: { label: '网页', color: 'blue' },
  kb: { label: '知识库', color: 'green' },
  mcp: { label: '工具', color: 'purple' },
}

const STEP_ICON: Record<string, string> = {
  search: '🔎',
  web: '🌐',
  fetch: '📄',
  kb: '📚',
  mcp: '🔧',
  distill: '✨',
  stage: '🧭',
  write: '✍️',
}

export default function ResearchPage() {
  const { message } = App.useApp()
  const location = useLocation()
  const navigate = useNavigate()
  const [reports, setReports] = useState<ReportBrief[]>([])
  const [topic, setTopic] = useState('')
  const [running, setRunning] = useState(false)
  const [currentId, setCurrentId] = useState<string | null>(null)
  const [polishing, setPolishing] = useState(false)
  const [saving, setSaving] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [shareOpen, setShareOpen] = useState(false)
  const [shareUrl, setShareUrl] = useState('')
  const [shareId, setShareId] = useState('')
  const [sharing, setSharing] = useState(false)
  const [notifying, setNotifying] = useState(false)

  // 流式状态
  const [phase, setPhase] = useState('')
  const [statusDetail, setStatusDetail] = useState('')
  const [plan, setPlan] = useState<ResearchPlan | null>(null)
  const [sources, setSources] = useState<ResearchSource[]>([])
  const [steps, setSteps] = useState<ResearchStep[]>([])
  const [liveText, setLiveText] = useState('')
  const [finalMd, setFinalMd] = useState<string | null>(null)
  const [detail, setDetail] = useState<ReportDetail | null>(null)
  const [loadingDetail, setLoadingDetail] = useState(false)
  // V0.0.5 ② Verifier Loop:实时进度 + 完成后的详情
  const [loopDetail, setLoopDetail] = useState<LoopDetail | null>(null)
  // 进度面板展开态：桌面默认展开，手机默认收起（省屏幕）
  const isMobile =
    typeof window !== 'undefined' && window.matchMedia('(max-width: 768px)').matches
  const [feedOpen, setFeedOpen] = useState(!isMobile)
  const [historyDrawerOpen, setHistoryDrawerOpen] = useState(false)

  const abortRef = useRef<AbortController | null>(null)
  const bodyRef = useRef<HTMLDivElement>(null)
  // 当前 report id 的 ref(避免 SSE 回调闭包读到旧值)
  const currentIdRef = useRef<string | null>(null)

  const loadReports = useCallback(async () => {
    try {
      const res = await researchApi.list(1, 50)
      setReports(res.data.items)
    } catch {
      /* 忽略 */
    }
  }, [])

  useEffect(() => {
    loadReports()
    return () => abortRef.current?.abort()
  }, [loadReports])

  // 深链：?report=<id> 自动打开某份报告（来自任务运行历史/首页简报跳转）
  useEffect(() => {
    const id = new URLSearchParams(location.search).get('report')
    if (id) openReport(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.search])

  const stepsRef = useRef<HTMLDivElement>(null)

  // 流式时自动滚到底部
  useEffect(() => {
    if (running && bodyRef.current) {
      bodyRef.current.scrollTop = bodyRef.current.scrollHeight
    }
  }, [liveText, running])

  // 活动流自动滚到最新
  useEffect(() => {
    if (stepsRef.current) {
      stepsRef.current.scrollTop = stepsRef.current.scrollHeight
    }
  }, [steps])

  const resetLive = () => {
    setPhase('')
    setStatusDetail('')
    setPlan(null)
    setSources([])
    setSteps([])
    setLiveText('')
    setFinalMd(null)
    setDetail(null)
    setLoopDetail(null)
  }

  const buildHandlers = (): ResearchStreamHandlers => ({
    onMeta: (d) => {
      setCurrentId(d.report_id)
      currentIdRef.current = d.report_id
      setReports((prev) => [
        { id: d.report_id, topic: d.topic, title: null, status: 'planning', created_at: null },
        ...prev,
      ])
    },
    onStatus: (d) => {
      setPhase(d.phase)
      setStatusDetail(d.detail)
      // 阶段切换也作为一条活动记录，让流程更连贯
      if (
        ['writing', 'summarizing', 'planning', 'distilling', 'reflecting', 'curating'].includes(
          d.phase,
        )
      ) {
        setSteps((s) => [...s, { icon: 'stage', ok: true, text: d.detail }])
      }
    },
    onPlan: (p) => setPlan(p),
    onSources: (s) => setSources(s),
    onProgress: (st) => setSteps((s) => [...s, st]),
    onSectionStart: (d) => {
      setLiveText((t) => `${t}\n\n## ${d.heading}\n\n`)
      setSteps((s) => [...s, { icon: 'write', ok: true, text: `撰写：${d.heading}` }])
    },
    onToken: (text) => setLiveText((t) => t + text),
    onReport: (d) => {
      setFinalMd(d.markdown)
      setSources(d.sources)
    },
    onResume: (d) => {
      setPhase(d.phase)
      setPlan(d.plan)
      setSources(d.sources)
      setSteps(d.steps || [])
      setLiveText(d.partial_md || '')
    },
    onDone: () => {
      setRunning(false)
      setFeedOpen(false)
      loadReports()
      // 拉一次 LoopDetail 显示评分卡(loop_enabled 关或 engine 异常时返回 null)
      // 延迟 500ms 给后端 LoopStore.finish_run() 落库 commit 留时间,
      // 避免拉到 status=running 的临时态(loop_finished 事件先到 + store 异步 commit 后到的时序竞态)
      if (currentIdRef.current) {
        const reportId = currentIdRef.current
        window.setTimeout(() => {
          researchApi
            .loopDetail(reportId)
            .then((res) => setLoopDetail(res.data))
            .catch(() => setLoopDetail(null))
        }, 500)
      }
    },
    onIdle: () => setRunning(false),
    onError: (msg) => {
      message.error(msg)
      setRunning(false)
    },
    // V0.0.5 ② Verifier Loop 实时进度
    onLoopStarted: (d) => {
      setSteps((s) => [
        ...s,
        { icon: 'verify', ok: true, text: `质量复核启动(最多 ${d.max_iterations} 轮,通过线 ${d.pass_threshold.toFixed(2)})` },
      ])
    },
    onLoopVerifyStart: (d) => {
      setSteps((s) => [...s, { icon: 'verify', ok: true, text: `第 ${d.iteration} 轮质量复核中…` }])
    },
    onLoopVerifyDone: (d) => {
      const total =
        (d.scores as { total?: number })?.total ?? null
      setSteps((s) => [
        ...s,
        {
          icon: 'verify',
          ok: d.decision === 'pass',
          text: `第 ${d.iteration} 轮评分 ${total != null ? total.toFixed(2) : '-'}(决策:${d.decision})${d.feedback_summary ? ` · ${d.feedback_summary}` : ''}`,
        },
      ])
    },
    onLoopRepairStart: (d) => {
      const action =
        d.kind === 'patch'
          ? `补搜补写(${(d.patch_queries || []).slice(0, 2).join(' / ') || '-'})`
          : d.kind === 'chapter_rewrite'
            ? `重写章节(${(d.rewrite_chapters || []).join('、') || '-'})`
            : d.kind
      setSteps((s) => [
        ...s,
        { icon: 'repair', ok: true, text: `第 ${d.iteration} 轮回炉:${action}` },
      ])
    },
    onLoopFinished: (d) => {
      setSteps((s) => [
        ...s,
        {
          icon: 'verify',
          ok: d.status === 'passed',
          text: `质量复核完成:${d.status === 'passed' ? '通过' : d.status === 'exceeded' ? '未达标(达迭代上限)' : '异常'}${d.final_score != null ? ` · 总分 ${d.final_score.toFixed(2)}` : ''}`,
        },
      ])
    },
  })

  const polishTopic = async () => {
    const raw = topic.trim()
    if (!raw) {
      message.warning('请先输入研究主题再润色')
      return
    }
    if (polishing || running) return
    setPolishing(true)
    try {
      const res = await researchApi.optimizeTopic(raw)
      setTopic(res.data.optimized)
      message.success('已润色')
    } catch (err) {
      message.error((err as { message?: string })?.message || '润色失败')
    } finally {
      setPolishing(false)
    }
  }

  const startResearch = async () => {
    const t = topic.trim()
    if (!t) {
      message.warning('请输入研究主题')
      return
    }
    if (running) return
    abortRef.current?.abort()
    const ac = new AbortController()
    abortRef.current = ac
    resetLive()
    setRunning(true)
    setFeedOpen(!isMobile)
    setCurrentId(null)
    await streamResearch(t, buildHandlers(), ac.signal)
  }

  const openReport = async (id: string) => {
    setHistoryDrawerOpen(false)
    if (running) {
      message.warning('请等待当前研究完成')
      return
    }
    abortRef.current?.abort()
    resetLive()
    setCurrentId(id)
    currentIdRef.current = id
    setLoadingDetail(true)
    try {
      const res = await researchApi.detail(id)
      const d = res.data
      if (RUNNING_STATUSES.includes(d.status)) {
        // 仍在进行中：订阅续传
        setRunning(true)
        setPhase(d.status)
        setPlan(d.outline ?? null)
        setSources(d.sources ?? [])
        const ac = new AbortController()
        abortRef.current = ac
        subscribeResearchEvents(id, buildHandlers(), ac.signal)
      } else {
        setDetail(d)
        setFinalMd(d.report_md)
        setSources(d.sources ?? [])
        setPlan(d.outline ?? null)
        // 拉历史报告对应的 Verifier Loop 评分卡(没跑过 verifier 的老报告会返回 null,卡不显示)
        researchApi
          .loopDetail(id)
          .then((r) => setLoopDetail(r.data))
          .catch(() => setLoopDetail(null))
      }
    } catch {
      message.error('加载报告失败')
    } finally {
      setLoadingDetail(false)
    }
  }

  const newResearch = () => {
    setHistoryDrawerOpen(false)
    if (running) {
      message.warning('请等待当前研究完成')
      return
    }
    abortRef.current?.abort()
    resetLive()
    setCurrentId(null)
    setTopic('')
  }

  const removeReport = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation()
    try {
      await researchApi.remove(id)
      setReports((prev) => prev.filter((r) => r.id !== id))
      if (currentId === id) {
        setCurrentId(null)
        resetLive()
      }
      message.success('已删除')
    } catch {
      message.error('删除失败')
    }
  }

  const displayMd = finalMd ?? detail?.report_md ?? liveText
  const reportTitle = detail?.title || plan?.title || ''

  const downloadMd = () => {
    if (!displayMd) return
    const blob = new Blob([displayMd], { type: 'text/markdown;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${reportTitle || '研究报告'}.md`
    a.click()
    URL.revokeObjectURL(url)
  }

  const saveToKb = async () => {
    if (!currentId || saving) return
    setSaving(true)
    try {
      const res = await researchApi.saveToKb(currentId)
      const kbName = res.data?.kb_name || '知识库'
      message.success(`已存入「${kbName}」，正在解析入库`)
    } catch (err) {
      const m = (err as { message?: string })?.message
      message.error(m || '存入失败')
    } finally {
      setSaving(false)
    }
  }

  const exportDocx = async () => {
    if (!currentId || exporting) return
    setExporting(true)
    try {
      const blob = await researchApi.exportDocx(currentId)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${reportTitle || '研究报告'}.docx`
      a.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      message.error((err as { message?: string })?.message || '导出失败')
    } finally {
      setExporting(false)
    }
  }

  const printReport = () => {
    // 把已渲染的报告正文克隆到 body 顶层再打印：脱离页面的滚动/定高容器，
    // 内容才能正常跨多页分页（直接 window.print 会被 overflow 容器裁成一页）。
    const src = document.querySelector('.research-print')
    if (!src) {
      window.print()
      return
    }
    const holder = document.createElement('div')
    holder.id = 'print-root'
    holder.innerHTML = src.innerHTML
    document.body.appendChild(holder)
    document.body.classList.add('printing')
    const cleanup = () => {
      document.body.classList.remove('printing')
      holder.remove()
      window.removeEventListener('afterprint', cleanup)
    }
    window.addEventListener('afterprint', cleanup)
    window.print()
  }

  const openShare = async () => {
    if (!currentId) return
    setSharing(true)
    try {
      const { data } = await researchApi.share(currentId)
      setShareUrl(`${window.location.origin}/r/${data.share_token}`)
      setShareId(data.id)
      setShareOpen(true)
    } catch (err) {
      message.error((err as { message?: string })?.message || '生成分享失败')
    } finally {
      setSharing(false)
    }
  }

  const notifyReport = async () => {
    if (!currentId || notifying) return
    setNotifying(true)
    try {
      const res = await researchApi.notify(currentId)
      const count = res.data?.sent || 1
      message.success(`已推送到飞书（${count} 个渠道）`)
    } catch (err) {
      message.error((err as { message?: string })?.message || '推送到飞书失败')
    } finally {
      setNotifying(false)
    }
  }

  const copyShareUrl = async () => {
    try {
      await navigator.clipboard.writeText(shareUrl)
      message.success('链接已复制')
    } catch {
      message.warning('复制失败，请手动复制')
    }
  }

  const revokeShare = async () => {
    if (!shareId) return
    try {
      await researchApi.revokeShare(shareId)
      message.success('已取消分享')
      setShareOpen(false)
    } catch (err) {
      message.error((err as { message?: string })?.message || '取消失败')
    }
  }

  const showReport = !!displayMd && displayMd.trim().length > 0
  const canManage = !running && (detail?.status === 'done' || finalMd)

  const historyList = (
    <>
      <Button type="primary" icon={<PlusOutlined />} block onClick={newResearch} style={{ marginBottom: 12 }}>
        新建研究
      </Button>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {reports.length === 0 && (
          <Typography.Text type="secondary" style={{ fontSize: 13 }}>
            还没有研究报告，输入一句话开始吧。
          </Typography.Text>
        )}
        {reports.map((r) => (
          <Card
            key={r.id}
            size="small"
            hoverable
            onClick={() => openReport(r.id)}
            style={{
              cursor: 'pointer',
              borderColor: currentId === r.id ? '#155EEF' : undefined,
            }}
            styles={{ body: { padding: '10px 12px' } }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
              <div style={{ minWidth: 0, flex: 1 }}>
                <div
                  style={{
                    fontWeight: 500,
                    fontSize: 13,
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {r.title || r.topic}
                </div>
                <div style={{ marginTop: 4 }}>
                  {RUNNING_STATUSES.includes(r.status) ? (
                    <Tag color="processing" style={{ marginInlineEnd: 0 }}>
                      进行中
                    </Tag>
                  ) : r.status === 'failed' ? (
                    <Tag color="error" style={{ marginInlineEnd: 0 }}>
                      失败
                    </Tag>
                  ) : (
                    <Tag color="success" style={{ marginInlineEnd: 0 }}>
                      已完成
                    </Tag>
                  )}
                </div>
              </div>
              <Tooltip title="删除">
                <DeleteOutlined
                  onClick={(e) => removeReport(r.id, e)}
                  style={{ color: '#A8A9AA' }}
                />
              </Tooltip>
            </div>
          </Card>
        ))}
      </div>
    </>
  )

  return (
    <div className="fluid-page research-page" style={{ display: 'flex', gap: 20, alignItems: 'flex-start', flexWrap: 'wrap' }}>
      {/* 左：历史报告（桌面端常驻；手机端收进抽屉） */}
      <div className="research-history" style={{ flex: '0 0 260px', minWidth: 220, maxWidth: '100%' }}>
        {historyList}
      </div>

      {/* 手机端历史抽屉 */}
      <Drawer
        title="研究报告"
        placement="left"
        open={historyDrawerOpen}
        onClose={() => setHistoryDrawerOpen(false)}
        width="80%"
      >
        {historyList}
      </Drawer>

      {/* 右：研究主区 */}
      <div style={{ flex: 1, minWidth: 0, width: '100%' }}>
        {/* 手机端顶部工具条：新建 / 历史 */}
        <div className="research-mobile-bar">
          <Button icon={<PlusOutlined />} onClick={newResearch}>
            新建
          </Button>
          <Button icon={<UnorderedListOutlined />} onClick={() => setHistoryDrawerOpen(true)}>
            历史报告{reports.length ? `（${reports.length}）` : ''}
          </Button>
        </div>

        {/* 输入区（初始态：居中引导） */}
        {!showReport && !running && !detail && !loadingDetail && (
          <div className="research-hero">
            <div className="research-hero-icon">
              <FileSearchOutlined />
            </div>
            <h2 className="research-hero-title">深度研究</h2>
            <p className="research-hero-sub">
              用一句话描述主题，AI 会自主规划、联网检索并抓取资料、分章节撰写一份带来源链接的报告。
            </p>

            <div className="research-hero-input">
              <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 6 }}>
                <Button
                  type="text"
                  size="small"
                  icon={<HighlightOutlined />}
                  loading={polishing}
                  onClick={polishTopic}
                  style={{ fontSize: 13 }}
                >
                  AI 润色
                </Button>
              </div>
              <TextArea
                value={topic}
                onChange={(e) => setTopic(e.target.value)}
                placeholder="例如：调研 AI Agent 开发岗秋招的在招公司、岗位要求与投递链接"
                autoSize={{ minRows: 3, maxRows: 6 }}
                onPressEnter={(e) => {
                  if (!e.shiftKey) {
                    e.preventDefault()
                    startResearch()
                  }
                }}
              />
              <Button
                type="primary"
                size="large"
                icon={<FileSearchOutlined />}
                onClick={startResearch}
                block
                style={{ marginTop: 12, height: 44, borderRadius: 10 }}
              >
                开始研究
              </Button>
            </div>

            <div className="research-hero-examples">
              <span className="research-hero-examples-label">试试这些 👇</span>
              <div className="research-hero-chips">
                {EXAMPLES.map((ex) => (
                  <button key={ex} className="research-chip" onClick={() => setTopic(ex)}>
                    {ex}
                  </button>
                ))}
              </div>
            </div>

            <div className="research-flow">
              {[
                { icon: '🧭', t: '规划', d: '拆解提纲与检索角度' },
                { icon: '🔎', t: '检索', d: '多源搜索 + 抓取正文' },
                { icon: '✍️', t: '撰写', d: '分章节撰写并标注引用' },
                { icon: '🔗', t: '成稿', d: '带来源链接，可存知识库' },
              ].map((s, i) => (
                <div key={i} className="research-flow-step">
                  <div className="research-flow-icon">{s.icon}</div>
                  <div className="research-flow-t">{s.t}</div>
                  <div className="research-flow-d">{s.d}</div>
                </div>
              ))}
            </div>
          </div>
        )}

        {loadingDetail && (
          <div style={{ textAlign: 'center', padding: 40 }}>
            <Spin />
          </div>
        )}

        {/* 进度 + 计划 + 来源 */}
        {(running || showReport || !!detail) && (
          <div ref={bodyRef} className="research-body">
            {/* 固定进度面板：滚动正文时始终可见 */}
            {(running || steps.length > 0) && (
              <div className="research-progress">
                <div
                  className="research-progress-head"
                  onClick={() => setFeedOpen((o) => !o)}
                >
                  {running ? (
                    <Spin size="small" />
                  ) : (
                    <CheckCircleFilled style={{ color: '#52C41A', fontSize: 16 }} />
                  )}
                  {running && PHASE_LABEL[phase] && (
                    <Tag color="processing" style={{ marginInlineEnd: 0 }}>
                      {PHASE_LABEL[phase]}
                    </Tag>
                  )}
                  <span className="research-progress-latest">
                    {running
                      ? statusDetail || '研究进行中…'
                      : `研究完成 · 共 ${steps.length} 步`}
                  </span>
                  <DownOutlined
                    className="research-progress-caret"
                    rotate={feedOpen ? 180 : 0}
                  />
                </div>
                {feedOpen && (
                  <div ref={stepsRef} className="research-feed">
                    {steps.map((st, i) => (
                      <div
                        key={i}
                        className={`research-step${st.ok ? '' : ' research-step--warn'}`}
                      >
                        <span className="research-step-icon">
                          {STEP_ICON[st.icon] || '•'}
                        </span>
                        <span className="research-step-text">{st.text}</span>
                      </div>
                    ))}
                    {running && (
                      <div className="research-step research-step--pending">
                        <span className="research-step-icon">
                          <Spin size="small" />
                        </span>
                        <span className="research-step-text">
                          {statusDetail || '处理中…'}
                        </span>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}

            {plan && plan.queries?.length > 0 && (
              <Card size="small" title="检索角度" style={{ marginBottom: 12 }}>
                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                  {plan.queries.map((q, i) => (
                    <Tag key={i} icon={<GlobalOutlined />} color="blue">
                      {q}
                    </Tag>
                  ))}
                </div>
              </Card>
            )}

            {sources.length > 0 && (
              <Card size="small" title={`参考来源（${sources.length}）`} style={{ marginBottom: 12 }}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {sources.map((s) => (
                    <div key={s.index} style={{ fontSize: 13 }}>
                      <Tag color={SOURCE_META[s.type]?.color}>{SOURCE_META[s.type]?.label || s.type}</Tag>
                      [{s.index}]{' '}
                      {s.url ? (
                        <a href={s.url} target="_blank" rel="noreferrer">
                          {s.title || s.url}
                        </a>
                      ) : (
                        <span>{s.title}</span>
                      )}
                    </div>
                  ))}
                </div>
              </Card>
            )}

            {/* 报告正文 */}
            {showReport && (
              <Card
                title={reportTitle || '研究报告'}
                extra={
                  canManage && (
                    <Space size="small" wrap>
                      <Dropdown
                        menu={{
                          items: [
                            {
                              key: 'md',
                              icon: <DownloadOutlined />,
                              label: '下载 Markdown',
                              onClick: downloadMd,
                            },
                            {
                              key: 'docx',
                              icon: <FileWordOutlined />,
                              label: exporting ? '导出中…' : '下载 Word',
                              onClick: exportDocx,
                            },
                            {
                              key: 'print',
                              icon: <PrinterOutlined />,
                              label: '打印 / 存为 PDF',
                              onClick: printReport,
                            },
                          ],
                        }}
                      >
                        <Button icon={<DownloadOutlined />}>
                          下载 <DownOutlined />
                        </Button>
                      </Dropdown>
                      <Button
                        icon={<ShareAltOutlined />}
                        loading={sharing}
                        onClick={openShare}
                      >
                        分享
                      </Button>
                      <Button
                        icon={<SendOutlined />}
                        loading={notifying}
                        onClick={notifyReport}
                      >
                        推送到飞书
                      </Button>
                      {currentId && !running && (
                        <Button
                          icon={<HistoryOutlined />}
                          onClick={() => navigate(`/traces?task_id=${currentId}`)}
                        >
                          执行轨迹
                        </Button>
                      )}
                      <Button
                        type="primary"
                        icon={<SaveOutlined />}
                        loading={saving}
                        onClick={saveToKb}
                      >
                        存入知识库
                      </Button>
                    </Space>
                  )
                }
              >
                <div className="research-print">
                  <h1 className="research-print-title">{reportTitle || '研究报告'}</h1>
                  <MarkdownMessage content={displayMd} />
                </div>
                {running && <span className="research-caret">▍</span>}
              </Card>
            )}

            {/* V0.0.5 ② 质量评分卡(loop_enabled 关或异常时 loopDetail=null 不显示) */}
            {detail?.status === 'done' && !showReport && (
              <Empty
                description="研究已完成，但报告正文为空"
                style={{ marginTop: 24 }}
              />
            )}

            {loopDetail && !running && (
              <div style={{ marginTop: 16 }}>
                <QualityCard detail={loopDetail} />
              </div>
            )}

            {detail?.status === 'failed' && (
              <Empty
                description={`研究失败：${detail.error_msg || '未知错误'}`}
                style={{ marginTop: 24 }}
              />
            )}
          </div>
        )}
      </div>

      <Modal
        title="分享研究报告"
        open={shareOpen}
        onCancel={() => setShareOpen(false)}
        footer={[
          <Button key="revoke" danger onClick={revokeShare}>
            取消分享
          </Button>,
          <Button key="copy" type="primary" onClick={copyShareUrl}>
            复制链接
          </Button>,
        ]}
      >
        <Typography.Paragraph type="secondary" style={{ fontSize: 13 }}>
          公开只读链接，任何人无需登录即可查看这份报告快照（不含你的其他数据）。
        </Typography.Paragraph>
        <Input.TextArea value={shareUrl} readOnly autoSize style={{ marginBottom: 8 }} />
        <Button type="link" href={shareUrl} target="_blank" rel="noreferrer" style={{ paddingLeft: 0 }}>
          在新标签打开预览 →
        </Button>
      </Modal>
    </div>
  )
}
