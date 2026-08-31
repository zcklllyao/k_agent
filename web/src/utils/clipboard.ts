/**
 * 复制文本到剪贴板，带降级兼容。
 *
 * navigator.clipboard 只在安全上下文（HTTPS / localhost）可用；
 * 线上若是纯 http + IP 访问，该 API 不可用，回退到 document.execCommand('copy')
 * （创建临时 textarea 选中复制），后者在 http 下也能工作。
 *
 * @returns 是否复制成功
 */
export async function copyText(text: string): Promise<boolean> {
  // 优先用现代 API（安全上下文下）
  if (navigator.clipboard && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(text)
      return true
    } catch {
      // 失败则继续走降级
    }
  }
  // 降级：临时 textarea + execCommand
  try {
    const ta = document.createElement('textarea')
    ta.value = text
    // 移出视口、避免影响布局与滚动
    ta.style.position = 'fixed'
    ta.style.top = '-9999px'
    ta.style.left = '-9999px'
    ta.setAttribute('readonly', '')
    document.body.appendChild(ta)
    ta.select()
    ta.setSelectionRange(0, ta.value.length)
    const ok = document.execCommand('copy')
    document.body.removeChild(ta)
    return ok
  } catch {
    return false
  }
}
