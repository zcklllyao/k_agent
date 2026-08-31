/**
 * 记忆审查页 —— V0.0.5 ⑤ 人类反馈闭环
 *
 * 两 Tab:
 * - 📊 全景:KPI 网格 + 类型饼图 + 置信度直方 + 30 天趋势 + 纠错统计
 * - 🔍 审查纠错:筛选低置信度实体,逐条 确认/修正/删除,操作落 memory_corrections 表
 */
import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  App,
  Button,
  Card,
  Empty,
  Form,
  Input,
  Modal,
  Popconfirm,
  Segmented,
  Select,
  Space,
  Spin,
  Tag,
  Tooltip,
  Typography,
} from 'antd'
import {
  CheckCircleOutlined,
  DeleteOutlined,
  EditOutlined,
  ReloadOutlined,
} from '@ant-design/icons'
import ReactECharts from 'echarts-for-react'

import {
  memoryApi,
  type ReviewEntity,
  type ReviewOverview,
} from '@/api/memories'

const { Text, Paragraph } = Typography

// 手机端断点 hook(同 MemoryPage 风格)
function useIsMobile() {
  const [m, setM] = useState(
    typeof window !== 'undefined' ? window.innerWidth <= 768 : false,
  )
  useEffect(() => {
    const mq = window.matchMedia('(max-width: 768px)')
    const onChange = (e: MediaQueryListEvent) => setM(e.matches)
    setM(mq.matches)
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [])
  return m
}


export default function ReviewPanel() {
  const [subTab, setSubTab] = useState<'overview' | 'audit'>('overview')
  const [maxConfidence, setMaxConfidence] = useState<number>(0.75)

  return (
    <div>
      <Segmented
        value={subTab}
        onChange={(v) => setSubTab(v as 'overview' | 'audit')}
        options={[
          { label: '📊 我的记忆全景', value: 'overview' },
          { label: '🔍 质量审查与纠错', value: 'audit' },
        ]}
        style={{ marginBottom: 18 }}
      />
      {subTab === 'overview' ? (
        <OverviewPanel
          onJumpToAudit={(threshold) => {
            setMaxConfidence(threshold)
            setSubTab('audit')
          }}
        />
      ) : (
        <AuditPanel maxConfidence={maxConfidence} onChangeMax={setMaxConfidence} />
      )}
    </div>
  )
}

// ── Tab 1:全景 ──

function OverviewPanel({
  onJumpToAudit,
}: {
  onJumpToAudit: (threshold: number) => void
}) {
  const [data, setData] = useState<ReviewOverview | null>(null)
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await memoryApi.reviewOverview(30)
      setData(res.data)
    } catch {
      /* 静默 */
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  if (loading) {
    return <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
  }
  if (!data || data.total_entities === 0) {
    return (
      <Empty description="还没有记忆数据,先去「画像」Tab 主动记住或对话中积累记忆" />
    )
  }

  // KPI 网格(替代单行长句总结)
  const kpis = [
    {
      label: '已记住实体',
      value: data.total_entities,
      sub: `+${data.total_relations} 条关系`,
      color: '#155EEF',
      bg: 'linear-gradient(135deg, #eef4ff 0%, #ffffff 70%)',
    },
    {
      label: '长期记住',
      value: data.long_term,
      sub: '稳定可靠',
      color: '#FAAD14',
      bg: 'linear-gradient(135deg, #fffaf0 0%, #ffffff 70%)',
    },
    {
      label: '你已确认',
      value: data.verified,
      sub: '人类反馈',
      color: '#369F21',
      bg: 'linear-gradient(135deg, #f3fbef 0%, #ffffff 70%)',
    },
    {
      label: '待你确认',
      value: data.pending,
      sub: data.pending > 0 ? '点击处理 →' : '全部已审',
      color: data.pending > 0 ? '#FF7875' : '#98A2B3',
      bg: data.pending > 0
        ? 'linear-gradient(135deg, #fff5f5 0%, #ffffff 70%)'
        : '#fafafa',
      clickable: data.pending > 0,
    },
  ]

  // 类型分布饼图(图内 label + 右侧图例,避免外部 label 截断)
  const typePie = {
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    legend: {
      type: 'scroll',
      orient: 'vertical',
      right: 8,
      top: 'center',
      itemWidth: 10,
      itemHeight: 10,
      textStyle: { fontSize: 12, color: '#475467' },
    },
    series: [
      {
        type: 'pie',
        radius: ['38%', '68%'],
        center: ['38%', '50%'],
        avoidLabelOverlap: true,
        itemStyle: { borderRadius: 4, borderColor: '#fff', borderWidth: 2 },
        label: { show: false },
        emphasis: {
          label: {
            show: true,
            fontSize: 13,
            fontWeight: 'bold',
            formatter: '{b}\n{d}%',
          },
        },
        data: data.type_distribution.map((t) => ({
          name: t.type,
          value: t.count,
        })),
      },
    ],
  }

  // 置信度直方图(柔和配色,绿→黄→红)
  const confHist = {
    tooltip: { trigger: 'axis' },
    grid: { left: 36, right: 16, top: 24, bottom: 28 },
    xAxis: {
      type: 'category',
      data: data.confidence_buckets.map((b) => b.range),
      axisLine: { lineStyle: { color: '#d6dae0' } },
      axisTick: { show: false },
      axisLabel: { color: '#667085', fontSize: 11 },
    },
    yAxis: {
      type: 'value',
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: '#98A2B3', fontSize: 11 },
      splitLine: { lineStyle: { color: '#f2f4f7' } },
    },
    series: [
      {
        type: 'bar',
        data: data.confidence_buckets.map((b, i) => ({
          value: b.count,
          itemStyle: {
            color:
              i < 2 ? '#FF7875'  // 0~0.4 红(严重)
              : i === 2 ? '#FFA940'  // 0.4~0.6 橙
              : i === 3 ? '#FAAD14'  // 0.6~0.8 黄
              : '#369F21',           // 0.8~1.0 绿
            borderRadius: [4, 4, 0, 0],
          },
        })),
        barWidth: '52%',
        label: {
          show: true,
          position: 'top',
          color: '#475467',
          fontSize: 11,
        },
      },
    ],
  }

  // 趋势折线
  const trend = {
    tooltip: { trigger: 'axis' },
    grid: { left: 36, right: 16, top: 24, bottom: 28 },
    xAxis: {
      type: 'category',
      data: data.trend.map((t) => t.date.slice(5)),
      axisLine: { lineStyle: { color: '#d6dae0' } },
      axisTick: { show: false },
      axisLabel: { color: '#667085', fontSize: 11 },
    },
    yAxis: {
      type: 'value',
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: '#98A2B3', fontSize: 11 },
      splitLine: { lineStyle: { color: '#f2f4f7' } },
    },
    series: [
      {
        type: 'line',
        smooth: true,
        symbol: 'circle',
        symbolSize: 6,
        data: data.trend.map((t) => t.count),
        areaStyle: {
          color: {
            type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: 'rgba(21, 94, 239, 0.28)' },
              { offset: 1, color: 'rgba(21, 94, 239, 0.02)' },
            ],
          },
        },
        lineStyle: { color: '#155EEF', width: 2 },
        itemStyle: { color: '#155EEF', borderColor: '#fff', borderWidth: 2 },
      },
    ],
  }

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      {/* 顶部 KPI 网格 */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
          gap: 12,
        }}
      >
        {kpis.map((k) => (
          <div
            key={k.label}
            onClick={() => k.clickable && onJumpToAudit(0.75)}
            style={{
              background: k.bg,
              border: '1px solid #eef0f4',
              borderRadius: 12,
              padding: '16px 18px',
              cursor: k.clickable ? 'pointer' : 'default',
              transition: 'transform 0.15s, box-shadow 0.15s',
            }}
            onMouseEnter={(e) => {
              if (k.clickable) {
                e.currentTarget.style.transform = 'translateY(-2px)'
                e.currentTarget.style.boxShadow = '0 8px 20px -10px rgba(15, 23, 42, 0.18)'
              }
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.transform = ''
              e.currentTarget.style.boxShadow = ''
            }}
          >
            <div style={{ fontSize: 13, color: '#667085' }}>{k.label}</div>
            <div
              style={{
                fontSize: 30,
                fontWeight: 700,
                color: k.color,
                lineHeight: 1.1,
                marginTop: 6,
              }}
            >
              {k.value}
            </div>
            <div style={{ fontSize: 12, color: '#98A2B3', marginTop: 4 }}>
              {k.sub}
            </div>
          </div>
        ))}
      </div>

      {/* 三张图卡 */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
          gap: 14,
        }}
      >
        <Card
          size="small"
          title={<span style={{ fontWeight: 600 }}>🎨 我的画像维度</span>}
          styles={{ body: { padding: 8 } }}
        >
          <ReactECharts option={typePie} style={{ height: 250 }} />
        </Card>
        <Card
          size="small"
          title={<span style={{ fontWeight: 600 }}>📈 置信度分布</span>}
          extra={
            data.pending > 0 ? (
              <Button
                type="link"
                size="small"
                onClick={() => onJumpToAudit(0.75)}
                style={{ padding: 0 }}
              >
                处理 {data.pending} 待确认 →
              </Button>
            ) : null
          }
          styles={{ body: { padding: 8 } }}
        >
          <ReactECharts
            option={confHist}
            style={{ height: 250 }}
            onEvents={{
              click: (e: unknown) => {
                const p = e as { name?: string }
                const m = (p?.name || '').match(/~(\d+(?:\.\d+)?)/)
                if (m) {
                  const upper = parseFloat(m[1])
                  if (upper <= 0.8) onJumpToAudit(upper)
                }
              },
            }}
          />
        </Card>
        <Card
          size="small"
          title={<span style={{ fontWeight: 600 }}>📅 近 {data.days} 天新增</span>}
          styles={{ body: { padding: 8 } }}
        >
          {data.trend.length === 0 ? (
            <div
              style={{
                height: 250,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: '#98A2B3',
                fontSize: 13,
              }}
            >
              近期无新增 ——
              <br />
              对话或主动记住后会自动累积
            </div>
          ) : (
            <ReactECharts option={trend} style={{ height: 250 }} />
          )}
        </Card>
      </div>

      {/* 纠错历史 */}
      {Object.keys(data.correction_counts).length > 0 && (
        <div
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            alignItems: 'center',
            gap: 10,
            padding: '12px 16px',
            background: '#f9fafb',
            borderRadius: 10,
            border: '1px solid #eef0f4',
          }}
        >
          <Text strong style={{ fontSize: 13 }}>
            ✏️ 你的纠错历史
          </Text>
          {data.correction_counts.confirm && (
            <Tag color="success">已确认 {data.correction_counts.confirm}</Tag>
          )}
          {data.correction_counts.correct && (
            <Tag color="processing">已修正 {data.correction_counts.correct}</Tag>
          )}
          {data.correction_counts.delete && (
            <Tag color="error">已删除 {data.correction_counts.delete}</Tag>
          )}
          <Text type="secondary" style={{ fontSize: 12, marginLeft: 'auto' }}>
            这些操作会作为下一阶段 self-improvement 的训练信号
          </Text>
        </div>
      )}
    </Space>
  )
}

