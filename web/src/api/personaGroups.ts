import client from './client'

interface Wrapped<T> {
  code: number
  message: string
  data: T
}

export interface PersonaGroupMember {
  id: string
  name: string
  avatar_url: string | null
}

export interface PersonaGroup {
  id: string
  name: string
  description: string
  icon: string
  member_persona_ids: string[]
  members: PersonaGroupMember[]
  is_builtin: boolean
}

export interface BuiltinGroup {
  key: string
  name: string
  description: string
  icon: string
  members: { name: string }[]
}

export interface PersonaGroupPayload {
  name: string
  description?: string
  icon?: string
  member_persona_ids: string[]
}

export const personaGroupApi = {
  list() {
    return client.get<unknown, Wrapped<PersonaGroup[]>>('/persona-groups')
  },
  listBuiltins() {
    return client.get<unknown, Wrapped<BuiltinGroup[]>>('/persona-groups/builtins')
  },
  addBuiltin(key: string) {
    return client.post<unknown, Wrapped<PersonaGroup>>(`/persona-groups/builtins/${key}`)
  },
  create(body: PersonaGroupPayload) {
    return client.post<unknown, Wrapped<PersonaGroup>>('/persona-groups', body)
  },
  update(id: string, body: Partial<PersonaGroupPayload>) {
    return client.put<unknown, Wrapped<PersonaGroup>>(`/persona-groups/${id}`, body)
  },
  remove(id: string) {
    return client.delete<unknown, Wrapped<null>>(`/persona-groups/${id}`)
  },
}
