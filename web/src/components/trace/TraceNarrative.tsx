/**
 * Trace 流程解读 —— 把一堆 span 翻译成「这次任务做了什么」的人话叙述。
 *
 * 规则化识别(纯前端,无后端依赖):
 * - 对话 trace:主动召回 → 决策轮 → 工具集 → 最终回答 + 洞察
 * - 研究 trace:规划 → 检索 → 提炼 → 反思 → 大纲 → 写作 → 汇总 → 复核
 * - 通用洞察:缓存命中率、最贵 span、错误归因
 *
 * 输出风格:编号步骤 + 一句描述 + 耗时 ·关联 span 数;再加 2~4 条洞察 bullet。
 */
import { useMemo, useState } from 'react'
import { Space, Typography } from 'antd'

import type { SpanItem, TraceDetail } from '@/api/traces'

const { Text } = Typography


type Phase = {
  icon: string
  title: string
  duration: string  // 人话耗时
  desc: string     // 一句话描述
  badge?: string   // 右上角徽章(轮次 / 数量等)
}

type Insight = {
  kind: 'good' | 'warn' | 'info'
  text: string
}


function fmtMs(ms: number | null | undefined): string {
  if (ms == null) return '-'
  if (ms < 1000) return `${ms}ms`
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`
  return `${(ms / 60_000).toFixed(1)}m`
}

function isChat(s: SpanItem) {
  return s.span_type === 'llm_call' && s.name.startsWith('chat')
}
function isEmbed(s: SpanItem) {
  return s.span_type === 'llm_call' && s.name.startsWith('embed')
}
function isTool(s: SpanItem) {
  return s.span_type === 'tool_call' || s.span_type === 'mcp_call'
}
function isRerank(s: SpanItem) {
  return s.span_type === 'llm_call' && s.name.startsWith('rerank')
}

function durMs(s: SpanItem): number {
  return s.duration_ms || 0
}

// 从 chat span 的 name 抽轮次:chat:deepseek-v4-pro (轮 1) → 1
function chatRoundNo(s: SpanItem): number | null {
  const m = s.name.match(/\(轮\s*(\d+)\)/)
  return m ? parseInt(m[1], 10) : null
}

// 从 tool span 抽工具名:工具:web_search → web_search
function toolName(s: SpanItem): string {
  const n = s.name
  const idx = n.indexOf(':')
  return idx > 0 ? n.slice(idx + 1).trim() : n
}


function buildChatNarrative(trace: TraceDetail): { phases: Phase[]; insights: Insight[] } {
  const spans = [...trace.spans].sort((a, b) =>
    a.started_at.localeCompare(b.started_at),
  )
  const phases: Phase[] = []
  const insights: Insight[] = []

  // 找所有 chat 轮次
  const chatSpans = spans.filter(isChat)
  const firstChatIdx = chatSpans.length > 0 ? spans.indexOf(chatSpans[0]) : -1

  // Phase 1:第一次 chat 之前的独立 embed(主动召回)
  if (firstChatIdx > 0) {
    const preChatSpans = spans.slice(0, firstChatIdx)
    const preEmbeds = preChatSpans.filter(isEmbed)
    if (preEmbeds.length > 0) {
      const dur = preEmbeds.reduce((s, x) => s + durMs(x), 0)
      phases.push({
        icon: '🧠',
        title: '主动召回',
        duration: fmtMs(dur),
        desc: '把你的问题向量化,去记忆图谱查相关的历史信息,作为背景拼进 system prompt',
        badge: preEmbeds.length > 1 ? `${preEmbeds.length} 次` : undefined,
      })
    }
  }

  // 对话 + 工具组 phases:按 chat span 切片,每个 chat 之间的 tool 组成一个工具集
  for (let i = 0; i < chatSpans.length; i++) {
    const chat = chatSpans[i]
    const next = chatSpans[i + 1]
    const isLast = i === chatSpans.length - 1
    const roundNo = chatRoundNo(chat)
    // chat 自身阶段
    phases.push({
      icon: isLast && chatSpans.length > 1 ? '✍️' : '🤔',
      title: isLast && chatSpans.length > 1
        ? '最终回答生成'
        : `决策轮 ${roundNo ?? i + 1}`,
      duration: fmtMs(durMs(chat)),
      desc: isLast && chatSpans.length > 1
        ? `模型读了前面所有工具的返回结果,流式产出最终回答(输出 ${chat.output_tokens.toLocaleString()} tokens)`
        : '模型读了问题+背景+工具列表,决定下一步该做什么',
      badge: chat.model_name || undefined,
    })
    // chat 之后到下一 chat 之前的工具/embed 组
    const groupStart = spans.indexOf(chat) + 1
    const groupEnd = next ? spans.indexOf(next) : spans.length
    const group = spans.slice(groupStart, groupEnd)
    const tools = group.filter(isTool)
    const groupEmbeds = group.filter(isEmbed)
    const groupReranks = group.filter(isRerank)
    if (tools.length > 0) {
      const toolNames = [...new Set(tools.map(toolName))]
      const dur = group.reduce((s, x) => s + durMs(x), 0)
      let desc = ''
      const internal: string[] = []
      if (groupEmbeds.length > 0) internal.push(`${groupEmbeds.length} 次向量化`)
      if (groupReranks.length > 0) internal.push(`${groupReranks.length} 次重排`)
      const internalNote = internal.length > 0 ? `(内部还做了 ${internal.join('、')})` : ''
      if (toolNames.length === 1) {
        desc = `调用 ${toolNames[0]} 工具 ${tools.length} 次${internalNote}`
      } else {
        desc = `并行调用了 ${tools.length} 个工具:${toolNames.join(' / ')}${internalNote}`
      }
      phases.push({
        icon: '🔧',
        title: `执行工具`,
        duration: fmtMs(dur),
        desc,
        badge: `${tools.length} 次`,
      })
    }
  }

  // ── 通用洞察 ──
  addCommonInsights(trace, spans, insights)

  return { phases, insights }
}


function buildResearchNarrative(trace: TraceDetail): { phases: Phase[]; insights: Insight[] } {
  const spans = [...trace.spans].sort((a, b) =>
    a.started_at.localeCompare(b.started_at),
  )
  const phases: Phase[] = []
  const insights: Insight[] = []

  const byType = (t: string) => spans.filter((s) => s.span_type === t)
  const planners = byType('planner').filter((s) => !s.name.startsWith('反思'))  // 规划但不是反思
  const reflectors = byType('planner').filter((s) => s.name.startsWith('反思'))
  const retrievers = byType('retriever')
  const writers = byType('writer').filter((s) => !s.name.startsWith('汇总') && !s.name.startsWith('补提炼'))
  const distillers = byType('writer').filter((s) => s.name.startsWith('补提炼') || s.name.startsWith('逐源提炼'))
  const summarizers = byType('writer').filter((s) => s.name.startsWith('汇总'))
  const verifiers = byType('verifier')
  const repairs = byType('repair')

  if (planners.length > 0) {
    phases.push({
      icon: '🗺️',
      title: '规划提纲',
      duration: fmtMs(planners.reduce((s, x) => s + durMs(x), 0)),
      desc: '把研究主题拆成多角度子问题,生成章节大纲',
    })
  }
  if (retrievers.length > 0) {
    const dur = retrievers.reduce((s, x) => s + durMs(x), 0)
    phases.push({
      icon: '🔎',
      title: '检索资料',
      duration: fmtMs(dur),
      desc: `从联网搜索、知识库、MCP 工具三路并行采集相关资料`,
      badge: retrievers.length > 1 ? `${retrievers.length} 轮` : undefined,
    })
  }
  if (distillers.length > 0) {
    phases.push({
      icon: '⚗️',
      title: '逐源提炼',
      duration: fmtMs(distillers.reduce((s, x) => s + durMs(x), 0)),
      desc: '把每个来源原始资料提炼成带来源编号的关键要点,引用对齐前置',
    })
  }
  if (reflectors.length > 0) {
    phases.push({
      icon: '💭',
      title: '反思补搜',
      duration: fmtMs(reflectors.reduce((s, x) => s + durMs(x), 0)),
      desc: '检查信息缺口,生成补充检索的子查询',
    })
  }
  // 大纲整理(planner 第二次,无法精确识别,跳过)
  if (writers.length > 0) {
    phases.push({
      icon: '✍️',
      title: '分节写作',
      duration: fmtMs(writers.reduce((s, x) => s + durMs(x), 0)),
      desc: '逐章节流式撰写,吃 curator 分配的要点 + 前文摘要避免重复',
      badge: `${writers.length} 章`,
    })
  }
  if (summarizers.length > 0) {
    phases.push({
      icon: '📋',
      title: '汇总摘要',
      duration: fmtMs(summarizers.reduce((s, x) => s + durMs(x), 0)),
      desc: '从全文提炼 TL;DR + 核心要点',
    })
  }
  if (verifiers.length > 0) {
    phases.push({
      icon: '🔍',
      title: '质量复核',
      duration: fmtMs(verifiers.reduce((s, x) => s + durMs(x), 0)),
      desc: '独立 LLM-as-judge 按 6 维评分(覆盖度/引用/深度/时效/相关性/可读)',
      badge: verifiers.length > 1 ? `${verifiers.length} 轮` : undefined,
    })
  }
  if (repairs.length > 0) {
    const kinds = [...new Set(repairs.map((s) => s.name.includes('rewrite') ? '重写' : '补搜'))]
    phases.push({
      icon: '🛠️',
      title: '不合格回炉',
      duration: fmtMs(repairs.reduce((s, x) => s + durMs(x), 0)),
      desc: `按 verifier 反馈选择策略修复:${kinds.join(' + ')}`,
      badge: `${repairs.length} 次`,
    })
  }

  addCommonInsights(trace, spans, insights)
  return { phases, insights }
}


function addCommonInsights(
  trace: TraceDetail,
  spans: SpanItem[],
  insights: Insight[],
): void {
  // 缓存命中率
  if (trace.total_input_tokens > 0 && trace.total_cached_tokens > 0) {
    const rate = (trace.total_cached_tokens / trace.total_input_tokens) * 100
    if (rate >= 5) {
      insights.push({
        kind: 'good',
        text: `命中 prompt 缓存 ${rate.toFixed(1)}%(${trace.total_cached_tokens.toLocaleString()} / ${trace.total_input_tokens.toLocaleString()} tokens),省了一笔钱`,
      })
    }
  }
  // 最贵 span
  const costliest = [...spans].sort((a, b) => b.cost_cny - a.cost_cny)[0]
  if (costliest && costliest.cost_cny > 0 && trace.total_cost_cny > 0) {
    const pct = (costliest.cost_cny / trace.total_cost_cny) * 100
    if (pct >= 40) {
      insights.push({
        kind: 'info',
        text: `「${humanName(costliest)}」一步占了 ${pct.toFixed(0)}% 的成本,是这次的主要支出`,
      })
    }
  }
  // 最慢 span
  const slowest = [...spans].sort((a, b) => durMs(b) - durMs(a))[0]
  if (slowest && trace.duration_ms && trace.duration_ms > 0) {
    const pct = (durMs(slowest) / trace.duration_ms) * 100
    if (pct >= 40 && durMs(slowest) > 3000) {
      insights.push({
        kind: 'info',
        text: `「${humanName(slowest)}」耗时占整体 ${pct.toFixed(0)}%,是性能瓶颈`,
      })
    }
  }
  // 错误检测
  const errs = spans.filter((s) => s.status === 'error')
  if (errs.length > 0) {
    insights.push({
      kind: 'warn',
      text: `有 ${errs.length} 个步骤执行失败:${errs.slice(0, 3).map(humanName).join('、')}${errs.length > 3 ? ' …' : ''}`,
    })
  }
  // 检索工具串行很多次的优化建议
  const toolCalls = spans.filter(isTool)
  const kbCalls = toolCalls.filter((s) => /knowledge|kb_search|web_search/.test(s.name))
  if (kbCalls.length >= 3) {
    insights.push({
      kind: 'warn',
      text: `本次串行调用了 ${kbCalls.length} 次检索类工具,问题可以问得更具体来减少工具调用次数`,
    })
  }
}


function humanName(s: SpanItem): string {
  const PREFIXES = ['工具:', '检索:', '规划:', '写作:', '审稿:', '修复:']
  for (const p of PREFIXES) {
    if (s.name.startsWith(p)) return s.name.slice(p.length).trim()
  }
  const m = s.name.match(/^(chat|embed|rerank|vision)(?:\([^)]+\))?:([^\s(]+)\s*\(轮\s*(\d+)\)?/)
  if (m) return `${m[1]} · 轮 ${m[3] || '?'}`
  const m2 = s.name.match(/^(chat|embed|rerank|vision):([^\s(]+)/)
  if (m2) return `${m2[1]} · ${m2[2]}`
  return s.name
}


export default function TraceNarrative({ trace }: { trace: TraceDetail }) {
  const [open, setOpen] = useState(true)

  const { phases, insights } = useMemo(() => {
    if (trace.task_type === 'chat') return buildChatNarrative(trace)
    if (trace.task_type === 'research') return buildResearchNarrative(trace)
    // 其他类型不生成解读
    return { phases: [], insights: [] }
  }, [trace])

  if (phases.length === 0) {
    return null
  }

  return (
    <div
      style={{
        padding: '14px 16px',
        background: 'linear-gradient(135deg, #f4f8ff 0%, #ffffff 70%)',
        border: '1px solid #dbe6ff',
        borderRadius: 12,
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: open ? 12 : 0,
          cursor: 'pointer',
        }}
        onClick={() => setOpen(!open)}
      >
        <Text strong style={{ fontSize: 14, color: '#171719' }}>
          📖 流程解读 · 这次任务做了什么
        </Text>
        <Text type="secondary" style={{ fontSize: 12 }}>
          {open ? '点击收起 ▲' : '点击展开 ▼'}
        </Text>
      </div>
      {open && (
        <Space direction="vertical" size={10} style={{ width: '100%' }}>
          {/* 阶段列表 */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {phases.map((p, i) => (
              <PhaseRow key={i} index={i + 1} phase={p} />
            ))}
          </div>

          {/* 洞察 */}
          {insights.length > 0 && (
            <div
              style={{
                marginTop: 6,
                paddingTop: 10,
                borderTop: '1px dashed #dbe6ff',
                display: 'flex',
                flexDirection: 'column',
                gap: 6,
              }}
            >
              {insights.map((it, i) => (
                <InsightRow key={i} insight={it} />
              ))}
            </div>
          )}
        </Space>
      )}
    </div>
  )
}


function PhaseRow({ index, phase }: { index: number; phase: Phase }) {
  return (
    <div
      style={{
        display: 'flex',
        gap: 10,
        alignItems: 'flex-start',
        padding: '8px 12px',
        background: '#ffffff',
        border: '1px solid #eef0f4',
        borderRadius: 8,
      }}
    >
      <span
        style={{
          flexShrink: 0,
          width: 22,
          height: 22,
          borderRadius: '50%',
          background: '#155EEF',
          color: '#fff',
          fontSize: 12,
          fontWeight: 700,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        {index}
      </span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div
          style={{
            display: 'flex',
            alignItems: 'baseline',
            gap: 8,
            flexWrap: 'wrap',
            marginBottom: 2,
          }}
        >
          <Text strong style={{ fontSize: 13.5, color: '#171719' }}>
            {phase.icon} {phase.title}
          </Text>
          <Text type="secondary" style={{ fontSize: 11.5, color: '#155EEF', fontWeight: 600 }}>
            {phase.duration}
          </Text>
          {phase.badge && (
            <span
              style={{
                padding: '1px 7px',
                fontSize: 11,
                fontWeight: 600,
                borderRadius: 999,
                background: '#EEF4FF',
                color: '#155EEF',
              }}
            >
              {phase.badge}
            </span>
          )}
        </div>
        <Text style={{ fontSize: 12.5, color: '#475467', lineHeight: 1.6 }}>
          {phase.desc}
        </Text>
      </div>
    </div>
  )
}


function InsightRow({ insight }: { insight: Insight }) {
  const meta = {
    good: { icon: '💡', color: '#369F21' },
    warn: { icon: '⚠️', color: '#FAAD14' },
    info: { icon: '📊', color: '#667085' },
  }[insight.kind]
  return (
    <div style={{ display: 'flex', gap: 8, alignItems: 'flex-start', fontSize: 12.5 }}>
      <span>{meta.icon}</span>
      <Text style={{ flex: 1, color: meta.color, lineHeight: 1.6 }}>{insight.text}</Text>
    </div>
  )
}
