/**
 * 工具调用过程展示：顶部 1px 流光进度线 + 单行状态条 + 横排工具 chip。
 *
 * 状态机驱动（基于真实 SSE 事件派生 phase，不依赖后端文字 thought）：
 * - 流式中无 toolRuns：phase = 'understanding'，显示「正在理解问题」
 * - 有 toolRun running：phase = 'tool_running'，显示「正在检索 · {工具名}」+ query + 计时
 * - toolRun 全部 done 但 token 还没来：phase = 'analyzing'，显示「正在汇总信息」
 * - 第一个 token 到达：phase = 'generating'，状态条淡出消失，仅留 chip 行
 * - done：状态条已隐藏，chip 行常驻，作为永久 footprint（历史消息打开就是这一行）
 *
 * chip 副文绑定 toolRun.stats（命中数/实体数/网页数等），有数据就显示真信息。
 * chip 可点击 → 展开 inline 详情面板（query / preview / stats / latency / 引用计数徽标）。
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import { CheckCircleFilled, ExclamationCircleFilled } from '@ant-design/icons'
import type { Citation, ToolRun, ToolRunStats, ToolRunStatus } from '@/api/chat'
import MarkdownMessage from '@/components/MarkdownMessage'
import { resolveToolMeta } from './types'

type Phase = 'understanding' | 'tool_running' | 'analyzing' | 'generating' | 'done'

function derivePhase(
  toolRuns: ToolRun[] | undefined,
  hasContent: boolean,
  streaming: boolean,
): Phase {
  if (!streaming) return 'done'
  if (hasContent) return 'generating'
  const runs = toolRuns ?? []
  const running = runs.find((r) => r.status === 'running')
  if (running) return 'tool_running'
  if (runs.length > 0) return 'analyzing'
  return 'understanding'
}

function formatStats(stats?: ToolRunStats, tool?: string): string {
  if (!stats) return ''
  if (tool === 'knowledge_search') {
    const hits = (stats.hit_count as number) ?? 0
    const docs = (stats.doc_count as number) ?? 0
    if (hits === 0) return '未命中'
    return docs > 0 ? `${hits} 条命中 · ${docs} 篇文档` : `${hits} 条命中`
  }
  if (tool === 'memory_search') {
    const ents = (stats.entity_count as number) ?? 0
    const rels = (stats.relation_count as number) ?? 0
    if (ents === 0) return '未命中'
    return `${ents} 个实体 · ${rels} 条关系`
  }
  if (tool === 'web_search') {
    const webs = (stats.web_count as number) ?? 0
    return webs > 0 ? `${webs} 个网页` : '未命中'
  }
  return ''
}

function formatLatency(ms?: number): string {
  if (typeof ms !== 'number') return ''
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

/**
 * 详情面板 result 字段的渲染处理：
 * - 看着像 JSON（{} 或 []）→ 解析后用 ```json 代码块（自动美化 + 高亮）
 * - 否则当作 Markdown 渲染（标题、列表、链接都能正确显示）
 */
function renderResultMarkdown(text: string): string {
  const trimmed = text.trim()
  if (!trimmed) return ''
  if (
    (trimmed.startsWith('{') && trimmed.endsWith('}')) ||
    (trimmed.startsWith('[') && trimmed.endsWith(']'))
  ) {
    try {
      const obj = JSON.parse(trimmed)
      return '```json\n' + JSON.stringify(obj, null, 2) + '\n```'
    } catch {
      // 解析失败：当 Markdown 处理
    }
  }
  return text
}

const STATUS_TEXT: Record<ToolRunStatus, string> = {
  running: '运行中',
  success: '已完成',
  error: '失败',
}

interface Props {
  toolRuns?: ToolRun[]
  citations?: Citation[]
  hasContent: boolean
  streaming: boolean
}

