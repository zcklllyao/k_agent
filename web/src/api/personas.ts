import client from './client'

interface Wrapped<T> {
  code: number
  message: string
  data: T
}

export interface Persona {
  id: string
  name: string
  avatar_key: string | null
  avatar_url: string | null
  system_prompt: string
  temperature: number
  is_active: boolean
}

export interface PersonaPayload {
  name: string
  avatar_key?: string | null
  system_prompt?: string
  temperature?: number
}

export const personaApi = {
  list(all = false) {
    return client.get<unknown, Wrapped<Persona[]>>('/personas', {
      params: all ? { all: true } : undefined,
    })
  },
  create(body: PersonaPayload) {
    return client.post<unknown, Wrapped<Persona>>('/personas', body)
  },
  update(id: string, body: Partial<PersonaPayload>) {
    return client.put<unknown, Wrapped<Persona>>(`/personas/${id}`, body)
  },
  remove(id: string) {
    return client.delete<unknown, Wrapped<null>>(`/personas/${id}`)
  },
  activate(id: string) {
    return client.post<unknown, Wrapped<Persona>>(`/personas/${id}/activate`)
  },
}
