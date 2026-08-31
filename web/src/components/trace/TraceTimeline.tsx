/**
 * Trace 时间线视图(Gantt 风格)—— 把一次 Agent 任务的所有 span 按时间横向排列。
 *
 * 单层 Drawer 设计:外层是 trace 详情,内层 span 详情直接在时间线上「行内展开」(手风琴),
 * 不再嵌套第二层 Drawer,层级更扁、信息密度更高。
 */
import { useEffect, useMemo, useState } from 'react'
import { Empty, Space, Tag, Typography } from 'antd'

import type { SpanItem, TraceDetail } from '@/api/traces'

const { Text } = Typography

// span_type → 颜色 + label(技术圈通用术语 LLM/MCP 不翻译,其他用中文)
const TYPE_COLORS: Record<string, { bg: string; border: string; label: string }> = {
  planner:   { bg: '#EEF4FF', border: '#155EEF', label: '规划' },
  retriever: { bg: '#F0F7FF', border: '#1677FF', label: '检索' },
  writer:    { bg: '#F3FBEF', border: '#369F21', label: '写作' },
  tool_call: { bg: '#FFF7E6', border: '#FA8C16', label: '工具' },
  mcp_call:  { bg: '#FFF7E6', border: '#FA8C16', label: 'MCP' },
  verifier:  { bg: '#F4F1FE', border: '#7A5AF8', label: '审稿' },
  repair:    { bg: '#FCE7F3', border: '#EC4899', label: '修复' },
  llm_call:  { bg: '#F4F6F8', border: '#667085', label: 'LLM' },
  other:     { bg: '#F4F6F8', border: '#98A2B3', label: '其他' },
}

function colorOf(spanType: string) {
  return TYPE_COLORS[spanType] || TYPE_COLORS.other
}

function fmtMs(ms: number | null | undefined): string {
  if (ms == null) return '-'
  if (ms < 1000) return `${ms} 毫秒`
  if (ms < 60_000) return `${(ms / 1000).toFixed(2)} 秒`
  return `${(ms / 60_000).toFixed(1)} 分钟`
}

function fmtCost(cny: number | null | undefined): string {
  if (cny == null || cny === 0) return '-'
  if (cny < 0.01) return `¥${cny.toFixed(5)}`
  return `¥${cny.toFixed(4)}`
}

function fmtTokens(n: number | null | undefined): string {
  if (n == null || n === 0) return '0'
  if (n < 1000) return String(n)
  return `${(n / 1000).toFixed(1)}k`
}

// 字段中文化(LLM/MCP 等技术圈通用术语保留英文)
const KEY_LABELS: Record<string, string> = {
  'gen_ai.system': '模型厂商',
  'gen_ai.request.temperature': '温度',
  'gen_ai.request.max_tokens': '最大输出',
  'gen_ai.response.finish_reasons': '结束原因',
  'gen_ai.tool.name': '工具',
  'gen_ai.embedding.dimensions': '向量维度',
  'k-agent.chat.iteration': '对话轮次',
  'k-agent.chat.tools_bound': '可用工具数',
  'k-agent.chat.mode': '调用模式',
  'k-agent.tool.name': '工具',
  'k-agent.tool.query': '查询内容',
  'k-agent.tool.provider': '工具来源',
  'k-agent.retrieval.query_count': '检索角度数',
  'k-agent.retrieval.hit_count': '命中条数',
  'k-agent.verifier.kind': '审稿模式',
  'k-agent.verifier.rubric': '评分规则',
  'k-agent.loop.iteration_no': '回炉轮次',
  'k-agent.repair.action': '修复策略',
  'k-agent.vision.mime': '图片类型',
  'k-agent.rerank.doc_count': '待重排数',
  'k-agent.rerank.top_n': '返回前 N',
  'k-agent.distill.source_count': '来源数',
  'k-agent.curator.section_count': '章节数',
  'k-agent.curator.learning_count': '要点数',
  batch_size: '批量大小',
  tool_calls_count: '触发工具数',
  source_count: '采集来源数',
  learning_count: '提炼要点数',
  gap_query_count: '补搜角度数',
  section_index: '当前章节序号',
  section_total: '章节总数',
  content_chars: '正文字数',
  prompt_chars: '提示词字数',
  query_chars: '查询字数',
  doc_count: '文档数',
  total_score: '总分',
  raw_scores: '各维度分',
  output_chars: '返回字数',
  rationale: '决策理由',
  patch_queries: '补搜子查询',
  rewrite_chapters: '重写章节',
  status: '状态',
  messages_count: '消息条数',
  // 后端会逐步补充的「实质内容」字段
  request_summary: '请求内容',
  response_preview: '回复预览',
  output_preview: '工具返回预览',
  tool_query: '查询参数',
}

