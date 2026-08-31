import { useState } from 'react'
import { StarFilled, StarOutlined } from '@ant-design/icons'
import { Tooltip, message } from 'antd'
import { favoriteApi, type FavoriteType } from '@/api/favorites'

interface Props {
  targetType: FavoriteType
  targetId: string
  // 初始已收藏的收藏记录 id（来自列表加载时拉的收藏集合）
  initialFavId?: string | null
  snapshot?: Record<string, unknown>
  // 收藏态变化回调（让父组件同步集合）
  onChange?: (targetId: string, favId: string | null) => void
}

// 通用收藏星标：未收藏空心灰、已收藏实心金黄，点击切换
export default function FavoriteButton({
  targetType,
  targetId,
  initialFavId,
  snapshot,
  onChange,
}: Props) {
  const [favId, setFavId] = useState<string | null>(initialFavId ?? null)
  const [loading, setLoading] = useState(false)

  const toggle = async (e: React.MouseEvent) => {
    e.stopPropagation()
    if (loading) return
    setLoading(true)
    try {
      if (favId) {
        await favoriteApi.remove(favId)
        setFavId(null)
        onChange?.(targetId, null)
        message.success('已取消收藏')
      } else {
        const { data } = await favoriteApi.add(targetType, targetId, snapshot)
        setFavId(data.id)
        onChange?.(targetId, data.id)
        message.success('已收藏')
      }
    } catch (err) {
      message.error((err as Error).message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <Tooltip title={favId ? '取消收藏' : '收藏'}>
      {favId ? (
        <StarFilled onClick={toggle} style={{ color: '#FAAD14', cursor: 'pointer' }} />
      ) : (
        <StarOutlined onClick={toggle} style={{ color: '#C0C4CC', cursor: 'pointer' }} />
      )}
    </Tooltip>
  )
}
