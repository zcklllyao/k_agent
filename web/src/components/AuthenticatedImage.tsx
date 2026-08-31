import { useEffect, useState } from 'react'
import { Image } from 'antd'
import type { ImageProps } from 'antd'

type ImgProps = React.ImgHTMLAttributes<HTMLImageElement>

function shouldFetchWithAuth(src?: string) {
  if (!src) return false
  // 本地存储文件需要带 Authorization 头，故用 fetch + blob 方式加载。
  return src.startsWith('/api/files/')
}

// ── 模块级 blob URL 缓存（带引用计数）──
// 同一个 src 只 fetch 一次，多个组件共享同一个 object URL；
// 用引用计数管理生命周期，最后一个使用者卸载时才释放，避免重复请求与误释放。
interface CacheEntry {
  promise: Promise<string> // 解析为 object URL
  url?: string // fetch 完成后的 object URL
  refs: number // 当前使用该 URL 的组件数
}

const blobCache = new Map<string, CacheEntry>()

function acquire(src: string): Promise<string> {
  let entry = blobCache.get(src)
  if (!entry) {
    const promise = (async () => {
      const token = localStorage.getItem('access_token')
      const headers: Record<string, string> = token
        ? { Authorization: `Bearer ${token}` }
        : {}
      const resp = await fetch(src, { headers })
      if (!resp.ok) {
        throw new Error(`图片加载失败: ${resp.status}`)
      }
      const blob = await resp.blob()
      const url = URL.createObjectURL(blob)
      const cur = blobCache.get(src)
      if (cur && cur.refs > 0) {
        cur.url = url
      } else {
        // fetch 期间使用者已全部卸载：立即释放，避免泄漏
        URL.revokeObjectURL(url)
        blobCache.delete(src)
      }
      return url
    })()
    entry = { promise, refs: 0 }
    blobCache.set(src, entry)
  }
  entry.refs += 1
  return entry.promise
}

function release(src: string) {
  const entry = blobCache.get(src)
  if (!entry) return
  entry.refs -= 1
  if (entry.refs <= 0) {
    if (entry.url) {
      URL.revokeObjectURL(entry.url)
    }
    blobCache.delete(src)
  }
}

function useAuthenticatedImageUrl(src?: string) {
  const [resolvedSrc, setResolvedSrc] = useState(src)

  useEffect(() => {
    if (!src || !shouldFetchWithAuth(src)) {
      setResolvedSrc(src)
      return
    }

    let active = true
    acquire(src)
      .then((url) => {
        if (active) setResolvedSrc(url)
      })
      .catch(() => {
        if (active) setResolvedSrc(src) // 失败回退原始 URL
      })

    return () => {
      active = false
      release(src)
    }
  }, [src])

  return resolvedSrc
}

export function AuthenticatedImage({ src, ...props }: ImgProps) {
  const resolvedSrc = useAuthenticatedImageUrl(src)
  return <img src={resolvedSrc} {...props} />
}

export function AuthenticatedAntdImage({ src, ...props }: ImageProps) {
  const resolvedSrc = useAuthenticatedImageUrl(src)
  return <Image src={resolvedSrc} {...props} />
}