function fmtValue(key: string, value: unknown): string {
  if (value === null || value === undefined) return '-'
  if (typeof value === 'boolean') return value ? '是' : '否'
  if (key === 'gen_ai.operation.name') {
    const map: Record<string, string> = {
      chat: '对话生成',
      embeddings: '文本向量化',
      rerank: '重排序',
      tool: '工具调用',
    }
    return map[String(value)] || String(value)
  }
  if (key === 'status') {
    const map: Record<string, string> = { ok: '成功', error: '失败', success: '成功' }
    return map[String(value)] || String(value)
  }
  if (key === 'k-agent.chat.mode') {
    const map: Record<string, string> = { react: 'ReAct 推理', function_calling: 'Function Calling' }
    return map[String(value)] || String(value)
  }
  if (Array.isArray(value)) {
    return value.slice(0, 5).map(String).join(' · ') + (value.length > 5 ? ` …+${value.length - 5}` : '')
  }
  if (typeof value === 'object') {
    return JSON.stringify(value).slice(0, 200)
  }
  return String(value)
}

function fmtKey(key: string): string {
  return KEY_LABELS[key] || key
}

// 长文本预览字段(单独大块展示而不挤在 key/value 表里)
const LONG_PREVIEW_KEYS = new Set([
  'request_summary',
  'response_preview',
  'output_preview',
  'tool_query',
  'rationale',
])

