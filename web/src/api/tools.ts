import client from './client'

interface Wrapped<T> {
  code: number
  message: string
  data: T
}

export interface ToolItem {
  tool_key: string
  name: string
  description: string
  icon: string
  tool_type: string
  needs_config: boolean
  config_hint: string
  enabled: boolean
}

export const toolsApi = {
  list() {
    return client.get<unknown, Wrapped<ToolItem[]>>('/tools')
  },
  toggle(toolKey: string, enabled: boolean) {
    return client.put<unknown, Wrapped<{ tool_key: string; enabled: boolean }>>(
      `/tools/${toolKey}`,
      { enabled },
    )
  },
}
