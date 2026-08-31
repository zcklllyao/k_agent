import client from '@/api/client'

// ── Types ──

export interface SpanItem {
  span_id: string
  parent_span_id: string | null
  trace_id: string
  span_type: string  // planner / retriever / writer / tool_call / verifier / repair / mcp_call / llm_call / other
  name: string
  status: 'running' | 'ok' | 'error'
  error_message: string | null
  started_at: string
  finished_at: string | null
  duration_ms: number | null
  model_name: string | null
  input_tokens: number
  output_tokens: number
  cached_tokens: number
  cost_cny: number
  payload: Record<string, unknown>
  attributes: Record<string, unknown>
  iteration_id: string | null
}

export interface TraceListItem {
  trace_id: string
  task_type: string
  task_id: string | null
  task_name: string | null
  status: 'running' | 'ok' | 'error'
  error_message: string | null
  started_at: string
  finished_at: string | null
  duration_ms: number | null
  total_input_tokens: number
  total_output_tokens: number
  total_cached_tokens: number
  total_cost_cny: number
  models_used: string[]
  loop_run_id: string | null
}

export interface TraceListResponse {
  total: number
  items: TraceListItem[]
}

export interface TraceDetail extends TraceListItem {
  root_span_id: string | null
  attributes: Record<string, unknown>
  spans: SpanItem[]
}

export interface ModelCostRow {
  model: string
  calls: number
  input_tokens: number
  output_tokens: number
  cached_tokens: number
  cost_cny: number
}

export interface TaskTypeCostRow {
  task_type: string
  count: number
  total_cost_cny: number
  avg_duration_ms: number
  fail_rate: number
}

export interface CostSummary {
  days: number
  total_traces: number
  total_input_tokens: number
  total_output_tokens: number
  total_cached_tokens: number
  total_cost_cny: number
  by_task_type: TaskTypeCostRow[]
  by_model: ModelCostRow[]
}

type Wrapped<T> = { code: number; message: string; data: T }

// ── API ──

export const traceApi = {
  list(params: {
    task_type?: string
    task_id?: string
    status?: string
    days?: number
    limit?: number
    offset?: number
  } = {}) {
    return client.get<unknown, Wrapped<TraceListResponse>>('/traces', { params })
  },
  detail(traceId: string) {
    return client.get<unknown, Wrapped<TraceDetail>>(`/traces/${traceId}`)
  },
  costSummary(days = 30) {
    return client.get<unknown, Wrapped<CostSummary>>('/traces/cost-summary', {
      params: { days },
    })
  },
}
