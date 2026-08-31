import client from './client'

interface Wrapped<T> {
  code: number
  message: string
  data: T
}

export type ResearchStatus =
  | 'pending'
  | 'planning'
  | 'searching'
  | 'distilling'
  | 'reflecting'
  | 'curating'
  | 'writing'
  | 'summarizing'
  | 'done'
  | 'failed'

export interface ResearchSource {
  index: number
  type: 'web' | 'kb' | 'mcp'
  title: string
  url: string | null
}

export interface PlanSection {
  heading: string
  points: string
}

export interface ResearchPlan {
  title: string
  sections: PlanSection[]
  queries: string[]
}

export interface ReportBrief {
  id: string
  topic: string
  title: string | null
  status: ResearchStatus
  created_at: string | null
}

export interface ReportDetail extends ReportBrief {
  report_md: string | null
  outline: ResearchPlan | null
  sources: ResearchSource[]
  error_msg: string | null
}

export interface ResearchStep {
  icon: string // search | web | fetch | kb | mcp
  ok: boolean
  text: string
}

// V0.0.5 ② Verifier Loop:SSE 事件 payload + LoopRun 详情类型
export interface LoopVerifyScore {
  raw: Record<string, number>   // {coverage: 4, faithfulness: 4.5, ...} 原始 0~5 分
  total: number                  // 加权归一总分 0~1
}
export interface LoopVerifyStartEvent {
  iteration: number
}
export interface LoopVerifyDoneEvent {
  iteration: number
  scores: LoopVerifyScore | Record<string, never>
  feedback_summary?: string
  decision: 'pass' | 'retry_patch' | 'retry_rewrite' | 'exceed'
  note?: string
}
export interface LoopRepairStartEvent {
  iteration: number
  kind: 'patch' | 'chapter_rewrite' | 'force_exceed'
  rationale?: string
  patch_queries?: string[]
  rewrite_chapters?: string[]
}
export interface LoopFinishedEvent {
  status: 'passed' | 'exceeded' | 'failed'
  final_score: number | null
  iterations: number
  note?: string | null
  final_artifact?: Record<string, unknown>
}
export interface LoopStartedEvent {
  run_id: string
  rubric: string
  max_iterations: number
  pass_threshold: number
}
export interface LoopIterationDetail {
  iteration_no: number
  scores: { raw: Record<string, number>; total: number } | Record<string, never>
  feedback: {
    summary?: string
    issues?: { dim: string; detail: string }[]
    missing_coverage?: string[]
    wrong_citations?: number[]
    weak_chapters?: string[]
  }
  decision: string
  repair_action: {
    kind: string
    patch_queries?: string[]
    rewrite_chapters?: string[]
    rationale?: string
  } | null
  duration_ms: number | null
  artifact_snapshot: Record<string, unknown>
}
export interface LoopDetail {
  run_id: string
  task_type: string
  status: 'running' | 'passed' | 'failed' | 'exceeded'
  iterations: number
  final_score: number | null
  pass_threshold: number
  max_iterations: number
  rubric_name: string | null
  generator_model: string | null
  verifier_model: string | null
  verifier_kind: string | null
  note: string | null
  started_at: string | null
  finished_at: string | null
  iterations_detail: LoopIterationDetail[]
}

export interface ResearchStreamHandlers {
  onMeta?: (d: { report_id: string; topic: string }) => void
  onStatus?: (d: { phase: string; detail: string }) => void
  onPlan?: (d: ResearchPlan) => void
  onSources?: (sources: ResearchSource[]) => void
  onProgress?: (d: ResearchStep) => void
  onSectionStart?: (d: { heading: string }) => void
  onToken?: (text: string) => void
  onSectionDone?: (d: { heading: string }) => void
  onReport?: (d: { title: string; markdown: string; sources: ResearchSource[] }) => void
  onDone?: (d: { report_id: string }) => void
  onError?: (message: string) => void
  // V0.0.5 ② Verifier Loop:6 个新事件
  onLoopStarted?: (d: LoopStartedEvent) => void
  onLoopVerifyStart?: (d: LoopVerifyStartEvent) => void
  onLoopVerifyDone?: (d: LoopVerifyDoneEvent) => void
  onLoopRepairStart?: (d: LoopRepairStartEvent) => void
  onLoopRepairDone?: (d: { iteration: number; kind: string }) => void
  onLoopFinished?: (d: LoopFinishedEvent) => void
  // 续传快照
  onResume?: (d: {
    phase: string
    title: string
    plan: ResearchPlan | null
    sources: ResearchSource[]
    steps: ResearchStep[]
    partial_md: string
  }) => void
  onIdle?: () => void
}

