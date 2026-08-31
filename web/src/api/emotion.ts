import client from './client'

interface Wrapped<T> {
  code: number
  message: string
  data: T
}

export interface EmotionProfile {
  dominant_emotion: string
  avg_valence: number
  avg_arousal: number
  sample_count: number
  updated_at: string | null
  health_index: number
}

export interface EmotionTrendPoint {
  date: string
  avg_valence: number
  avg_arousal: number
  count: number
}

export interface EmotionDistributionItem {
  name: string
  value: number
}

export interface EmotionRecord {
  id: string
  conversation_id: string | null
  message_id: string | null
  emotion_type: string
  intensity: number
  valence: number
  arousal: number
  keywords: string[]
  trigger: string | null
  summary: string | null
  created_at: string | null
}

export const emotionApi = {
  current() {
    return client.get<unknown, Wrapped<EmotionProfile>>('/emotion/current')
  },
  trend(days = 7) {
    return client.get<unknown, Wrapped<{ points: EmotionTrendPoint[] }>>(
      `/emotion/trend?days=${days}`,
    )
  },
  distribution(days = 30) {
    return client.get<unknown, Wrapped<{ items: EmotionDistributionItem[]; total: number }>>(
      `/emotion/distribution?days=${days}`,
    )
  },
  records(limit = 50, offset = 0) {
    return client.get<unknown, Wrapped<{ items: EmotionRecord[]; total: number }>>(
      `/emotion/records?limit=${limit}&offset=${offset}`,
    )
  },
}
