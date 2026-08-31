/**
 * 研究报告质量评分卡 —— V0.0.5 ② Verifier Loop 落地的前端入口。
 *
 * 显示:
 * - verified 徽章(✅ passed / ⚠️ exceeded / ❌ failed)
 * - 加权总分 + 通过阈值 + 迭代次数
 * - 6 维评分雷达图(对比维度硬门槛)
 * - 各轮 feedback 可折叠展开(summary / issues / missing_coverage / wrong_citations / weak_chapters)
 * - 模型审计(generator / verifier 模型名 + verifier kind)
 */
import { Card, Collapse, Empty, Space, Tag, Tooltip, Typography } from 'antd'
import ReactECharts from 'echarts-for-react'
import { CheckCircleFilled, CloseCircleFilled, ExclamationCircleFilled } from '@ant-design/icons'

import type { LoopDetail, LoopIterationDetail } from '@/api/research'

const { Text } = Typography

// 维度展示信息(与后端 rubric/research.py 保持一致)
const DIM_LABELS: { key: string; label: string; threshold: number }[] = [
  { key: 'coverage', label: '覆盖度', threshold: 3 },
  { key: 'faithfulness', label: '引用对齐', threshold: 3 },
  { key: 'depth', label: '论证深度', threshold: 2 },
  { key: 'timeliness', label: '时效性', threshold: 3 },
  { key: 'relevance', label: '相关性', threshold: 3 },
  { key: 'readability', label: '结构与可读', threshold: 2 },
]

interface QualityCardProps {
  detail: LoopDetail
}

function StatusBadge({ status }: { status: LoopDetail['status'] }) {
  if (status === 'passed') {
    return (
      <Tag icon={<CheckCircleFilled />} color="success">
        verified · 通过
      </Tag>
    )
  }
  if (status === 'exceeded') {
    return (
      <Tag icon={<ExclamationCircleFilled />} color="warning">
        unverified · 复核未达标
      </Tag>
    )
  }
  if (status === 'failed') {
    return (
      <Tag icon={<CloseCircleFilled />} color="error">
        失败
      </Tag>
    )
  }
  return <Tag color="processing">复核中</Tag>
}

function RadarChart({ iterations }: { iterations: LoopIterationDetail[] }) {
  // 取最后一轮的评分作为「最终」(更接近通过状态)
  const last = iterations[iterations.length - 1]
  const raw = (last?.scores as { raw?: Record<string, number> })?.raw ?? {}
  const series = DIM_LABELS.map((d) => Number(raw[d.key] ?? 0))
  const thresholds = DIM_LABELS.map((d) => d.threshold)

  const option = {
    tooltip: { trigger: 'item' },
    legend: { data: ['最终评分', '硬门槛'], top: 0, textStyle: { fontSize: 12 } },
    radar: {
      indicator: DIM_LABELS.map((d) => ({ name: d.label, max: 5 })),
      radius: '64%',
      splitNumber: 5,
      axisName: { color: '#475467', fontSize: 12 },
      splitLine: { lineStyle: { color: '#e5e7eb' } },
      splitArea: { areaStyle: { color: ['#f9fafb', '#fff'] } },
    },
    series: [
      {
        type: 'radar',
        data: [
          {
            value: series,
            name: '最终评分',
            areaStyle: { color: 'rgba(21, 94, 239, 0.20)' },
            lineStyle: { color: '#155EEF', width: 2 },
            itemStyle: { color: '#155EEF' },
          },
          {
            value: thresholds,
            name: '硬门槛',
            lineStyle: { color: '#FFA940', width: 1, type: 'dashed' },
            itemStyle: { color: '#FFA940' },
            areaStyle: { opacity: 0 },
          },
        ],
      },
    ],
  }
  return <ReactECharts option={option} style={{ height: 280 }} />
}