export default function ChatProcess({
  toolRuns,
  citations,
  hasContent,
  streaming,
}: Props) {
  const phase = derivePhase(toolRuns, hasContent, streaming)
  const runs = toolRuns ?? []
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [tick, setTick] = useState(0)
  const startedAtRef = useRef<Record<string, number>>({})

  // 运行中工具的"实时计时"：每 100ms 触发一次重渲染（仅 phase 在 tool_running 时启用）
  useEffect(() => {
    if (phase !== 'tool_running') return
    const id = window.setInterval(() => setTick((x) => x + 1), 100)
    return () => window.clearInterval(id)
  }, [phase])

  // 记录每个 run 的起始时间，用于运行中实时显示秒数
  useEffect(() => {
    runs.forEach((r) => {
      if (!startedAtRef.current[r.id]) startedAtRef.current[r.id] = Date.now()
    })
  }, [runs])

  // 状态条文案：基于真实事件派生（运行中那条用工具名 + query + 实时秒数）
  const headlineText = useMemo(() => {
    if (phase === 'generating' || phase === 'done') return ''
    if (phase === 'understanding') return '正在理解问题…'
    if (phase === 'analyzing') return '正在汇总信息…'
    // tool_running
    const running = runs.find((r) => r.status === 'running')
    if (!running) return '正在检索…'
    const meta = resolveToolMeta(running.tool)
    const since = startedAtRef.current[running.id]
    const sec = since ? ((Date.now() - since) / 1000).toFixed(1) : '0.0'
    const q = running.query ? ` · 「${running.query}」` : ''
    return `正在检索 · ${meta.label}${q} · ${sec}s`
    // tick 触发重渲染，无需读它
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phase, runs, tick])

  // 进度推进：理解 25% / 调工具 25~75%（按工具完成数线性映射）/ 汇总 80% / 生成 100%
  const progress = useMemo(() => {
    if (phase === 'done' || phase === 'generating') return 100
    if (phase === 'understanding') return 18
    if (phase === 'analyzing') return 80
    // tool_running
    if (runs.length === 0) return 30
    const done = runs.filter((r) => r.status !== 'running').length
    return 30 + Math.round((done / Math.max(runs.length, 1)) * 45)
  }, [phase, runs])

  // 计算每个 chip 的"引用闭环徽标"：当前回答 citations 里有几条来自该工具
  // 知识库 chip 显示对应 citation 数；其他工具暂不计（无引用关联）
  const citationCount = useMemo(() => {
    const map: Record<string, number> = {}
    if (!citations || citations.length === 0) return map
    let n = 0
    for (const c of citations) {
      if (c.source_type === 'document' || c.source_type === 'image') n++
    }
    if (n > 0) map['knowledge_search'] = n
    return map
  }, [citations])

  // 没有任何过程数据 + 不在流式 → 不渲染（兜底）
  if (runs.length === 0 && !streaming) return null

  const headlineVisible = phase !== 'generating' && phase !== 'done'
  const focusedId = expandedId

  return (
    <div className="chat-process" data-phase={phase}>
      {/* 顶部 1px 流光进度线（无 emoji） */}
      {streaming && (
        <div className="chat-process-progress">
          <div
            className="chat-process-progress-bar"
            style={{ width: `${progress}%` }}
          />
        </div>
      )}

      {/* 状态条（替换式刷新；生成阶段开始淡出，DOM 仍保留高度过渡） */}
      <div
        className={`chat-process-headline${headlineVisible ? '' : ' chat-process-headline--hide'}`}
      >
        <span className="chat-process-dot chat-process-dot--running" />
        <span className="chat-process-text">{headlineText}</span>
      </div>

      {/* 工具 chip 行（横排 wrap） */}
      {runs.length > 0 && (
        <div
          className={`chat-process-tools${focusedId ? ' chat-process-tools--has-focus' : ''}`}
        >
          {runs.map((run, i) => {
            const meta = resolveToolMeta(run.tool)
            const focused = focusedId === run.id
            const dimmed = focusedId !== null && !focused
            const sub = run.status === 'running' ? '检索中…' : formatStats(run.stats, run.tool)
            const cite = citationCount[run.tool] ?? 0
            return (
              <div
                key={run.id}
                className={[
                  'chat-process-chip',
                  `chat-process-chip--${run.status}`,
                  focused ? 'chat-process-chip--focus' : '',
                  dimmed ? 'chat-process-chip--dim' : '',
                ]
                  .filter(Boolean)
                  .join(' ')}
                style={{ animationDelay: `${i * 60}ms` }}
                onClick={() => setExpandedId(focused ? null : run.id)}
              >
                <span className="chat-process-chip__icon">
                  {run.status === 'running' ? (
                    <span className="chat-process-spinner" />
                  ) : run.status === 'success' ? (
                    <CheckCircleFilled />
                  ) : (
                    <ExclamationCircleFilled />
                  )}
                </span>
                <span className="chat-process-chip__name">
                  {meta.icon} {meta.label}
                </span>
                {sub && <span className="chat-process-chip__sub">· {sub}</span>}
                {cite > 0 && (
                  <span
                    className="chat-process-chip__badge"
                    title={`本次回答引用了 ${cite} 项`}
                  >
                    {cite}
                  </span>
                )}
              </div>
            )
          })}
        </div>
      )}

      {/* 展开详情面板（被点 chip 的 query / preview / stats / latency） */}
      {focusedId && (() => {
        const run = runs.find((r) => r.id === focusedId)
        if (!run) return null
        const meta = resolveToolMeta(run.tool)
        const sub = formatStats(run.stats, run.tool)
        const lat = formatLatency(run.latencyMs)
        return (
          <div className="chat-process-panel">
            <div className="chat-process-panel__head">
              <span className="chat-process-panel__title">
                {meta.icon} {meta.label}
              </span>
              <span className="chat-process-panel__meta">
                {STATUS_TEXT[run.status]}
                {sub ? ` · ${sub}` : ''}
                {lat ? ` · ${lat}` : ''}
              </span>
            </div>
            {run.query && (
              <div className="chat-process-panel__row">
                <span className="chat-process-panel__label">查询</span>
                <span className="chat-process-panel__value">{run.query}</span>
              </div>
            )}
            {run.result && (
              <div className="chat-process-panel__row">
                <span className="chat-process-panel__label">摘要</span>
                <div className="chat-process-panel__value chat-process-panel__md">
                  <MarkdownMessage content={renderResultMarkdown(run.result)} />
                </div>
              </div>
            )}
          </div>
        )
      })()}
    </div>
  )
}
