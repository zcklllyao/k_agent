import client from './client'

interface Wrapped<T> {
  code: number
  message: string
  data: T
}

export type DocStatus = 'pending' | 'parsing' | 'done' | 'failed'

export interface DocTag {
  name: string
  color: string
}

export interface DocumentItem {
  id: string
  kb_id: string | null
  file_name: string
  file_ext: string
  file_size: number
  source_type: string
  source_url: string | null
  status: DocStatus
  progress: number
  chunk_num: number
  error_msg: string | null
  tags: DocTag[]
  created_at: string
}

export interface DocumentListData {
  total: number
  page: number
  page_size: number
  items: DocumentItem[]
}

export interface SearchHit {
  chunk_id: string
  content: string
  doc_name: string | null
  source_id: string | null
  source_type: string | null
  score: number
}

export interface DocumentPreview {
  id: string
  file_name: string
  file_ext: string
  is_markdown: boolean
  source_url: string | null
  content: string
  truncated: boolean
}

export const documentApi = {
  list(page = 1, pageSize = 100, tag?: string, kbId?: string) {
    const q = new URLSearchParams({ page: String(page), page_size: String(pageSize) })
    if (tag) q.set('tag', tag)
    if (kbId) q.set('kb_id', kbId)
    return client.get<unknown, Wrapped<DocumentListData>>(`/documents?${q.toString()}`)
  },
  // 上传文档（multipart）
  upload(file: File, kbId?: string) {
    const form = new FormData()
    form.append('file', file)
    if (kbId) form.append('kb_id', kbId)
    return client.post<unknown, Wrapped<DocumentItem>>(
      '/documents/upload',
      form,
      { headers: { 'Content-Type': 'multipart/form-data' } },
    )
  },
  importUrl(url: string, kbId?: string) {
    return client.post<unknown, Wrapped<DocumentItem>>('/documents/from-url', {
      url,
      kb_id: kbId,
    })
  },
  detail(id: string) {
    return client.get<unknown, Wrapped<DocumentItem>>(`/documents/${id}`)
  },
  preview(id: string) {
    return client.get<unknown, Wrapped<DocumentPreview>>(`/documents/${id}/preview`)
  },
  status(id: string) {
    return client.get<unknown, Wrapped<{ status: DocStatus; progress: number; error_msg: string | null }>>(
      `/documents/${id}/status`,
    )
  },
  retry(id: string) {
    return client.post<unknown, Wrapped<DocumentItem>>(`/documents/${id}/retry`)
  },
  remove(id: string) {
    return client.delete<unknown, Wrapped<null>>(`/documents/${id}`)
  },
  bulkRemove(ids: string[]) {
    return client.post<
      unknown,
      Wrapped<{ requested: number; deleted: number; skipped: number }>
    >('/documents/bulk-delete', { ids })
  },
  move(id: string, kbId: string) {
    return client.put<unknown, Wrapped<DocumentItem>>(`/documents/${id}/move`, {
      kb_id: kbId,
    })
  },
  search(query: string, topK = 5, tags?: string[]) {
    return client.post<unknown, Wrapped<SearchHit[]>>('/documents/search', {
      query,
      top_k: topK,
      tags,
    })
  },
}
