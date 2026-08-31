import client from './client'

interface Wrapped<T> {
  code: number
  message: string
  data: T
}

export interface KnowledgeBase {
  id: string
  name: string
  description: string | null
  icon: string | null
  color: string | null
  is_default: boolean
  chat_enabled: boolean
  doc_count: number
  image_count: number
  created_at: string | null
  overview_status: 'empty' | 'generating' | 'done' | 'failed'
  overview_updated_at: string | null
}

export interface KnowledgeBaseOverview {
  kb_id: string
  content: string
  status: 'empty' | 'generating' | 'done' | 'failed'
  error: string | null
  updated_at: string | null
}

export interface KnowledgeBaseInput {
  name: string
  description?: string | null
  icon?: string | null
  color?: string | null
}

export const knowledgeBaseApi = {
  list() {
    return client.get<unknown, Wrapped<KnowledgeBase[]>>('/knowledge-bases')
  },
  detail(id: string) {
    return client.get<unknown, Wrapped<KnowledgeBase>>(`/knowledge-bases/${id}`)
  },
  overview(id: string) {
    return client.get<unknown, Wrapped<KnowledgeBaseOverview>>(`/knowledge-bases/${id}/overview`)
  },
  generateOverview(id: string) {
    return client.post<unknown, Wrapped<KnowledgeBaseOverview>>(`/knowledge-bases/${id}/overview/generate`)
  },
  create(body: KnowledgeBaseInput) {
    return client.post<unknown, Wrapped<KnowledgeBase>>('/knowledge-bases', body)
  },
  update(id: string, body: Partial<KnowledgeBaseInput>) {
    return client.put<unknown, Wrapped<KnowledgeBase>>(`/knowledge-bases/${id}`, body)
  },
  setChatEnabled(id: string, chatEnabled: boolean) {
    return client.put<unknown, Wrapped<KnowledgeBase>>(
      `/knowledge-bases/${id}/chat-enabled`,
      { chat_enabled: chatEnabled },
    )
  },
  remove(id: string) {
    return client.delete<unknown, Wrapped<null>>(`/knowledge-bases/${id}`)
  },
}
