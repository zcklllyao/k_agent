import client from './client'

interface Wrapped<T> {
  code: number
  message: string
  data: T
}

export type ChannelType = 'serverchan' | 'wecom' | 'dingtalk' | 'feishu' | 'webhook'

export interface NotifyChannel {
  id: string
  channel_type: ChannelType
  name: string
  target_mask: string
  secret_configured?: boolean
  enabled: boolean
  created_at: string | null
}

export interface NotifyChannelCreate {
  channel_type: ChannelType
  name?: string
  target: string
  secret?: string
  enabled?: boolean
}

export interface NotifyChannelUpdate {
  name?: string
  target?: string
  secret?: string
  enabled?: boolean
}

export const notifyApi = {
  list() {
    return client.get<unknown, Wrapped<NotifyChannel[]>>('/notify-channels')
  },
  create(body: NotifyChannelCreate) {
    return client.post<unknown, Wrapped<NotifyChannel>>('/notify-channels', body)
  },
  update(id: string, body: NotifyChannelUpdate) {
    return client.put<unknown, Wrapped<NotifyChannel>>(`/notify-channels/${id}`, body)
  },
  test(id: string) {
    return client.post<unknown, Wrapped<null>>(`/notify-channels/${id}/test`)
  },
  remove(id: string) {
    return client.delete<unknown, Wrapped<null>>(`/notify-channels/${id}`)
  },
}