export const researchApi = {
  list(page = 1, pageSize = 20) {
    return client.get<unknown, Wrapped<{ items: ReportBrief[]; total: number }>>(
      `/research?page=${page}&page_size=${pageSize}`,
    )
  },
  detail(id: string) {
    return client.get<unknown, Wrapped<ReportDetail>>(`/research/${id}`)
  },
  notify(id: string) {
    return client.post<unknown, Wrapped<{ sent: number; channel_type: string; repository_url: string }>>(
      `/research/${id}/notify`,
    )
  },
  remove(id: string) {
    return client.delete<unknown, Wrapped<null>>(`/research/${id}`)
  },
  saveToKb(id: string, kbId?: string | null) {
    return client.post<unknown, Wrapped<{ document_id: string; kb_id: string; kb_name: string }>>(
      `/research/${id}/save-to-kb`,
      { kb_id: kbId ?? null },
    )
  },
  // V0.0.5 ② Verifier Loop 详情:无 LoopRun(loop_enabled 关 / engine 异常时) → 返回 null
  loopDetail(id: string) {
    return client.get<unknown, Wrapped<LoopDetail | null>>(`/research/${id}/loop`)
  },
  optimizeTopic(topic: string) {
    return client.post<unknown, Wrapped<{ optimized: string }>>(
      '/research/optimize-topic',
      { topic },
    )
  },
  share(id: string, payload?: { title?: string; expire_days?: number | null }) {
    return client.post<unknown, Wrapped<ReportShare>>(`/research/${id}/share`, {
      title: payload?.title ?? null,
      expire_days: payload?.expire_days ?? null,
    })
  },
  listShares() {
    return client.get<unknown, Wrapped<ReportShare[]>>('/research/shares')
  },
  revokeShare(shareId: string) {
    return client.delete<unknown, Wrapped<null>>(`/research/shares/${shareId}`)
  },
  // 导出 Word：返回 docx 文件 blob（带鉴权头）
  async exportDocx(id: string): Promise<Blob> {
    const token = localStorage.getItem('access_token')
    const resp = await fetch(`/api/research/${id}/export/docx`, {
      headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    })
    if (!resp.ok) throw new Error(`导出失败（HTTP ${resp.status}）`)
    return resp.blob()
  },
}

export interface ReportShare {
  id: string
  report_id: string
  share_token: string
  title: string
  is_active: boolean
  expire_at: string | null
  view_count: number
  created_at: string | null
}

export interface PublicReportShare {
  title: string
  markdown: string
  sources: ResearchSource[]
  created_at: string | null
}

export function fetchPublicReportShare(token: string) {
  return client.get<unknown, { code: number; message: string; data: PublicReportShare }>(
    `/public/report-shares/${token}`,
  )
}

function dispatch(
  event: string,
  payload: Record<string, unknown>,
  h: ResearchStreamHandlers,
) {
  switch (event) {
    case 'meta':
      h.onMeta?.(payload as never)
      break
    case 'status':
      h.onStatus?.(payload as never)
      break
    case 'plan':
      h.onPlan?.(payload as never)
      break
    case 'sources':
      h.onSources?.((payload.sources as ResearchSource[]) ?? [])
      break
    case 'progress':
      h.onProgress?.(payload as never)
      break
    case 'section_start':
      h.onSectionStart?.(payload as never)
      break
    case 'token':
      h.onToken?.(payload.text as string)
      break
    case 'section_done':
      h.onSectionDone?.(payload as never)
      break
    case 'report':
      h.onReport?.(payload as never)
      break
    case 'resume':
      h.onResume?.(payload as never)
      break
    case 'idle':
      h.onIdle?.()
      break
    case 'done':
      h.onDone?.(payload as never)
      break
    case 'error':
      h.onError?.((payload.message as string) ?? '研究失败')
      break
    // V0.0.5 ② Verifier Loop 事件
    case 'loop_started':
      h.onLoopStarted?.(payload as never)
      break
    case 'loop_verify_start':
      h.onLoopVerifyStart?.(payload as never)
      break
    case 'loop_verify_done':
      h.onLoopVerifyDone?.(payload as never)
      break
    case 'loop_repair_start':
      h.onLoopRepairStart?.(payload as never)
      break
    case 'loop_repair_done':
      h.onLoopRepairDone?.(payload as never)
      break
    case 'loop_finished':
      h.onLoopFinished?.(payload as never)
      break
  }
}

async function consumeSSE(
  resp: Response,
  h: ResearchStreamHandlers,
): Promise<void> {
  if (!resp.ok || !resp.body) {
    h.onError?.(`请求失败（HTTP ${resp.status}）`)
    return
  }
  const reader = resp.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    let chunk: ReadableStreamReadResult<Uint8Array>
    try {
      chunk = await reader.read()
    } catch {
      break
    }
    if (chunk.done) break
    buffer += decoder.decode(chunk.value, { stream: true })
    const blocks = buffer.split('\n\n')
    buffer = blocks.pop() ?? ''
    for (const block of blocks) {
      const lines = block.split('\n')
      let event = 'message'
      let data = ''
      for (const line of lines) {
        if (line.startsWith('event:')) event = line.slice(6).trim()
        else if (line.startsWith('data:')) data += line.slice(5).trim()
      }
      if (!data) continue
      let payload: Record<string, unknown> = {}
      try {
        payload = JSON.parse(data)
      } catch {
        continue
      }
      dispatch(event, payload, h)
    }
  }
}

// 发起研究并流式推进度（POST SSE）
export async function streamResearch(
  topic: string,
  handlers: ResearchStreamHandlers,
  signal?: AbortSignal,
  kbIds?: string[] | null,
): Promise<void> {
  const token = localStorage.getItem('access_token')
  let resp: Response
  try {
    resp = await fetch('/api/research/stream', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ topic, kb_ids: kbIds ?? null }),
      signal,
    })
  } catch {
    handlers.onError?.('网络错误')
    return
  }
  await consumeSSE(resp, handlers)
}

// 重连续传：订阅进行中的研究（GET SSE），已结束会回放最终报告
export async function subscribeResearchEvents(
  reportId: string,
  handlers: ResearchStreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const token = localStorage.getItem('access_token')
  let resp: Response
  try {
    resp = await fetch(`/api/research/${reportId}/events`, {
      method: 'GET',
      headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      signal,
    })
  } catch {
    return
  }
  await consumeSSE(resp, handlers)
}