// ── Tab 2:审查纠错 ──

function AuditPanel({
  maxConfidence,
  onChangeMax,
}: {
  maxConfidence: number
  onChangeMax: (v: number) => void
}) {
  const { message } = App.useApp()
  const isMobile = useIsMobile()
  const [items, setItems] = useState<ReviewEntity[]>([])
  const [loading, setLoading] = useState(false)
  const [typeFilter, setTypeFilter] = useState<string | null>(null)
  const [includeVerified, setIncludeVerified] = useState(false)
  const [editing, setEditing] = useState<ReviewEntity | null>(null)
  const [form] = Form.useForm()

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await memoryApi.reviewEntities({
        maxConfidence,
        type: typeFilter || undefined,
        includeVerified,
        limit: 100,
      })
      setItems(res.data)
    } catch (e) {
      message.error((e as { message?: string })?.message || '加载失败')
    } finally {
      setLoading(false)
    }
  }, [maxConfidence, typeFilter, includeVerified, message])

  useEffect(() => {
    load()
  }, [load])

  const typeOptions = useMemo(() => {
    const set = new Set<string>()
    items.forEach((it) => it.type && set.add(it.type))
    return Array.from(set).sort()
  }, [items])

  const onConfirm = async (it: ReviewEntity) => {
    try {
      await memoryApi.reviewConfirm(it.id)
      message.success('已确认')
      setItems((prev) => prev.filter((x) => x.id !== it.id))
    } catch (e) {
      message.error((e as { message?: string })?.message || '确认失败')
    }
  }

  const onDelete = async (it: ReviewEntity) => {
    try {
      await memoryApi.reviewDelete(it.id)
      message.success('已删除')
      setItems((prev) => prev.filter((x) => x.id !== it.id))
    } catch (e) {
      message.error((e as { message?: string })?.message || '删除失败')
    }
  }

  const openEdit = (it: ReviewEntity) => {
    setEditing(it)
    form.setFieldsValue({
      name: it.name,
      type: it.type,
      description: it.description,
    })
  }

  const onSaveCorrect = async () => {
    if (!editing) return
    try {
      const v = await form.validateFields()
      await memoryApi.reviewCorrect(editing.id, {
        name: v.name,
        type: v.type,
        description: v.description,
      })
      message.success('已修正')
      setEditing(null)
      load()
    } catch (e) {
      const err = e as { errorFields?: unknown; message?: string }
      if (!err.errorFields) message.error(err.message || '修正失败')
    }
  }

  return (
    <div>
      {/* 筛选栏 —— Segmented 替代下拉,可一眼看到所有阈值;桌面单行,手机分两行 */}
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'center',
          gap: isMobile ? 10 : 14,
          padding: isMobile ? '12px 14px' : '12px 16px',
          background: '#ffffff',
          border: '1px solid #eef0f4',
          borderRadius: 12,
          marginBottom: 14,
        }}
      >
        {/* 置信度阈值 —— Segmented,选项更直观 */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flex: isMobile ? '1 1 100%' : '0 0 auto' }}>
          {!isMobile && (
            <Text type="secondary" style={{ fontSize: 12, whiteSpace: 'nowrap' }}>
              置信度
            </Text>
          )}
          <Segmented
            size="small"
            value={maxConfidence}
            onChange={(v) => onChangeMax(v as number)}
            block={isMobile}
            options={[
              { label: '≤0.6', value: 0.6 },
              { label: '≤0.75', value: 0.75 },
              { label: '≤0.9', value: 0.9 },
              { label: '全部', value: 1.0 },
            ]}
            style={{ flex: isMobile ? 1 : 'none' }}
          />
        </div>

        {!isMobile && <div style={{ width: 1, height: 18, background: '#eef0f4' }} />}

        {/* 状态:未确认/全部 */}
        <Segmented
          size="small"
          value={includeVerified ? 'all' : 'pending'}
          onChange={(v) => setIncludeVerified(v === 'all')}
          options={[
            { label: '仅未确认', value: 'pending' },
            { label: '含已确认', value: 'all' },
          ]}
          block={isMobile}
          style={{ flex: isMobile ? 1 : 'none' }}
        />

        {!isMobile && <div style={{ width: 1, height: 18, background: '#eef0f4' }} />}

        {/* 类型筛选 —— 仍用 Select(值不固定) */}
        <Select
          size="small"
          value={typeFilter}
          onChange={(v) => setTypeFilter(v || null)}
          placeholder="所有类型"
          allowClear
          style={{
            width: isMobile ? '100%' : 140,
            flex: isMobile ? '1 1 100%' : 'none',
          }}
          options={typeOptions.map((t) => ({ label: t, value: t }))}
        />

        <div style={{ flex: 1 }} />

        {/* 计数 + 刷新 */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            width: isMobile ? '100%' : 'auto',
            justifyContent: isMobile ? 'space-between' : 'flex-end',
          }}
        >
          <Text
            type="secondary"
            style={{ fontSize: 12.5, color: '#667085', whiteSpace: 'nowrap' }}
          >
            {loading ? '加载中…' : (
              <>
                <Text strong style={{ color: '#155EEF', fontSize: 13 }}>
                  {items.length}
                </Text>{' '}
                条待审查
              </>
            )}
          </Text>
          <Tooltip title="刷新">
            <Button
              size="small"
              type="text"
              icon={<ReloadOutlined />}
              onClick={load}
              loading={loading}
            />
          </Tooltip>
        </div>
      </div>

      {/* 卡片列表 */}
      {loading ? (
        <div style={{ textAlign: 'center', padding: 40 }}>
          <Spin />
        </div>
      ) : items.length === 0 ? (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description={
            <span style={{ color: '#475467' }}>
              没有待审查的实体 —— AI 当前萃取质量挺好 ✨
            </span>
          }
          style={{ padding: '40px 0' }}
        />
      ) : (
        <Space direction="vertical" size={10} style={{ width: '100%' }}>
          {items.map((it) => (
            <ReviewCard
              key={it.id}
              item={it}
              isMobile={isMobile}
              onConfirm={() => onConfirm(it)}
              onEdit={() => openEdit(it)}
              onDelete={() => onDelete(it)}
            />
          ))}
        </Space>
      )}

      {/* 修正弹窗 */}
      <Modal
        title="✏️ 修正实体"
        open={!!editing}
        onCancel={() => setEditing(null)}
        onOk={onSaveCorrect}
        okText="保存"
        cancelText="取消"
        width={480}
      >
        <Form form={form} layout="vertical" preserve={false}>
          <Form.Item name="name" label="名称" rules={[{ required: true }]}>
            <Input placeholder="如:复旦大学" />
          </Form.Item>
          <Form.Item name="type" label="类型">
            <Input placeholder="如:组织 / 人物 / 地点 / 偏好" />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea
              rows={3}
              placeholder="一句话说明,如:用户毕业的大学"
            />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