function IterationDetail({ it }: { it: LoopIterationDetail }) {
  const total = (it.scores as { total?: number })?.total
  const fb = it.feedback || {}
  return (
    <Space direction="vertical" size={6} style={{ width: '100%' }}>
      <Space wrap size={6}>
        <Tag color="blue">总分 {typeof total === 'number' ? total.toFixed(2) : '-'}</Tag>
        <Tag>决策: {it.decision}</Tag>
        {it.duration_ms != null && <Tag>{Math.round(it.duration_ms / 1000)}s</Tag>}
        {it.repair_action?.kind && it.repair_action.kind !== 'force_exceed' && (
          <Tag color="orange">回炉: {it.repair_action.kind}</Tag>
        )}
      </Space>
      {fb.summary && (
        <Text type="secondary" style={{ fontSize: 13 }}>
          {fb.summary}
        </Text>
      )}
      {fb.issues && fb.issues.length > 0 && (
        <div>
          <Text strong style={{ fontSize: 12 }}>
            发现问题:
          </Text>
          <ul style={{ margin: '4px 0 0 16px', paddingLeft: 16, fontSize: 12.5, color: '#475467' }}>
            {fb.issues.slice(0, 5).map((iss, i) => (
              <li key={i}>
                <Text type="warning">{iss.dim}</Text>:{iss.detail}
              </li>
            ))}
          </ul>
        </div>
      )}
      {fb.missing_coverage && fb.missing_coverage.length > 0 && (
        <div>
          <Text strong style={{ fontSize: 12 }}>
            覆盖缺漏:
          </Text>
          <ul style={{ margin: '4px 0 0 16px', paddingLeft: 16, fontSize: 12.5, color: '#475467' }}>
            {fb.missing_coverage.slice(0, 4).map((m, i) => (
              <li key={i}>{m}</li>
            ))}
          </ul>
        </div>
      )}
      {it.repair_action?.patch_queries && it.repair_action.patch_queries.length > 0 && (
        <Text style={{ fontSize: 12, color: '#667085' }}>
          📍 补搜:{it.repair_action.patch_queries.join(' / ')}
        </Text>
      )}
      {it.repair_action?.rewrite_chapters && it.repair_action.rewrite_chapters.length > 0 && (
        <Text style={{ fontSize: 12, color: '#667085' }}>
          ✏️ 重写章节:{it.repair_action.rewrite_chapters.join('、')}
        </Text>
      )}
    </Space>
  )
}

export default function QualityCard({ detail }: QualityCardProps) {
  const finalTotal = detail.final_score
  const passRate = detail.pass_threshold
  return (
    <Card
      title={
        <Space wrap size={8}>
          <span style={{ fontWeight: 600 }}>📊 质量复核</span>
          <StatusBadge status={detail.status} />
          {typeof finalTotal === 'number' && (
            <Tag color={finalTotal >= passRate ? 'success' : 'warning'}>
              加权总分 {finalTotal.toFixed(2)} / 通过阈值 {passRate.toFixed(2)}
            </Tag>
          )}
          <Tag>
            已执行 {detail.iterations} 轮 / 最多 {detail.max_iterations} 轮
          </Tag>
        </Space>
      }
      size="small"
      style={{ borderColor: '#e5e7eb' }}
      styles={{ body: { padding: 12 } }}
    >
      <Space direction="vertical" size={12} style={{ width: '100%' }}>
        {/* 模型审计 */}
        <Space wrap size={6} style={{ fontSize: 12 }}>
          <Tooltip title="生成报告的对话模型">
            <Tag color="default">Generator: {detail.generator_model || '-'}</Tag>
          </Tooltip>
          <Tooltip title="独立 Verifier 模型(同 = self-critique 基线 / 跨 = 异源审稿)">
            <Tag color="purple">
              Verifier({detail.verifier_kind || '-'}): {detail.verifier_model || '-'}
            </Tag>
          </Tooltip>
          {detail.note && <Tag color="orange">note: {detail.note}</Tag>}
        </Space>

        {/* 雷达图(用最后一轮评分作为最终) */}
        {detail.iterations_detail.length > 0 ? (
          <RadarChart iterations={detail.iterations_detail} />
        ) : (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无评分数据" />
        )}

        {/* 各轮 feedback 折叠 */}
        {detail.iterations_detail.length > 0 && (
          <Collapse
            size="small"
            items={detail.iterations_detail.map((it) => ({
              key: String(it.iteration_no),
              label: (
                <Space size={6}>
                  <span>第 {it.iteration_no} 轮</span>
                  <Tag color={it.decision === 'pass' ? 'success' : 'warning'}>{it.decision}</Tag>
                </Space>
              ),
              children: <IterationDetail it={it} />,
            }))}
          />
        )}
      </Space>
    </Card>
  )
}