function humanizeName(name: string, terse: boolean): string {
  const PREFIXES = ['工具:', '工具：', '检索:', '检索：', '规划:', '规划：', '写作:', '写作：', '审稿:', '审稿：', '修复:', '修复：']
  for (const p of PREFIXES) {
    if (name.startsWith(p)) {
      return name.slice(p.length).trim()
    }
  }
  const chatMatch = name.match(/^chat(?:\(ReAct\))?:([^\s(]+)\s*\(轮\s*(\d+)\)/)
  if (chatMatch) {
    return terse ? `对话 · 第 ${chatMatch[2]} 轮` : `对话 · 第 ${chatMatch[2]} 轮 · ${chatMatch[1]}`
  }
  const chatBare = name.match(/^chat(?:\(ReAct\))?:(.+)$/)
  if (chatBare) {
    return terse ? '对话生成' : `对话 · ${chatBare[1]}`
  }
  const embedMatch = name.match(/^embed:(.+)$/)
  if (embedMatch) {
    return terse ? '向量化' : `向量化 · ${embedMatch[1]}`
  }
  const rerankMatch = name.match(/^rerank:(.+)$/)
  if (rerankMatch) {
    return terse ? '重排序' : `重排序 · ${rerankMatch[1]}`
  }
  const visionMatch = name.match(/^vision:(.+)$/)
  if (visionMatch) {
    return terse ? '看图' : `看图理解 · ${visionMatch[1]}`
  }
  return name
}

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


export default function TraceTimeline({ trace }: { trace: TraceDetail }) {
  // 内联展开:同时只展开一条;再点同一条收起
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const isMobile = useIsMobile()

  const { traceStart, traceEnd } = useMemo(() => {
    const ts = trace.started_at ? new Date(trace.started_at).getTime() : Date.now()
    let endMs = trace.finished_at ? new Date(trace.finished_at).getTime() : ts
    let startMs = ts
    for (const s of trace.spans) {
      const ss = new Date(s.started_at).getTime()
      const se = s.finished_at ? new Date(s.finished_at).getTime() : ss
      if (ss < startMs) startMs = ss
      if (se > endMs) endMs = se
    }
    if (endMs <= startMs) endMs = startMs + 1
    return { traceStart: startMs, traceEnd: endMs }
  }, [trace])

  const totalMs = Math.max(1, traceEnd - traceStart)

  const rows = useMemo(() => {
    return [...trace.spans]
      .sort((a, b) => a.started_at.localeCompare(b.started_at))
      .map((s) => {
        const start = new Date(s.started_at).getTime() - traceStart
        const end = (s.finished_at ? new Date(s.finished_at).getTime() : traceStart + totalMs) - traceStart
        const leftPct = Math.max(0, (start / totalMs) * 100)
        const widthPct = Math.max(0.4, ((end - start) / totalMs) * 100)
        return { span: s, leftPct, widthPct, durationMs: end - start }
      })
  }, [trace.spans, traceStart, totalMs])

  if (rows.length === 0) {
    return <Empty description="该任务没有执行步骤(可能 Tracing 已关闭或正在进行)" />
  }

  const ticks = Array.from({ length: 5 }, (_, i) => {
    const pct = (i / 4) * 100
    const ms = (totalMs * i) / 4
    return { pct, label: fmtMs(Math.round(ms)) }
  })

  const labelWidth = isMobile ? 100 : 180
  const labelFontSize = isMobile ? 11.5 : 12.5

  return (
    <div>
      {/* 时间刻度 */}
      <div
        style={{
          position: 'relative',
          height: 20,
          marginLeft: labelWidth,
          marginBottom: 6,
          borderBottom: '1px dashed #eef0f4',
          color: '#98A2B3',
          fontSize: isMobile ? 10 : 11,
        }}
      >
        {ticks.map((t, i) => (
          <span
            key={i}
            style={{
              position: 'absolute',
              left: `${t.pct}%`,
              transform: t.pct >= 95 ? 'translateX(-100%)' : (t.pct <= 5 ? 'none' : 'translateX(-50%)'),
              whiteSpace: 'nowrap',
            }}
          >
            {t.label}
          </span>
        ))}
      </div>

      {/* span 横条列表 —— 点击行内展开详情 */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
        {rows.map(({ span, leftPct, widthPct, durationMs }) => {
          const c = colorOf(span.span_type)
          const failed = span.status === 'error'
          const isExpanded = expandedId === span.span_id
          return (
            <div key={span.span_id}>
              {/* 时间线行 */}
              <div
                style={{
                  position: 'relative',
                  display: 'flex',
                  alignItems: 'center',
                  height: 28,
                  cursor: 'pointer',
                  borderRadius: 4,
                  background: isExpanded ? '#f0f7ff' : 'transparent',
                  transition: 'background 0.15s',
                }}
                onClick={() =>
                  setExpandedId(isExpanded ? null : span.span_id)
                }
                onMouseEnter={(e) => {
                  if (!isExpanded) e.currentTarget.style.background = '#f7f9fc'
                }}
                onMouseLeave={(e) => {
                  if (!isExpanded) e.currentTarget.style.background = ''
                }}
              >
                {/* 左侧标签栏 */}
                <div
                  style={{
                    width: labelWidth,
                    flexShrink: 0,
                    paddingLeft: 8,
                    fontSize: labelFontSize,
                    color: '#475467',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 4,
                  }}
                  title={span.name}
                >
                  <span
                    style={{
                      color: '#98A2B3',
                      fontSize: 10,
                      flexShrink: 0,
                      width: 10,
                      display: 'inline-block',
                    }}
                  >
                    {isExpanded ? '▼' : '▶'}
                  </span>
                  <span
                    style={{
                      display: 'inline-block',
                      fontSize: 10,
                      color: c.border,
                      fontWeight: 600,
                      flexShrink: 0,
                      minWidth: isMobile ? 22 : 28,
                    }}
                  >
                    {c.label}
                  </span>
                  <span
                    style={{
                      flex: 1,
                      minWidth: 0,
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                    }}
                  >
                    {humanizeName(span.name, true)}
                  </span>
                </div>
                {/* 时间轴区 */}
                <div style={{ position: 'relative', flex: 1, height: 28 }}>
                  <div
                    style={{
                      position: 'absolute',
                      top: 5,
                      height: 18,
                      left: `${leftPct}%`,
                      width: `${widthPct}%`,
                      minWidth: 4,
                      background: c.bg,
                      border: `1.5px solid ${failed ? '#FF4D4F' : c.border}`,
                      borderRadius: 3,
                      display: 'flex',
                      alignItems: 'center',
                      paddingLeft: 4,
                      fontSize: 10.5,
                      color: c.border,
                      fontWeight: 500,
                      overflow: 'hidden',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {widthPct >= 8 && !isMobile ? fmtMs(durationMs) : ''}
                  </div>
                </div>
              </div>
              {/* 行内展开:详情面板 */}
              {isExpanded && (
                <div
                  style={{
                    margin: '4px 0 10px',
                    padding: '14px 16px',
                    background: '#ffffff',
                    border: `1px solid ${c.border}33`,
                    borderLeft: `3px solid ${c.border}`,
                    borderRadius: 10,
                    animation: 'fadeInDown 0.2s ease-out',
                  }}
                >
                  <SpanDetailContent span={span} isMobile={isMobile} />
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}


function SpanDetailContent({ span, isMobile }: { span: SpanItem; isMobile: boolean }) {
  const failed = span.status === 'error'

  // 拆分:长文本预览 + 表格字段
  const { longPreviews, tableEntries } = useMemo(() => {
    const all: Record<string, unknown> = { ...(span.attributes || {}), ...(span.payload || {}) }
    const HIDDEN = new Set<string>([
      'gen_ai.request.model',
      'gen_ai.response.model',
      'gen_ai.operation.name',
    ])
    const previews: Array<[string, string]> = []
    const tabs: Array<[string, unknown]> = []
    for (const [k, v] of Object.entries(all)) {
      if (HIDDEN.has(k)) continue
      if (v === null || v === undefined) continue
      if (typeof v === 'string' && v.trim() === '') continue
      if (Array.isArray(v) && v.length === 0) continue
      if (LONG_PREVIEW_KEYS.has(k) && typeof v === 'string' && v.length > 0) {
        previews.push([k, v])
      } else {
        tabs.push([k, v])
      }
    }
    return { longPreviews: previews, tableEntries: tabs }
  }, [span])

  return (
    <Space direction="vertical" size={12} style={{ width: '100%' }}>
      {/* 顶部:关键指标 4 宫 */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: `repeat(auto-fit, minmax(${isMobile ? 100 : 130}px, 1fr))`,
          gap: 8,
        }}
      >
        <KpiBox label="状态" value={failed ? '失败' : '成功'} tone={failed ? 'error' : 'ok'} />
        <KpiBox label="耗时" value={fmtMs(span.duration_ms)} />
        {span.cost_cny > 0 && <KpiBox label="估算成本" value={fmtCost(span.cost_cny)} tone="warn" />}
        {(span.input_tokens + span.output_tokens) > 0 && (
          <KpiBox
            label="tokens"
            value={`${fmtTokens(span.input_tokens)} → ${fmtTokens(span.output_tokens)}`}
            sub="输入 → 输出"
          />
        )}
      </div>

      {/* 模型 + 缓存 */}
      {(span.model_name || span.cached_tokens > 0) && (
        <div
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            gap: 12,
            padding: '8px 12px',
            background: '#f7f9fc',
            borderRadius: 8,
            fontSize: 12.5,
          }}
        >
          {span.model_name && (
            <Space size={6}>
              <Text type="secondary">使用模型</Text>
              <Tag color="processing" style={{ margin: 0, fontWeight: 600 }}>{span.model_name}</Tag>
            </Space>
          )}
          {span.cached_tokens > 0 && (
            <Space size={6}>
              <Text type="secondary">缓存命中</Text>
              <Text strong style={{ color: '#369F21' }}>{fmtTokens(span.cached_tokens)} tokens</Text>
            </Space>
          )}
        </div>
      )}

      {/* 错误信息 */}
      {failed && span.error_message && (
        <div
          style={{
            padding: '10px 14px',
            background: '#fff1f0',
            border: '1px solid #ffccc7',
            borderRadius: 8,
            fontSize: 12.5,
            color: '#cf1322',
            lineHeight: 1.6,
            wordBreak: 'break-all',
          }}
        >
          <Text strong style={{ color: '#cf1322', display: 'block', marginBottom: 4 }}>
            ❌ 错误信息
          </Text>
          {span.error_message}
        </div>
      )}

      {/* Verifier Loop 关联提示 */}
      {span.iteration_id && (
        <div
          style={{
            padding: '8px 12px',
            background: 'linear-gradient(135deg, #f4f1fe 0%, #ffffff 70%)',
            border: '1px solid #e3dbff',
            borderRadius: 8,
            fontSize: 12.5,
          }}
        >
          <Space>
            <span style={{ color: '#7A5AF8', fontWeight: 600 }}>🔗</span>
            <Text type="secondary">这一步属于「质量复核 Loop」的回炉轮次</Text>
          </Space>
        </div>
      )}

      {/* 长文本预览(请求内容 / 回复预览 / 工具返回 / 决策理由)*/}
      {longPreviews.map(([k, v]) => (
        <div key={k}>
          <Text strong style={{ fontSize: 13, color: '#171719' }}>
            📝 {fmtKey(k)}
          </Text>
          <div
            style={{
              marginTop: 4,
              padding: '10px 12px',
              background: '#fafbfc',
              border: '1px solid #eef0f4',
              borderRadius: 8,
              fontSize: 12.5,
              color: '#475467',
              lineHeight: 1.7,
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
              maxHeight: 240,
              overflow: 'auto',
            }}
          >
            {v}
          </div>
        </div>
      ))}

      {/* 表格字段 */}
      {tableEntries.length > 0 && (
        <div>
          <Text strong style={{ fontSize: 13, color: '#171719' }}>📋 步骤详情</Text>
          <div
            style={{
              marginTop: 4,
              border: '1px solid #eef0f4',
              borderRadius: 8,
              overflow: 'hidden',
              fontSize: 12.5,
            }}
          >
            {tableEntries.map(([k, v], i) => (
              <div
                key={k}
                style={{
                  display: 'flex',
                  alignItems: 'flex-start',
                  gap: 12,
                  padding: '8px 12px',
                  background: i % 2 === 0 ? '#ffffff' : '#f9fafb',
                  lineHeight: 1.6,
                }}
              >
                <span style={{ width: isMobile ? 90 : 110, flexShrink: 0, color: '#667085' }}>
                  {fmtKey(k)}
                </span>
                <span style={{ flex: 1, color: '#171719', wordBreak: 'break-all', minWidth: 0 }}>
                  {fmtValue(k, v)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {longPreviews.length === 0 && tableEntries.length === 0 && !failed && (
        <Text type="secondary" style={{ fontSize: 12.5, fontStyle: 'italic' }}>
          这一步没有额外的执行详情。它是个容器步骤,主要工作在子步骤里。
        </Text>
      )}
    </Space>
  )
}

function KpiBox({
  label,
  value,
  tone,
  sub,
}: {
  label: string
  value: string
  tone?: 'ok' | 'error' | 'warn'
  sub?: string
}) {
  const color =
    tone === 'error' ? '#cf1322'
    : tone === 'ok' ? '#369F21'
    : tone === 'warn' ? '#FAAD14'
    : '#171719'
  return (
    <div
      style={{
        padding: '10px 12px',
        background: '#ffffff',
        border: '1px solid #eef0f4',
        borderRadius: 10,
      }}
    >
      <div style={{ fontSize: 11, color: '#98A2B3' }}>{label}</div>
      <div style={{ fontSize: 16, fontWeight: 700, color, marginTop: 2, lineHeight: 1.2 }}>
        {value}
      </div>
      {sub && <div style={{ fontSize: 10.5, color: '#98A2B3', marginTop: 2 }}>{sub}</div>}
    </div>
  )
}