// ── 单个实体审查卡(响应式:操作按钮带文字、底部对齐,主操作高亮) ──

function ReviewCard({
  item,
  isMobile,
  onConfirm,
  onEdit,
  onDelete,
}: {
  item: ReviewEntity
  isMobile: boolean
  onConfirm: () => void
  onEdit: () => void
  onDelete: () => void
}) {
  const pct = Math.round(item.confidence * 100)
  const tone =
    pct >= 85 ? '#369F21' : pct >= 75 ? '#155EEF' : pct >= 60 ? '#FAAD14' : '#FF7875'
  const isWeak = pct < 75 && !item.human_verified

  // 操作按钮:统一带文字、统一尺寸(default),手机三等分,桌面靠右
  const actions = (
    <div
      style={{
        display: isMobile ? 'grid' : 'flex',
        gridTemplateColumns: isMobile ? '1fr 1fr 1fr' : undefined,
        gap: 8,
        marginTop: 12,
        paddingTop: 12,
        borderTop: '1px solid #f4f6f8',
        justifyContent: isMobile ? undefined : 'flex-end',
      }}
    >
      <Button
        type="primary"
        ghost
        icon={<CheckCircleOutlined />}
        onClick={onConfirm}
        disabled={item.human_verified}
        block={isMobile}
      >
        {item.human_verified ? '已确认' : '确认正确'}
      </Button>
      <Button
        icon={<EditOutlined />}
        onClick={onEdit}
        block={isMobile}
      >
        修正
      </Button>
      <Popconfirm
        title="确认删除这条记忆?"
        description="操作会落入纠错记录,可从快照回滚"
        okText="删除"
        okButtonProps={{ danger: true }}
        cancelText="取消"
        onConfirm={onDelete}
      >
        <Button danger icon={<DeleteOutlined />} block={isMobile}>
          删除
        </Button>
      </Popconfirm>
    </div>
  )

  return (
    <div
      style={{
        position: 'relative',
        background: isWeak
          ? 'linear-gradient(180deg, #fffaf2 0%, #ffffff 100%)'
          : '#ffffff',
        border: `1px solid ${isWeak ? '#ffe3a3' : '#eef0f4'}`,
        borderRadius: 12,
        padding: isMobile ? '14px 14px 12px' : '16px 18px 14px',
        transition: 'border-color 0.18s, box-shadow 0.18s',
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.borderColor = isWeak ? '#FFA940' : '#155EEF'
        e.currentTarget.style.boxShadow = '0 6px 14px -8px rgba(15, 23, 42, 0.14)'
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.borderColor = isWeak ? '#ffe3a3' : '#eef0f4'
        e.currentTarget.style.boxShadow = ''
      }}
    >
      {/* 左侧置信度色条 */}
      <div
        style={{
          position: 'absolute',
          left: 0,
          top: 14,
          bottom: 14,
          width: 3,
          borderRadius: 4,
          background: tone,
        }}
      />

      {/* 标题行:名称 + tags + 百分比 */}
      <div style={{ paddingLeft: 10 }}>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            marginBottom: 6,
            flexWrap: 'wrap',
          }}
        >
          <Text
            strong
            style={{
              fontSize: 15.5,
              flex: '1 1 auto',
              minWidth: 0,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
            title={item.name}
          >
            {item.name}
          </Text>
          <Tooltip title={`置信度 ${pct}%`}>
            <span
              style={{
                padding: '1px 9px',
                borderRadius: 999,
                fontSize: 12,
                fontWeight: 600,
                background: `${tone}1a`,
                color: tone,
                whiteSpace: 'nowrap',
                flexShrink: 0,
              }}
            >
              {pct}%
            </span>
          </Tooltip>
        </div>

        {/* 标签行 */}
        {(item.type || item.memory_layer === 'long_term' || item.human_verified) && (
          <Space wrap size={6} style={{ marginBottom: 6 }}>
            {item.type && <Tag color="blue" style={{ margin: 0 }}>{item.type}</Tag>}
            {item.memory_layer === 'long_term' && (
              <Tag color="gold" style={{ margin: 0 }}>长期</Tag>
            )}
            {item.human_verified && (
              <Tag color="success" style={{ margin: 0 }}>已确认</Tag>
            )}
          </Space>
        )}

        {/* 描述 */}
        {item.description && (
          <Paragraph
            type="secondary"
            style={{ margin: '4px 0 0', fontSize: 13, lineHeight: 1.6 }}
            ellipsis={{ rows: 2, tooltip: item.description }}
          >
            {item.description}
          </Paragraph>
        )}

        {/* 关系(最多 3 条) */}
        {item.relations.length > 0 && (
          <div
            style={{
              marginTop: 8,
              paddingLeft: 10,
              borderLeft: '2px solid #EEF4FF',
              fontSize: 12.5,
              color: '#475467',
              lineHeight: 1.7,
            }}
          >
            {item.relations.slice(0, 3).map((r, i) => (
              <div key={i}>
                <Text type="secondary">{r.predicate}</Text> {r.object_name}
              </div>
            ))}
            {item.relations.length > 3 && (
              <Text type="secondary" style={{ fontSize: 11.5 }}>
                …及其他 {item.relations.length - 3} 条
              </Text>
            )}
          </div>
        )}

        {/* 操作按钮 —— 桌面靠右,手机三等分,带文字标签 */}
        {actions}
      </div>
    </div>
  )
}
