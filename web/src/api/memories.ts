import client from './client'

interface Wrapped<T> {
  code: number
  message: string
  data: T
}

export type MemoryStatus = 'pending' | 'extracting' | 'done' | 'failed'

export interface MemoryStats {
  dialogue_id: string
  chunks: number
  statements: number
  entities: number
  relations: number
  entity_ids: string[]
}

export interface MemoryItem {
  id: string
  raw_text: string
  source: 'auto' | 'manual'
  status: MemoryStatus
  error_msg: string | null
  graph_stats: MemoryStats | null
  created_at: string
}

export interface MemoryListData {
  total: number
  page: number
  page_size: number
  items: MemoryItem[]
}

export interface MemoryRelation {
  predicate: string
  object_name: string | null
  object_type: string | null
  source_text: string | null
  confidence?: number
  importance?: number
}

export interface MemoryHit {
  id: string
  name: string
  type: string
  description: string | null
  aliases: string[]
  score: number
  reliability_score?: number
  confidence?: number
  memory_layer?: string
  relations: MemoryRelation[]
}

// 画像：实体（含一跳关系）
export interface EntityRelation {
  predicate: string
  object_name: string | null
  object_type: string | null
  confidence?: number
  importance?: number
}

export interface ProfileEntity {
  id: string
  name: string
  type: string
  description: string
  aliases: string[]
  relations: EntityRelation[]
  importance: number
  confidence: number
  memory_layer: string
  access_count: number
  mention_count: number
  core_facts: string[]
  traits: string[]
}

export interface ProfileGroup {
  type: string
  entities: ProfileEntity[]
}

export interface MemoryProfile {
  total: number
  type_counts: Record<string, number>
  groups: ProfileGroup[]
}

export interface Community {
  id: string
  name: string
  summary: string
  member_count: number
}

export interface CommunityMember {
  id: string
  name: string
  type: string
  description: string
  aliases: string[]
}

// 知识图谱
export interface GraphNode {
  id: string
  name: string
  type: string
  description: string
  community_id: string | null
  kind?: string // 节点大类：Entity/Event/Statement/Chunk/Dialogue
  importance?: number
  memory_layer?: string
  access_count?: number
  mention_count?: number
  aliases?: string[]
  core_facts?: string[]
  traits?: string[]
}

export interface GraphEdge {
  source: string
  target: string
  rel?: string // 边类型：HAS_CHUNK/HAS_STATEMENT/MENTIONS/RELATION/INVOLVES
  predicate: string
  predicate_surface: string
}

export interface GraphData {
  nodes: GraphNode[]
  edges: GraphEdge[]
  communities: Community[]
}

export interface EntitySubgraph {
  center: string
  nodes: GraphNode[]
  edges: GraphEdge[]
}

// 事件时间线
export interface TimelineParticipant {
  id: string
  name: string
  type: string
}

export interface TimelineEvent {
  id: string
  title: string
  description: string
  event_time: string | null
  created_at: string | null
  participants: TimelineParticipant[]
}

// 反思洞察
export interface Insight {
  id: string
  theme: string
  content: string
  importance: number
  confidence: number
  source_count: number
  created_at: string | null
  updated_at: string | null
}

