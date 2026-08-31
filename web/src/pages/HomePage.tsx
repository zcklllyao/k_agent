import { useEffect, useMemo, useState } from 'react'
import { Button, Card, Col, Modal, Row, Tag, Tooltip } from 'antd'
import {
  ArrowRightOutlined,
  BookOutlined,
  BulbOutlined,
  CheckCircleFilled,
  CommentOutlined,
  DeploymentUnitOutlined,
  ExperimentOutlined,
  HddOutlined,
  RightOutlined,
  SettingOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import dayjs from 'dayjs'
import {
  dashboardApi,
  type DailyReview,
  type OverviewData,
} from '@/api/dashboard'
import { emotionApi, type EmotionProfile } from '@/api/emotion'
import { memoryApi, type Insight } from '@/api/memories'
import { researchApi, type ReportBrief } from '@/api/research'
import { modelApi, type ModelConfigItem } from '@/api/models'
import { useAuthStore } from '@/stores/authStore'

const WELCOME_SEEN_KEY = 'k-agent_welcome_seen'

/**
 * 仪表盘 —— V0.0.5 收尾大瘦身:只保留日常真正高频用的 4 块。
 *
 * 保留:① 欢迎横幅 / ② 今日回顾+关怀 / ③ 新手引导(条件) / ④ 功能一览(主入口导航)
 *
 * 去掉:数据概览 6 KPI + 4 张大 ECharts(知识库分类/记忆新增/情绪趋势/情绪分布)
 *      + Agent 简报列表 + 快速提问输入框(对话页本身就一个输入框,仪表盘不需要二重)。
 *      Agent 工程指标(Loop 健康度 + 成本)迁去「执行轨迹 /traces」聚合在一起。
 */
export default function HomePage() {
  const navigate = useNavigate()
  const user = useAuthStore((s) => s.user)
  const [review, setReview] = useState<DailyReview | null>(null)
  const [overview, setOverview] = useState<OverviewData | null>(null)
  const [models, setModels] = useState<ModelConfigItem[] | null>(null)
  const [welcomeOpen, setWelcomeOpen] = useState(false)
  // V0.0.5 仪表盘补三块"有意义"的卡:
  // - 当前情绪画像(感知层面)
  // - AI 眼中的你(洞察,记忆层面)
  // - 最近一次研究(Agent 替你干活的痕迹)
  const [emotion, setEmotion] = useState<EmotionProfile | null>(null)
  const [insights, setInsights] = useState<Insight[]>([])
  const [recentReport, setRecentReport] = useState<ReportBrief | null>(null)

  const closeWelcome = () => {
    localStorage.setItem(WELCOME_SEEN_KEY, '1')
    setWelcomeOpen(false)
  }

  useEffect(() => {
    let cancelled = false
    let pollTimer: ReturnType<typeof setTimeout> | null = null
    let polls = 0

    const fetchReview = () => {
      dashboardApi
        .dailyReview()
        .then(({ data }) => {
          if (cancelled) return
          setReview(data)
          if (data.generating && polls < 10) {
            polls += 1
            pollTimer = setTimeout(fetchReview, 3000)
          }
        })
        .catch(() => {})
    }

    void (async () => {
      try {
        // overview 仍要拉(下面 quickSteps 判断 documents/conversations 用),
        // 但页面已不再渲染 6 KPI / 4 张图,只取 counts 字段。
        const { data } = await dashboardApi.overview()
        if (!cancelled) setOverview(data)
      } catch {
        // 统计失败不致命
      }
      modelApi
        .list()
        .then(({ data }) => setModels(data))
        .catch(() => setModels([]))
      fetchReview()
      // 情绪 / 洞察 / 最近研究 —— 失败一律降级为空,不影响其他渲染
      emotionApi
        .current()
        .then(({ data }) => {
          if (!cancelled) setEmotion(data)
        })
        .catch(() => {})
      memoryApi
        .insights()
        .then(({ data }) => {
          if (!cancelled) setInsights(data)
        })
        .catch(() => {})
      researchApi
        .list(1, 5)
        .then(({ data }) => {
          if (cancelled) return
          // 取最近 1 条已完成的研究
          const first = data.items.find((it) => it.status === 'done') ?? null
          setRecentReport(first)
        })
        .catch(() => {})
    })()

    return () => {
      cancelled = true
      if (pollTimer) clearTimeout(pollTimer)
    }
  }, [])

  const c = overview?.counts

  // 快速开始:根据已配模型类型 + 是否有内容判断完成度
  const modelTypes = useMemo(
    () => new Set((models ?? []).map((m) => m.type)),
    [models],
  )
  const hasChat = modelTypes.has('chat') || modelTypes.has('multimodal')
  const hasEmbedding = modelTypes.has('embedding')
  const hasDocs = (c?.documents ?? 0) > 0
  const hasChatted = (c?.conversations ?? 0) > 0

  const quickSteps = [
    {
      done: hasChat,
      title: '配置对话模型(必做)',
      icon: <SettingOutlined />,
      desc: '先去「模型配置」加一个对话大模型。推荐智谱 GLM / DeepSeek(注册即送免费额度)。',
      action: () => navigate('/settings/models'),
      btn: hasChat ? '已配置' : '去配置',
    },
    {
      done: hasEmbedding,
      title: '配置向量模型',
      icon: <SettingOutlined />,
      desc: '加一个 embedding 模型,知识库和记忆的语义检索靠它。',
      action: () => navigate('/settings/models'),
      btn: hasEmbedding ? '已配置' : '去配置',
    },
    {
      done: hasDocs,
      title: '建立你的知识库(可选)',
      icon: <BookOutlined />,
      desc: '上传文档或导入网页,系统自动分块、向量化,之后 AI 回答会引用你的资料。',
      action: () => navigate('/knowledge'),
      btn: hasDocs ? '去管理' : '去上传',
    },
    {
      done: hasChatted,
      title: '开始智能对话',
      icon: <CommentOutlined />,
      desc: '配好对话模型就能直接聊。AI 会自动调用知识库、记忆、联网工具回答。',
      action: () => navigate('/chat'),
      btn: hasChatted ? '继续对话' : '去对话',
    },
  ]

  // 功能导航(精简到 6 个最高频入口)
  const features = [
    { icon: <CommentOutlined />, label: '智能对话', desc: 'Agent 工具编排问答', to: '/chat', color: '#155EEF' },
    { icon: <BookOutlined />, label: '知识库', desc: '文档/网页 RAG 检索', to: '/knowledge', color: '#369F21' },
    { icon: <HddOutlined />, label: '记忆图谱', desc: '实体关系与画像', to: '/memory', color: '#7C4DFF' },
    { icon: <ExperimentOutlined />, label: '深度研究', desc: '一句话产出带来源报告', to: '/research', color: '#EB2F96' },
    { icon: <DeploymentUnitOutlined />, label: '图谱可视化', desc: '关系网络与时间线', to: '/graph', color: '#FF8A34' },
    { icon: <ThunderboltOutlined />, label: '执行轨迹', desc: 'Loop 健康度与成本', to: '/traces', color: '#FAAD14' },
  ]

  const allReady = hasChat && hasEmbedding
  const finishedSteps = quickSteps.filter((s) => s.done).length
  // 基础没配好(缺对话或向量模型)= 新用户态:首屏聚焦引导
  // models 未加载完(null)时不判定,避免闪现
  const needsSetup = models !== null && !allReady

  // 欢迎引导:仅对「还没配好基础」的新用户首次弹一次,老用户不打扰
  useEffect(() => {
    if (needsSetup && !localStorage.getItem(WELCOME_SEEN_KEY)) {
      setWelcomeOpen(true)
    }
  }, [needsSetup])

  // ── 区块 ──

  const welcomeModal = (
    <Modal
      open={welcomeOpen}
      onCancel={closeWelcome}
      centered
      width={460}
      footer={null}
      title={null}
    >
      <div style={{ textAlign: 'center', padding: '8px 4px' }}>
        <div style={{ fontSize: 34, marginBottom: 6 }}>👋</div>
        <h2 style={{ margin: '0 0 8px', fontSize: 22 }}>欢迎使用 k-agent</h2>
        <p style={{ color: '#475467', lineHeight: 1.85, margin: '0 0 14px' }}>
          这是你的个人 AI 知识库 + 记忆助手:和 AI 对话、把文档/网页存进知识库让它引用、
          它还会自动记住你聊过的事,越用越懂你。
        </p>
        <div
          style={{
            background: '#F2F7FF',
            border: '1px solid #DBE7FF',
            borderRadius: 12,
            padding: '12px 16px',
            textAlign: 'left',
            color: '#1D2129',
            lineHeight: 1.8,
            marginBottom: 18,
          }}
        >
          <b>开始前只需一步:</b>配置一个大模型 API。
          <br />
          推荐 <b>智谱 GLM</b> 或 <b>DeepSeek</b>(注册即送免费额度),
          在「模型配置」页填入 API Key 即可。
        </div>
        <div style={{ display: 'flex', gap: 10, justifyContent: 'center' }}>
          <Button
            type="primary"
            size="large"
            onClick={() => {
              closeWelcome()
              navigate('/settings/models')
            }}
          >
            去配置模型
          </Button>
          <Button size="large" onClick={closeWelcome}>
            先随便逛逛
          </Button>
        </div>
      </div>
    </Modal>
  )

  const quickStartCard = (
    <Card
      style={{ marginBottom: 22, borderRadius: 16 }}
      styles={{ body: { padding: 22 } }}
      title={
        <span>
            🚀 {needsSetup ? '开始使用 k-agent' : '快速开始'}
          <span style={{ color: '#98A2B3', fontWeight: 400, fontSize: 13, marginLeft: 10 }}>
            {finishedSteps}/{quickSteps.length} 已完成
          </span>
        </span>
      }
      extra={
        allReady ? (
          <Tag color="success" icon={<CheckCircleFilled />}>
            基础配置已就绪
          </Tag>
        ) : (
          <Tag color="warning">第一步:先配置对话模型</Tag>
        )
      }
    >
      {needsSetup && (
        <p style={{ margin: '0 0 16px', color: '#475467', lineHeight: 1.8 }}>
          完成下面几步,就能开始和你的 AI 助手对话啦 👇 其中{' '}
          <b style={{ color: '#155EEF' }}>配置对话模型是必做项</b>,没配好其他功能都用不了。
        </p>
      )}
      <Row gutter={[14, 14]}>
        {quickSteps.map((step, i) => {
          const firstTodo = quickSteps.findIndex((s) => !s.done)
          const isCurrent = !step.done && i === firstTodo
          return (
            <Col xs={24} sm={12} lg={6} key={step.title}>
              <div
                className={`qs-step${step.done ? ' qs-step--done' : ''}`}
                style={
                  isCurrent
                    ? { borderColor: '#155EEF', boxShadow: '0 0 0 2px rgba(21,94,239,0.12)' }
                    : undefined
                }
              >
                <div className="qs-step__num">
                  {step.done ? <CheckCircleFilled /> : i + 1}
                </div>
                <div style={{ display: 'flex', flexDirection: 'column' }}>
                  <div className="qs-step__title">
                    {step.icon} {step.title}
                  </div>
                  <div className="qs-step__desc">{step.desc}</div>
                  <Button
                    type={step.done ? 'default' : 'primary'}
                    size="small"
                    style={{ marginTop: 10, alignSelf: 'flex-start' }}
                    onClick={step.action}
                  >
                    {step.btn} <ArrowRightOutlined />
                  </Button>
                </div>
              </div>
            </Col>
          )
        })}
      </Row>
    </Card>
  )

  const featuresCard = (
    <Card
      title="✨ 功能一览"
      style={{ marginBottom: 22, borderRadius: 16 }}
      styles={{ body: { padding: 18 } }}
    >
      <Row gutter={[14, 14]}>
        {features.map((f) => (
          <Col xs={12} sm={8} md={8} lg={6} xl={6} key={f.label}>
            <div
              className="qs-step"
              style={{ cursor: 'pointer', alignItems: 'center' }}
              onClick={() => navigate(f.to)}
            >
              <div
                className="stat-card__icon"
                style={{ background: `${f.color}1a`, color: f.color, marginBottom: 0 }}
              >
                {f.icon}
              </div>
              <div>
                <div className="qs-step__title">{f.label}</div>
                <div className="qs-step__desc" style={{ marginTop: 2 }}>
                  {f.desc}
                </div>
              </div>
            </div>
          </Col>
        ))}
      </Row>
    </Card>
  )

  // 😊 今日心情小药丸 —— 合并到「今日回顾」卡右上角 extra,不单独占行。
  const moodEmoji = (() => {
    if (!emotion) return '🙂'
    if (emotion.avg_valence > 0.3) return '😊'
    if (emotion.avg_valence > 0) return '🙂'
    if (emotion.avg_valence > -0.3) return '😐'
    return '😔'
  })()
  const moodColor = (() => {
    if (!emotion) return '#155EEF'
    if (emotion.health_index >= 60) return '#369F21'
    if (emotion.health_index >= 40) return '#FF8A34'
    return '#FF5D34'
  })()
  const moodChip = emotion && emotion.sample_count > 0 && (
    <Tooltip title={`基于近期 ${emotion.sample_count} 条对话感知 · 点击查看记忆画像`}>
      <span
        onClick={() => navigate('/memory')}
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 6,
          padding: '4px 12px',
          background: `${moodColor}14`,
          border: `1px solid ${moodColor}33`,
          borderRadius: 999,
          cursor: 'pointer',
          fontSize: 13,
          color: '#1D2129',
          transition: 'transform 0.15s',
          userSelect: 'none',
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.transform = 'translateY(-1px)'
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.transform = 'translateY(0)'
        }}
      >
        <span style={{ fontSize: 16 }}>{moodEmoji}</span>
        <span style={{ color: '#98A2B3' }}>今日心情</span>
        <span style={{ fontWeight: 600 }}>{emotion.dominant_emotion || '中性'}</span>
        <span style={{ color: moodColor, fontWeight: 600 }}>{emotion.health_index}%</span>
      </span>
    </Tooltip>
  )

  const reviewCard = (
    <Card
      title="📅 今日回顾"
      style={{ marginBottom: 22, borderRadius: 16 }}
      extra={moodChip || undefined}
    >
      <p style={{ margin: 0, color: '#475467', lineHeight: 1.8, whiteSpace: 'pre-wrap' }}>
        {review?.content ?? '加载中…'}
      </p>
      {review?.care && (
        <div className="daily-care">
          <span className="daily-care-text">💛 {review.care}</span>
          <Button
            size="small"
            type="primary"
            ghost
            icon={<CommentOutlined />}
            onClick={() =>
              navigate(`/chat?greeting=${encodeURIComponent(review.care ?? '')}`)
            }
          >
            聊聊
          </Button>
        </div>
      )}
    </Card>
  )

  // � 今日心情已合并到今日回顾卡 extra(见上),此处保留 AI 洞察分隔
  const topInsights = useMemo(
    () =>
      [...insights]
        .sort((a, b) => (b.importance ?? 0) - (a.importance ?? 0))
        .slice(0, 3),
    [insights],
  )
  const insightsCard = topInsights.length > 0 && (
    <Card
      title={
        <span>
          <BulbOutlined style={{ color: '#FAAD14', marginRight: 6 }} />
          AI 眼中的你
          <span style={{ color: '#98A2B3', fontWeight: 400, fontSize: 12, marginLeft: 10 }}>
            从你的对话与记忆中提炼的洞察
          </span>
        </span>
      }
      style={{ marginBottom: 22, borderRadius: 16 }}
      styles={{ body: { padding: 14 } }}
      extra={
        <Button type="link" size="small" onClick={() => navigate('/memory')}>
          全部洞察
        </Button>
      }
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {topInsights.map((it) => (
          <div
            key={it.id}
            onClick={() => navigate('/memory')}
            style={{
              display: 'flex',
              alignItems: 'flex-start',
              gap: 12,
              padding: '12px 14px',
              borderRadius: 12,
              background: 'linear-gradient(135deg, #fff8e6 0%, #ffffff 65%)',
              border: '1px solid #ffe7a3',
              cursor: 'pointer',
              transition: 'box-shadow 0.18s',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.boxShadow = '0 4px 14px rgba(250,173,20,0.12)'
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.boxShadow = 'none'
            }}
          >
            <span style={{ fontSize: 18 }}>💡</span>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div
                style={{
                  fontSize: 13,
                  fontWeight: 600,
                  color: '#1D2129',
                  marginBottom: 2,
                }}
              >
                {it.theme}
              </div>
              <div
                style={{
                  fontSize: 13,
                  color: '#475467',
                  lineHeight: 1.65,
                }}
              >
                {it.content}
              </div>
            </div>
          </div>
        ))}
      </div>
    </Card>
  )

  // 🔬 最近一次研究 —— 1 行卡,没完成的研究不显示
  const recentResearchCard = recentReport && (
    <Card
      style={{ marginBottom: 22, borderRadius: 16 }}
      styles={{ body: { padding: 14 } }}
    >
      <div
        onClick={() => navigate(`/research?report=${recentReport.id}`)}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 14,
          padding: '6px 4px',
          cursor: 'pointer',
        }}
      >
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            width: 44,
            height: 44,
            borderRadius: 12,
            background: '#f3edff',
            color: '#7C4DFF',
            fontSize: 20,
          }}
        >
          🔬
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 12, color: '#98A2B3', marginBottom: 2 }}>
            最近一次研究
          </div>
          <div
            style={{
              fontSize: 14,
              fontWeight: 600,
              color: '#1D2129',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
          >
            {recentReport.title || recentReport.topic}
          </div>
          {recentReport.created_at && (
            <div style={{ fontSize: 11, color: '#98A2B3', marginTop: 2 }}>
              {dayjs(recentReport.created_at).format('MM-DD HH:mm')} · 点击查看报告
            </div>
          )}
        </div>
        <RightOutlined style={{ color: '#98A2B3', fontSize: 12 }} />
      </div>
    </Card>
  )

  // �💬 快速提问栏已移除(用户反馈不需要,对话页本身就一个输入框,不必重复)

  return (
    <div className="fluid-page">
      {welcomeModal}

      {/* 欢迎横幅 */}
      <div className="dash-hero">
        <h2 className="dash-hero__title">
          你好,{user?.nickname || user?.username || '朋友'} 👋
        </h2>
        <p className="dash-hero__sub">
          {needsSetup
            ? '只差一步就能开始:先配置一个对话大模型,下面有详细引导。'
            : '欢迎使用 k-agent —— 你的个人 AI 知识库与记忆助手。'}
        </p>
      </div>

      {needsSetup ? (
        // 新用户态:聚焦引导
        <>
          {quickStartCard}
          {featuresCard}
        </>
      ) : (
        // 常用态:心情条 + 今日回顾 + AI 洞察 + 最近研究 + (可选)未完成引导 + 功能一览
        // 每个有条件卡片在没数据时自动不渲染,新用户不会看到空卡
        <>
          {reviewCard}
          {insightsCard}
          {recentResearchCard}
          {finishedSteps < quickSteps.length && quickStartCard}
          {featuresCard}
        </>
      )}
    </div>
  )
}
