import { useEffect, useRef, useState } from 'react'

interface SelInfo {
  text: string
  x: number
  y: number
}

interface Props {
  // 选中 AI 回答片段后点「追问/解释」：把引用片段交给外部填进输入框
  onAsk: (text: string, mode: 'ask' | 'explain') => void
}

// 划词追问：监听 AI 回答气泡内的文本选择，在选区上方浮出「追问 / 解释」小工具条。
// 桌面端 mouseup 触发、移动端 touchend（长按选中后抬起）触发。纯前端，不改后端。
export default function SelectionPopover({ onAsk }: Props) {
  const [sel, setSel] = useState<SelInfo | null>(null)
  const barRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const isInsideAiMessage = (node: Node | null): boolean => {
      let el: HTMLElement | null =
        node instanceof HTMLElement ? node : node?.parentElement ?? null
      while (el) {
        if (el.dataset && el.dataset.aiMessage === 'true') return true
        el = el.parentElement
      }
      return false
    }

    const handle = () => {
      // 延迟一拍，确保 selection 已更新
      setTimeout(() => {
        const selection = window.getSelection()
        const text = selection?.toString().trim() ?? ''
        if (!text || !selection || selection.rangeCount === 0) {
          setSel(null)
          return
        }
        // 选区必须落在 AI 回答气泡内
        if (!isInsideAiMessage(selection.anchorNode)) {
          setSel(null)
          return
        }
        const rect = selection.getRangeAt(0).getBoundingClientRect()
        if (rect.width === 0 && rect.height === 0) {
          setSel(null)
          return
        }
        setSel({
          text,
          x: rect.left + rect.width / 2,
          y: rect.top,
        })
      }, 10)
    }

    const onDown = (e: MouseEvent | TouchEvent) => {
      // 点击工具条自身不关闭
      if (barRef.current && e.target instanceof Node && barRef.current.contains(e.target)) {
        return
      }
    }

    document.addEventListener('mouseup', handle)
    document.addEventListener('touchend', handle)
    document.addEventListener('mousedown', onDown)
    return () => {
      document.removeEventListener('mouseup', handle)
      document.removeEventListener('touchend', handle)
      document.removeEventListener('mousedown', onDown)
    }
  }, [])

  if (!sel) return null

  const fire = (mode: 'ask' | 'explain') => {
    onAsk(sel.text, mode)
    setSel(null)
    window.getSelection()?.removeAllRanges()
  }

  // 浮条定位：选区上方居中，避免超出视口左右边界
  const left = Math.min(Math.max(sel.x, 70), window.innerWidth - 70)
  const top = Math.max(sel.y - 46, 8)

  return (
    <div
      ref={barRef}
      className="sel-popover"
      style={{ left, top }}
      onMouseDown={(e) => e.preventDefault()} // 防止点击时丢失选区
    >
      <button className="sel-popover-btn" onClick={() => fire('ask')}>
        💬 追问
      </button>
      <span className="sel-popover-divider" />
      <button className="sel-popover-btn" onClick={() => fire('explain')}>
        💡 解释
      </button>
    </div>
  )
}