export const memoryApi = {
  remember(text: string) {
    return client.post<unknown, Wrapped<MemoryItem>>('/memories/remember', { text })
  },
  profile() {
    return client.get<unknown, Wrapped<MemoryProfile>>('/memories/profile')
  },
  deleteEntity(entityId: string) {
    return client.delete<unknown, Wrapped<null>>(`/memories/entity/${entityId}`)
  },
  communities() {
    return client.get<unknown, Wrapped<Community[]>>('/memories/communities')
  },
  communityMembers(id: string) {
    return client.get<unknown, Wrapped<CommunityMember[]>>(`/memories/communities/${id}`)
  },
  recluster() {
    return client.post<unknown, Wrapped<null>>('/memories/recluster')
  },
  mergeDuplicates() {
    return client.post<unknown, Wrapped<{ removed: number }>>('/memories/merge-duplicates')
  },
  consolidate() {
    return client.post<
      unknown,
      Wrapped<{ promoted_entities: number; promoted_statements: number; enhanced_profiles: number }>
    >('/memories/consolidate')
  },
  graph() {
    return client.get<unknown, Wrapped<GraphData>>('/memories/graph')
  },
  entitySubgraph(id: string) {
    return client.get<unknown, Wrapped<EntitySubgraph>>(`/memories/graph/entity/${id}`)
  },
  timeline() {
    return client.get<unknown, Wrapped<TimelineEvent[]>>('/memories/timeline')
  },
  insights() {
    return client.get<unknown, Wrapped<Insight[]>>('/memories/insights')
  },
  reflect() {
    return client.post<unknown, Wrapped<{ insights: number }>>('/memories/reflect')
  },
  deleteInsight(id: string) {
    return client.delete<unknown, Wrapped<null>>(`/memories/insights/${id}`)
  },
  list(page = 1, pageSize = 20) {
    const q = new URLSearchParams({ page: String(page), page_size: String(pageSize) })
    return client.get<unknown, Wrapped<MemoryListData>>(`/memories?${q.toString()}`)
  },
  detail(id: string) {
    return client.get<unknown, Wrapped<MemoryItem>>(`/memories/${id}`)
  },
  remove(id: string) {
    return client.delete<unknown, Wrapped<null>>(`/memories/${id}`)
  },
  search(query: string, topK = 10) {
    return client.post<unknown, Wrapped<MemoryHit[]>>('/memories/search', {
      query,
      top_k: topK,
    })
  },
  // ── V0.0.5 ⑤ 记忆审查与人类反馈闭环 ──
  reviewOverview(days = 30) {
    return client.get<unknown, Wrapped<ReviewOverview>>(
      `/memories/review/overview?days=${days}`,
    )
  },
  reviewEntities(opts: {
    maxConfidence?: number
    type?: string | null
    includeVerified?: boolean
    limit?: number
  } = {}) {
    const q = new URLSearchParams()
    q.set('max_confidence', String(opts.maxConfidence ?? 0.75))
    if (opts.type) q.set('type', opts.type)
    if (opts.includeVerified) q.set('include_verified', 'true')
    if (opts.limit) q.set('limit', String(opts.limit))
    return client.get<unknown, Wrapped<ReviewEntity[]>>(
      `/memories/review/entities?${q.toString()}`,
    )
  },
  reviewConfirm(entityId: string, reason?: string) {
    return client.post<unknown, Wrapped<{ ok: boolean; entity_id: string }>>(
      `/memories/review/${entityId}/confirm`,
      { reason: reason ?? null },
    )
  },
  reviewCorrect(
    entityId: string,
    body: {
      name?: string | null
      type?: string | null
      description?: string | null
      aliases?: string[] | null
      reason?: string | null
    },
  ) {
    return client.patch<unknown, Wrapped<{ ok: boolean; entity_id: string; name: string }>>(
      `/memories/review/${entityId}/correct`,
      body,
    )
  },
  reviewDelete(entityId: string, reason?: string) {
    const q = reason ? `?reason=${encodeURIComponent(reason)}` : ''
    return client.delete<unknown, Wrapped<{ ok: boolean; entity_id: string }>>(
      `/memories/review/${entityId}${q}`,
    )
  },
}

// ── V0.0.5 ⑤ 类型 ──

export interface ReviewOverview {
  total_entities: number
  total_relations: number
  long_term: number
  verified: number
  pending: number
  type_distribution: { type: string; count: number }[]
  confidence_buckets: { range: string; count: number }[]
  trend: { date: string; count: number }[]
  correction_counts: Record<string, number>
  days: number
}

export interface ReviewEntity {
  id: string
  name: string
  type: string
  description: string | null
  aliases: string[]
  confidence: number
  memory_layer: 'short_term' | 'long_term'
  human_verified: boolean
  relations: {
    predicate: string | null
    object_name: string | null
    object_type: string | null
    confidence: number
  }[]
}
