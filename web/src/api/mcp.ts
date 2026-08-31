import client from './client'

interface Wrapped<T> {
  code: number
  message: string
  data: T
}

export type McpTransport = 'sse' | 'streamable_http'
export type McpAuthType = 'none' | 'bearer' | 'api_key'

export interface McpToolMeta {
  name: string
  description: string
}

export interface McpServer {
  id: string
  name: string
  transport: McpTransport
  url: string
  auth_type: McpAuthType
  auth_masked: string
  enabled: boolean
  status: string
  last_error: string | null
  tools_cache: McpToolMeta[]
  synced_at: string | null
  created_at: string
}

export interface McpServerInput {
  name: string
  transport: McpTransport
  url: string
  auth_type: McpAuthType
  auth_config?: Record<string, string> | null
  enabled?: boolean
}

export interface McpTestResult {
  success: boolean
  message: string
  tools: McpToolMeta[]
}

export const mcpApi = {
  list() {
    return client.get<unknown, Wrapped<McpServer[]>>('/tools/mcp')
  },
  create(body: McpServerInput) {
    return client.post<unknown, Wrapped<McpServer>>('/tools/mcp', body)
  },
  update(id: string, body: Partial<McpServerInput>) {
    return client.put<unknown, Wrapped<McpServer>>(`/tools/mcp/${id}`, body)
  },
  remove(id: string) {
    return client.delete<unknown, Wrapped<null>>(`/tools/mcp/${id}`)
  },
  test(id: string) {
    return client.post<unknown, Wrapped<McpTestResult>>(`/tools/mcp/${id}/test`)
  },
  sync(id: string) {
    return client.post<unknown, Wrapped<McpServer>>(`/tools/mcp/${id}/sync`)
  },
  toggle(id: string, enabled: boolean) {
    return client.put<unknown, Wrapped<McpServer>>(`/tools/mcp/${id}/toggle`, {
      enabled,
    })
  },
}
