import client from './client'

interface Wrapped<T> {
  code: number
  message: string
  data: T
}

export interface DailyReview {
  date: string
  content: string
  care?: string
  stats: { messages: number; memories: number; documents: number } | null
  generating?: boolean
  created_at: string
}

export interface OverviewData {
  counts: {
    documents: number
    images: number
    conversations: number
    entities: number
    communities: number
  }
  tag_distribution: { name: string; value: number }[]
  recent: { type: string; title: string; time: string | null }[]
}

export interface MemoryStatsData {
  trend: { date: string; count: number }[]
  community_distribution: { name: string; value: number }[]
}

export interface AgentBriefItem {
  id: string
  title: string
  scheduled: boolean
  created_at: string | null
}

// V0.0.5 ② Loop 健康度
export interface LoopHealthData {
  days: number
  total: number
  passed: number
  exceeded: number
  failed: number
  one_shot_pass_rate: number   // 一次通过率 0~1
  avg_iterations: number
  avg_final_score: number
  failure_dims: { dim: string; label: string; count: number }[]
  verifier_kinds: Record<string, number>
}

export const dashboardApi = {
  dailyReview() {
    return client.get<unknown, Wrapped<DailyReview>>('/dashboard/daily-review')
  },
  overview() {
    return client.get<unknown, Wrapped<OverviewData>>('/dashboard/overview')
  },
  memoryStats() {
    return client.get<unknown, Wrapped<MemoryStatsData>>('/dashboard/memory-stats')
  },
  agentBriefing() {
    return client.get<unknown, Wrapped<AgentBriefItem[]>>('/dashboard/agent-briefing')
  },
  loopHealth(days = 30) {
    return client.get<unknown, Wrapped<LoopHealthData>>(`/dashboard/loop-health?days=${days}`)
  },
}
