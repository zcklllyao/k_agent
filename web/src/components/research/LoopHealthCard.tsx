/**
 * Loop 健康度卡片 —— V0.0.5 ② Verifier Loop 可观测面板。
 *
 * 展示近 30 天:
 * - 总运行数 / 一次通过率 / 平均迭代 / 平均评分
 * - 状态分布(passed / exceeded / failed)
 * - 失败维度归因 top
 * - verifier 实际跑的 kind 分布(same vs cross)
 *
 * 完全在 HomePage 内复用,无 Loop 数据时不显示。
 */
import { Card, Empty, Progress, Space, Tag, Tooltip, Typography } from 'antd'
import { ExclamationCircleOutlined } from '@ant-design/icons'

import type { LoopHealthData } from '@/api/dashboard'

const { Text } = Typography

interface Props {
  data: LoopHealthData
}

const KIND_LABEL: Record<string, string> = {
  same: '同模型 critic',
  cross: '跨家族 verifier',
  '(none)': '未启用',
}

export default function LoopHealthCard({ data }: Props) {
  if (data.total === 0) {
    return (
      <Card
        title={<span style={{ fontWeight: 600 }}>📊 Loop 健康度(近 {data.days} 天)</span>}
        size="small"
        styles={{ body: { padding: 16 } }}
      >
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description="还没有 Verifier Loop 运行记录,跑一次深度研究后就能看到了"
        />
      </Card>
    )
  }

  const passRate = data.total > 0 ? (data.passed / data.total) * 100 : 0

  const topFail = data.failure_dims[0]

  return (
    <Card
      title={
        <Space wrap size={8}>
          <span style={{ fontWeight: 600 }}>📊 Loop 健康度</span>
          <Text type="secondary" style={{ fontSize: 12 }}>
            近 {data.days} 天
          </Text>
        </Space>
      }
      size="small"
      styles={{ body: { padding: 16 } }}
    >
      {/* 顶部 KPI 一行 */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(4, 1fr)',
          gap: 12,
          marginBottom: 14,
        }}
      >
        <KpiBox label="总运行" value={data.total} />
        <KpiBox
          label="一次通过率"
          value={`${Math.round(data.one_shot_pass_rate * 100)}%`}
          tone={data.one_shot_pass_rate >= 0.6 ? 'good' : 'warn'}
        />
        <KpiBox label="平均迭代" value={data.avg_iterations.toFixed(1)} />
        <KpiBox
          label="平均评分"
          value={data.avg_final_score ? data.avg_final_score.toFixed(2) : '-'}
        />
      </div>

      {/* 状态分布进度条 */}
      <div style={{ marginBottom: 14 }}>
        <Space size={6} style={{ marginBottom: 6 }}>
          <Text strong style={{ fontSize: 13 }}>
            状态分布
          </Text>
          <Text type="secondary" style={{ fontSize: 12 }}>
            通过 {data.passed} / 未达标 {data.exceeded} / 失败 {data.failed}
          </Text>
        </Space>
        <Progress
          percent={Math.round(passRate)}
          success={{ percent: Math.round((data.passed / data.total) * 100) }}
          size="small"
          format={(p) => `${p}% 通过`}
          strokeColor="#369F21"
        />
      </div>

      {/* 失败维度归因 */}
      {data.failure_dims.length > 0 && (
        <div style={{ marginBottom: 12 }}>
          <Text strong style={{ fontSize: 13, display: 'block', marginBottom: 6 }}>
            失败维度 Top
          </Text>
          <Space wrap size={6}>
            {data.failure_dims.slice(0, 5).map((d) => (
              <Tooltip key={d.dim} title={`${d.label} 未达硬门槛 ${d.count} 次`}>
                <Tag
                  icon={<ExclamationCircleOutlined />}
                  color={d.dim === topFail?.dim ? 'warning' : 'default'}
                >
                  {d.label}: {d.count}
                </Tag>
              </Tooltip>
            ))}
          </Space>
        </div>
      )}

      {/* Verifier kind 分布(便于 A/B 对照) */}
      {Object.keys(data.verifier_kinds).length > 0 && (
        <div>
          <Text strong style={{ fontSize: 13, display: 'block', marginBottom: 6 }}>
            Verifier 类型
          </Text>
          <Space wrap size={6}>
            {Object.entries(data.verifier_kinds).map(([k, v]) => (
              <Tag
                key={k}
                color={k === 'cross' ? 'purple' : k === 'same' ? 'blue' : 'default'}
              >
                {KIND_LABEL[k] || k}: {v}
              </Tag>
            ))}
          </Space>
        </div>
      )}
    </Card>
  )
}

function KpiBox({
  label,
  value,
  tone,
}: {
  label: string
  value: number | string
  tone?: 'good' | 'warn'
}) {
  const color = tone === 'good' ? '#369F21' : tone === 'warn' ? '#FAAD14' : '#155EEF'
  return (
    <div
      style={{
        border: '1px solid #eef0f4',
        borderRadius: 8,
        padding: '10px 12px',
        textAlign: 'center',
        background: '#fff',
      }}
    >
      <div style={{ fontSize: 20, fontWeight: 700, color }}>{value}</div>
      <div style={{ fontSize: 12, color: '#667085', marginTop: 4 }}>{label}</div>
    </div>
  )
}
